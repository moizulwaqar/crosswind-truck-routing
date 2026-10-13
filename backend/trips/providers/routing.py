"""Route options from OSRM.

OSRM's `alternatives` often returns only 1–2 routes. To reliably offer three
genuinely different options we add "via-point" alternatives: route through a
point offset perpendicular to the origin→destination line, then keep only
candidates that (a) are not mostly the same roads as an existing option and
(b) are not absurd detours.
"""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.cache import cache

from ..geo import LatLon, RouteGeometry, haversine_miles, overlap_fraction
from .http import ProviderError, get_json

log = logging.getLogger(__name__)

TARGET_ROUTES = 3
MAX_OVERLAP = 0.85  # reject a candidate sharing >85% of its length with a kept route
MAX_DETOUR_RATIO = 1.6  # reject a candidate >60% slower than the fastest
VIA_OFFSETS = (0.18, -0.18, 0.35, -0.35)  # fraction of straight-line distance, + = left


def _osrm_url(points: list[LatLon]) -> str:
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    return f"{settings.OSRM_BASE_URL.rstrip('/')}/route/v1/driving/{coords}"


def _parse_osrm_route(raw: dict, source: str) -> RouteGeometry:
    coords = [(lat, lon) for lon, lat in raw["geometry"]["coordinates"]]
    seg_m: list[float] = []
    seg_s: list[float] = []
    summaries: list[str] = []
    for leg in raw.get("legs", []):
        ann = leg.get("annotation") or {}
        seg_m.extend(ann.get("distance", []))
        seg_s.extend(ann.get("duration", []))
        if leg.get("summary"):
            summaries.append(leg["summary"])
    # Leg summaries for a via route repeat roads; keep order, drop duplicates.
    names: list[str] = []
    for s in summaries:
        for name in (n.strip() for n in s.split(",")):
            if name and name not in names:
                names.append(name)
    return RouteGeometry.from_segments(
        coords,
        seg_m,
        seg_s,
        max_speed_mph=settings.TRUCK_MAX_SPEED_MPH,
        total_seconds=raw.get("duration"),
        summary=", ".join(names[:3]),
        source=source,
    )


def _fetch(points: list[LatLon], alternatives: int, source: str) -> list[RouteGeometry]:
    params = {
        "overview": "full",
        "geometries": "geojson",
        "annotations": "distance,duration",
        "steps": "true",  # required for OSRM to fill in leg summaries (road names)
        "alternatives": str(alternatives) if alternatives else "false",
    }
    data = get_json(_osrm_url(points), params=params, service="Routing service (OSRM)")
    code = data.get("code")
    if code == "NoRoute" or code == "NoSegment":
        return []
    if code != "Ok":
        raise ProviderError(f"Routing service error: {data.get('message') or code}")
    return [_parse_osrm_route(r, source) for r in data.get("routes", [])]


def _via_point(origin: LatLon, dest: LatLon, offset_fraction: float) -> LatLon:
    """Point at the midpoint, pushed sideways by a fraction of the trip length."""
    mid_lat = (origin[0] + dest[0]) / 2
    mid_lon = (origin[1] + dest[1]) / 2
    cos_lat = math.cos(math.radians(mid_lat)) or 1e-6
    dx = (dest[1] - origin[1]) * cos_lat  # east, in "latitude-degree" units
    dy = dest[0] - origin[0]  # north
    length = math.hypot(dx, dy) or 1e-6
    px, py = -dy / length, dx / length  # unit vector, 90° to the left
    shift = offset_fraction * length
    return (mid_lat + py * shift, mid_lon + px * shift / cos_lat)


def _is_distinct(candidate: RouteGeometry, kept: list[RouteGeometry]) -> bool:
    return all(overlap_fraction(k, candidate) < MAX_OVERLAP for k in kept)


def get_routes(origin: LatLon, dest: LatLon) -> list[RouteGeometry]:
    key = "routes:%.4f,%.4f:%.4f,%.4f" % (*origin, *dest)
    cached = cache.get(key)
    if cached is not None:
        return cached

    primary = _fetch([origin, dest], alternatives=TARGET_ROUTES, source="osrm")
    if not primary:
        raise ProviderError("No drivable route found between these locations.", status=422)
    primary.sort(key=lambda r: r.duration_seconds)
    fastest = primary[0].duration_seconds

    kept: list[RouteGeometry] = []
    for r in primary:
        if len(kept) < TARGET_ROUTES and r.duration_seconds <= fastest * MAX_DETOUR_RATIO and _is_distinct(r, kept):
            kept.append(r)

    if len(kept) < TARGET_ROUTES and haversine_miles(origin, dest) > 15:
        vias = [_via_point(origin, dest, f) for f in VIA_OFFSETS]
        # Fetch in parallel; the order of VIA_OFFSETS still decides preference.
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda v: _safe_fetch([origin, v, dest]), vias))
        for routes in results:
            for r in routes:
                if len(kept) >= TARGET_ROUTES:
                    break
                if r.duration_seconds <= fastest * MAX_DETOUR_RATIO and _is_distinct(r, kept):
                    kept.append(r)

    kept.sort(key=lambda r: r.duration_seconds)
    cache.set(key, kept, 60 * 60)
    return kept


def _safe_fetch(points: list[LatLon]) -> list[RouteGeometry]:
    try:
        return _fetch(points, alternatives=0, source="osrm-via")
    except ProviderError as exc:  # an alternative failing shouldn't sink the request
        log.warning("Via-point route failed: %s", exc)
        return []
