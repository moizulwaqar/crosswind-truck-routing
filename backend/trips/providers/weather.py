"""Hourly forecasts from Open-Meteo (free, no key, many locations per call).

Units are requested directly from the API so no conversion is needed:
wind in mph, rain and snowfall in inches. Open-Meteo hourly precipitation
values are the sum over the *preceding* hour, i.e. already a per-hour rate.
"""
from __future__ import annotations

import logging
import math
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache

from ..geo import LatLon
from .http import ProviderError, get_json

log = logging.getLogger(__name__)
_notice: ContextVar[str] = ContextVar("weather_notice", default="")

NWS_NOTICE = (
    "Open-Meteo's free daily limit is used up for this network. "
    "This forecast is from the US National Weather Service instead."
)


def take_notice() -> str:
    """Notice set by the most recent forecast call, then cleared."""
    note = _notice.get()
    _notice.set("")
    return note


def _over_quota(exc: ProviderError) -> bool:
    message = str(exc).lower()
    return "429" in message or "limit" in message or "too many" in message

GRID_DEG = 0.05  # snap points to ~5 km cells: matches model resolution, dedupes requests
BATCH_SIZE = 40  # one batch in memory at a time; 128 MiB host cannot hold several at once
CACHE_SECONDS = 15 * 60
HOURLY_VARS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"


def snap(point: LatLon) -> LatLon:
    return (round(round(point[0] / GRID_DEG) * GRID_DEG, 4), round(round(point[1] / GRID_DEG) * GRID_DEG, 4))


@dataclass
class HourlySeries:
    """Hourly forecast for one location, starting at `start` (UTC, on the hour)."""

    start: datetime
    wind_mph: list[float]
    gust_mph: list[float]
    rain_in: list[float]  # rain + convective showers, inches in the preceding hour
    snow_in: list[float]  # snowfall depth, inches in the preceding hour

    def __len__(self) -> int:
        return len(self.wind_mph)

    def at(self, when: datetime) -> dict | None:
        """Conditions at an arbitrary instant.

        Wind is instantaneous → nearest hour. Precipitation is an accumulation
        over the hour *ending* at each timestamp → use the hour that contains
        `when` (round up).
        """
        hours = (when - self.start).total_seconds() / 3600.0
        if hours < -0.5 or hours > len(self) - 0.5:
            return None
        last = len(self) - 1
        wi = min(max(int(round(hours)), 0), last)
        pi = min(max(math.ceil(hours - 1e-9), 0), last)
        return {
            "wind_mph": self.wind_mph[wi],
            "gust_mph": self.gust_mph[wi],
            "rain_in_hr": self.rain_in[pi],
            "snow_in_hr": self.snow_in[pi],
            "forecast_hour": (self.start + timedelta(hours=pi)).isoformat(),
        }


def _hour_floor(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _num(values: list, i: int) -> float:
    v = values[i] if i < len(values) else None
    return float(v) if v is not None else 0.0


def _parse(loc: dict, start: datetime) -> HourlySeries:
    h = loc.get("hourly") or {}
    times = h.get("time") or []
    n = len(times)
    first = datetime.fromtimestamp(times[0], tz=timezone.utc) if times else start
    rain = h.get("rain", [])
    showers = h.get("showers", [])
    return HourlySeries(
        start=first,
        wind_mph=[_num(h.get("wind_speed_10m", []), i) for i in range(n)],
        gust_mph=[_num(h.get("wind_gusts_10m", []), i) for i in range(n)],
        rain_in=[_num(rain, i) + _num(showers, i) for i in range(n)],
        snow_in=[_num(h.get("snowfall", []), i) for i in range(n)],
    )


def _fetch_batch(points: list[LatLon], start: datetime, end: datetime) -> list[HourlySeries]:
    params = {
        "latitude": ",".join(f"{p[0]:.4f}" for p in points),
        "longitude": ",".join(f"{p[1]:.4f}" for p in points),
        "hourly": HOURLY_VARS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        "timeformat": "unixtime",
        "start_hour": start.strftime("%Y-%m-%dT%H:%M"),
        "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
    }
    data = get_json(settings.OPEN_METEO_URL, params=params, service="Weather service (Open-Meteo)")
    if isinstance(data, dict):  # single location → object, many → list
        if data.get("error"):
            raise ProviderError(f"Weather service error: {data.get('reason')}")
        data = [data]
    if len(data) != len(points):
        raise ProviderError("Weather service returned an unexpected number of locations")
    return [_parse(loc, start) for loc in data]


def get_forecasts(points: list[LatLon], start: datetime, end: datetime) -> dict[LatLon, HourlySeries]:
    """Forecast for every point (keyed by its snapped grid cell) over [start, end]."""
    _notice.set("")
    start, end = _hour_floor(start), _hour_floor(end) + timedelta(hours=1)
    try:
        return _open_meteo(points, start, end)
    except ProviderError as exc:
        if not _over_quota(exc):
            raise
        log.warning("Open-Meteo quota exceeded, using National Weather Service")
        _notice.set(NWS_NOTICE)
        from . import nws

        cells = list(dict.fromkeys(snap(p) for p in points))
        return nws.forecasts(cells, start, end)


def _open_meteo(points: list[LatLon], start: datetime, end: datetime) -> dict[LatLon, HourlySeries]:
    window = f"{start:%Y%m%d%H}-{end:%Y%m%d%H}"

    cells = list(dict.fromkeys(snap(p) for p in points))
    result: dict[LatLon, HourlySeries] = {}
    missing: list[LatLon] = []
    cached = cache.get_many([f"wx:{c[0]},{c[1]}:{window}" for c in cells])
    for c in cells:
        hit = cached.get(f"wx:{c[0]},{c[1]}:{window}")
        if hit is not None:
            result[c] = hit
        else:
            missing.append(c)

    if missing:
        batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
        # Sequential on purpose: parallel batches each hold a full parsed forecast.
        fetched = [_fetch_batch(b, start, end) for b in batches]
        to_cache = {}
        for batch, series_list in zip(batches, fetched):
            for c, series in zip(batch, series_list):
                result[c] = series
                to_cache[f"wx:{c[0]},{c[1]}:{window}"] = series
        cache.set_many(to_cache, CACHE_SECONDS)
        log.info("Weather: %d cells fetched in %d request(s), %d from cache", len(missing), len(batches), len(cells) - len(missing))
    return result
