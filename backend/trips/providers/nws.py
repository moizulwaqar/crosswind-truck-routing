"""US National Weather Service fallback.

Used when Open-Meteo's free daily quota is exhausted. NWS covers the United
States and needs no API key. Precipitation there is a total over several
hours, so it is converted to an hourly rate before the risk rules see it.
"""
from __future__ import annotations

import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache

from ..geo import LatLon
from .http import ProviderError, session

log = logging.getLogger(__name__)

KMH_TO_MPH = 0.621371
MM_TO_IN = 1 / 25.4
CACHE_SECONDS = 30 * 60
_DURATION = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$")


def duration_hours(spec: str) -> float:
    """ISO-8601 duration (PT1H, PT6H, P1DT2H) as hours."""
    match = _DURATION.match(spec)
    if not match:
        return 1.0
    days, hours, minutes = (int(part) if part else 0 for part in match.groups())
    total = days * 24 + hours + minutes / 60
    return total or 1.0


def _intervals(block: dict | None) -> list[tuple[datetime, datetime, float, float]]:
    found = []
    for item in (block or {}).get("values") or []:
        if item.get("value") is None or "/" not in str(item.get("validTime", "")):
            continue
        start_s, dur = item["validTime"].split("/", 1)
        start = datetime.fromisoformat(start_s).astimezone(timezone.utc)
        hours = duration_hours(dur)
        found.append((start, start + timedelta(hours=hours), float(item["value"]), hours))
    return found


def value_at(intervals, when: datetime, *, rate: bool = False, scale: float = 1.0) -> float:
    """Value in effect at `when`. Rates divide a period total by its length."""
    when = when.astimezone(timezone.utc)
    for start, end, value, hours in intervals:
        if start <= when < end:
            amount = value / hours if rate else value
            return amount * scale
    return 0.0


def _bucket(point: LatLon) -> LatLon:
    """~0.5° cell so a corridor shares one NWS grid fetch."""
    return (math.floor(point[0] * 2) / 2, math.floor(point[1] * 2) / 2)


def _get(url: str) -> dict | None:
    resp = session().get(
        url,
        timeout=settings.HTTP_TIMEOUT_SECONDS,
        headers={"Accept": "application/geo+json", "User-Agent": settings.HTTP_USER_AGENT},
    )
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        raise ProviderError(f"National Weather Service returned HTTP {resp.status_code}")
    return resp.json()


def _grid_props(lat: float, lon: float) -> dict | None:
    point_key = f"nws:point:{lat:.2f},{lon:.2f}"
    grid = cache.get(point_key)
    if grid is None:
        point = _get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
        if not point:
            return None
        props = point.get("properties") or {}
        grid = (props.get("gridId"), props.get("gridX"), props.get("gridY"))
        if not all(grid):
            return None
        cache.set(point_key, grid, CACHE_SECONDS)
    office, x, y = grid
    series_key = f"nws:grid:{office}:{x}:{y}"
    props = cache.get(series_key)
    if props is None:
        props = _get(f"https://api.weather.gov/gridpoints/{office}/{x},{y}")
        if not props:
            return None
        raw = props.get("properties") or {}
        # The full grid document is several MB. Only the series the risk rules read are kept.
        props = {
            key: raw.get(key)
            for key in ("windSpeed", "windGust", "quantitativePrecipitation", "snowfallAmount")
        }
        cache.set(series_key, props, CACHE_SECONDS)
    return props


def _series(props: dict, start: datetime, end: datetime):
    from .weather import HourlySeries

    wind_i = _intervals(props.get("windSpeed"))
    gust_i = _intervals(props.get("windGust"))
    rain_i = _intervals(props.get("quantitativePrecipitation"))
    snow_i = _intervals(props.get("snowfallAmount"))
    count = max(1, int((end - start).total_seconds() // 3600) + 1)
    wind, gust, rain, snow = [], [], [], []
    for step in range(count):
        when = start + timedelta(hours=step)
        wind_mph = value_at(wind_i, when, scale=KMH_TO_MPH)
        snow_in = value_at(snow_i, when, rate=True, scale=MM_TO_IN)
        rain_in = 0.0 if snow_in > 0 else value_at(rain_i, when, rate=True, scale=MM_TO_IN)
        wind.append(wind_mph)
        gust.append(value_at(gust_i, when, scale=KMH_TO_MPH) or wind_mph)
        rain.append(rain_in)
        snow.append(snow_in)
    return HourlySeries(start=start, wind_mph=wind, gust_mph=gust, rain_in=rain, snow_in=snow)


def _blank(start: datetime, end: datetime):
    from .weather import HourlySeries

    count = max(1, int((end - start).total_seconds() // 3600) + 1)
    zeros = [0.0] * count
    return HourlySeries(start=start, wind_mph=zeros, gust_mph=zeros, rain_in=zeros, snow_in=zeros)


def forecasts(points: list[LatLon], start: datetime, end: datetime) -> dict[LatLon, object]:
    """One series per snapped cell. Nearby cells share a forecast."""
    groups: dict[LatLon, list[LatLon]] = {}
    for point in points:
        groups.setdefault(_bucket(point), []).append(point)

    def load(bucket: LatLon):
        lat, lon = bucket[0] + 0.25, bucket[1] + 0.25
        try:
            props = _grid_props(lat, lon)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"National Weather Service is unreachable: {exc.__class__.__name__}") from exc
        if props is None:
            return _blank(start, end)
        return _series(props, start, end)

    buckets = list(groups)
    with ThreadPoolExecutor(max_workers=4) as pool:
        loaded = list(pool.map(load, buckets))

    result = {}
    for bucket, series in zip(buckets, loaded):
        for point in groups[bucket]:
            result[point] = series
    if result and all(max(series.wind_mph) == 0 and max(series.rain_in) == 0 for series in loaded):
        log.info("NWS returned no coverage for %d cells", len(points))
    log.info("NWS: %d cells from %d grid forecasts", len(points), len(buckets))
    return result
