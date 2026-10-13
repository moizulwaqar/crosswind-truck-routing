"""Deterministic stand-ins for OSRM, Open-Meteo and Photon.

Enabled with FAKE_PROVIDERS=1. Used by the test-suite and for an offline demo
that always contains a storm (so every risk level can be shown on camera).
They answer with the same JSON shapes as the real services, so everything
downstream of `get_json` runs exactly as in production.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ..geo import METERS_PER_MILE, haversine_miles

CITIES = [
    ("Dallas, Texas, United States", 32.7767, -96.7970),
    ("Chicago, Illinois, United States", 41.8781, -87.6298),
    ("Denver, Colorado, United States", 39.7392, -104.9903),
    ("Kansas City, Missouri, United States", 39.0997, -94.5786),
    ("Oklahoma City, Oklahoma, United States", 35.4676, -97.5164),
    ("Memphis, Tennessee, United States", 35.1495, -90.0490),
    ("Albuquerque, New Mexico, United States", 35.0844, -106.6504),
    ("Los Angeles, California, United States", 34.0522, -118.2437),
    ("Atlanta, Georgia, United States", 33.7490, -84.3880),
    ("Houston, Texas, United States", 29.7604, -95.3698),
]

# A storm over the Ozarks drifting north-east (it sits across the direct
# Dallas → Chicago corridor), plus a snow band over the Colorado Rockies —
# enough to exercise every risk level.
STORM_ORIGIN = (35.7, -93.4)
STORM_DRIFT_DEG_PER_HOUR = (0.05, 0.12)
STORM_RADIUS_MILES = 110.0


def _photon(params: dict) -> dict:
    q = str(params.get("q", "")).lower()
    feats = []
    for label, lat, lon in CITIES:
        if q in label.lower():
            name, state, country = [p.strip() for p in label.split(",")]
            feats.append(
                {
                    "geometry": {"coordinates": [lon, lat]},
                    "properties": {"name": name, "state": state, "country": country},
                }
            )
    return {"features": feats[: int(params.get("limit", 6))]}


def _curve(a, b, bend: float, n: int):
    """Points along a gently bowed path from a to b (bend = fraction of length)."""
    pts = []
    for i in range(n + 1):
        t = i / n
        lat = a[0] + (b[0] - a[0]) * t
        lon = a[1] + (b[1] - a[1]) * t
        off = bend * math.sin(math.pi * t)
        dlat, dlon = b[0] - a[0], b[1] - a[1]
        pts.append((lat + (-dlon) * off * 0.6, lon + dlat * off))
    return pts


def _osrm_route(waypoints, bend: float, mph: float) -> dict:
    coords = []
    for a, b in zip(waypoints, waypoints[1:]):
        n = max(10, int(haversine_miles(a, b)))  # ~1 vertex per mile
        seg = _curve(a, b, bend, n)
        coords.extend(seg if not coords else seg[1:])
    dist_m = [haversine_miles(coords[i], coords[i + 1]) * METERS_PER_MILE for i in range(len(coords) - 1)]
    dur = [d / (mph * METERS_PER_MILE / 3600) for d in dist_m]
    return {
        "geometry": {"coordinates": [[lon, lat] for lat, lon in coords]},
        "legs": [{"annotation": {"distance": dist_m, "duration": dur}, "summary": f"I {35 + int(bend * 100) % 50}, US {60 + int(mph)}"}],
        "distance": sum(dist_m),
        "duration": sum(dur),
    }


def _osrm(url: str, params: dict) -> dict:
    coord_str = url.rsplit("/", 1)[-1]
    pts = [(float(c.split(",")[1]), float(c.split(",")[0])) for c in coord_str.split(";")]
    if len(pts) == 2 and params.get("alternatives") not in (None, "false"):
        routes = [_osrm_route(pts, 0.0, 70), _osrm_route(pts, 0.12, 72)]  # only 2: forces via fallback
    else:
        routes = [_osrm_route(pts, 0.03, 68)]
    return {"code": "Ok", "routes": routes}


def _weather_at(lat: float, lon: float, hours_from_now: float) -> tuple[float, float, float, float]:
    clat = STORM_ORIGIN[0] + STORM_DRIFT_DEG_PER_HOUR[0] * hours_from_now
    clon = STORM_ORIGIN[1] + STORM_DRIFT_DEG_PER_HOUR[1] * hours_from_now
    d = haversine_miles((lat, lon), (clat, clon))
    storm = math.exp(-((d / STORM_RADIUS_MILES) ** 2))
    breeze = 9 + 5 * math.sin(lat * 3.1 + lon * 1.7 + hours_from_now / 5)
    wind = breeze + 52 * storm
    rain = 0.85 * storm**1.5 + 0.02 * max(0.0, math.sin(lon + hours_from_now / 3))
    snow = 0.0
    if lat > 38.5 and lon < -104.0:
        snow = 1.4 * math.exp(-(((lon + 106.0) / 1.5) ** 2)) * (0.6 + 0.4 * math.sin(hours_from_now / 6))
    return wind, wind * 1.35, rain, snow


def _open_meteo(params: dict):
    lats = [float(x) for x in str(params["latitude"]).split(",")]
    lons = [float(x) for x in str(params["longitude"]).split(",")]
    start = datetime.strptime(params["start_hour"], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    end = datetime.strptime(params["end_hour"], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    n = int((end - start).total_seconds() // 3600) + 1
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    out = []
    for lat, lon in zip(lats, lons):
        times, w, g, r, s = [], [], [], [], []
        for h in range(n):
            ts = start.timestamp() + h * 3600
            wind, gust, rain, snow = _weather_at(lat, lon, (ts - now.timestamp()) / 3600)
            times.append(int(ts))
            w.append(round(wind, 1))
            g.append(round(gust, 1))
            r.append(round(rain * 0.8, 3))
            s.append(round(snow, 3))
        showers = [round(x / 4, 3) for x in r]  # rain + showers = full rate
        out.append(
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": {"time": times, "wind_speed_10m": w, "wind_gusts_10m": g, "rain": r, "showers": showers, "snowfall": s},
            }
        )
    return out[0] if len(out) == 1 else out


def dispatch(url: str, params: dict | None):
    params = params or {}
    if "photon" in url:
        return _photon(params)
    if "/route/v1/" in url:
        return _osrm(url, params)
    return _open_meteo(params)
