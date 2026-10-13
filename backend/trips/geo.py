"""Geometry helpers: distances, polyline interpolation and checkpoint sampling."""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344

LatLon = tuple[float, float]


def haversine_miles(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(h)))


def cumulative(values: list[float]) -> list[float]:
    out, total = [0.0], 0.0
    for v in values:
        total += v
        out.append(total)
    return out


@dataclass
class RouteGeometry:
    """A routed path with per-vertex cumulative distance and truck travel time."""

    coords: list[LatLon]
    cum_miles: list[float]
    cum_seconds: list[float]
    summary: str = ""
    source: str = "osrm"
    extra: dict = field(default_factory=dict)

    @property
    def distance_miles(self) -> float:
        return self.cum_miles[-1]

    @property
    def duration_seconds(self) -> float:
        return self.cum_seconds[-1]

    @classmethod
    def from_segments(
        cls,
        coords: list[LatLon],
        seg_meters: list[float] | None,
        seg_seconds: list[float] | None,
        max_speed_mph: float,
        total_seconds: float | None = None,
        **kwargs,
    ) -> "RouteGeometry":
        """Build cumulative arrays, applying a truck speed cap per segment.

        If the router's per-segment annotations don't line up with the
        geometry, fall back to haversine distances and spread the router's
        total duration proportionally to distance.
        """
        n = len(coords) - 1
        if seg_meters and seg_seconds and len(seg_meters) == n and len(seg_seconds) == n:
            miles = [m / METERS_PER_MILE for m in seg_meters]
            secs = list(seg_seconds)
        else:
            miles = [haversine_miles(coords[i], coords[i + 1]) for i in range(n)]
            total_mi = sum(miles) or 1.0
            total_s = total_seconds or (total_mi / max_speed_mph * 3600)
            secs = [total_s * m / total_mi for m in miles]

        max_mps = max_speed_mph / 3600.0  # miles per second
        truck_secs = [max(s, mi / max_mps) for s, mi in zip(secs, miles)]
        return cls(coords=coords, cum_miles=cumulative(miles), cum_seconds=cumulative(truck_secs), **kwargs)

    def locate(self, mile: float) -> tuple[LatLon, float]:
        """Point and elapsed seconds at a given distance along the route."""
        mile = min(max(mile, 0.0), self.distance_miles)
        i = bisect.bisect_right(self.cum_miles, mile) - 1
        i = min(max(i, 0), len(self.coords) - 2)
        seg = self.cum_miles[i + 1] - self.cum_miles[i]
        t = 0.0 if seg <= 0 else (mile - self.cum_miles[i]) / seg
        (lat1, lon1), (lat2, lon2) = self.coords[i], self.coords[i + 1]
        point = (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)
        seconds = self.cum_seconds[i] + (self.cum_seconds[i + 1] - self.cum_seconds[i]) * t
        return point, seconds

    def slice(self, start_mile: float, end_mile: float) -> list[LatLon]:
        """Sub-polyline between two distances along the route (inclusive ends)."""
        start_pt, _ = self.locate(start_mile)
        end_pt, _ = self.locate(end_mile)
        i = bisect.bisect_right(self.cum_miles, start_mile)
        j = bisect.bisect_left(self.cum_miles, end_mile)
        return [start_pt, *self.coords[i:j], end_pt]

    def locate_at_time(self, elapsed_seconds: float) -> LatLon:
        """Where the truck is after `elapsed_seconds` of driving."""
        s = min(max(elapsed_seconds, 0.0), self.duration_seconds)
        i = bisect.bisect_right(self.cum_seconds, s) - 1
        i = min(max(i, 0), len(self.coords) - 2)
        seg = self.cum_seconds[i + 1] - self.cum_seconds[i]
        t = 0.0 if seg <= 0 else (s - self.cum_seconds[i]) / seg
        (lat1, lon1), (lat2, lon2) = self.coords[i], self.coords[i + 1]
        return (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)


@dataclass
class Checkpoint:
    index: int
    mile: float
    lat: float
    lon: float
    eta: datetime
    # Miles of the route this checkpoint "owns": half the gap to each neighbour.
    covers_miles: float = 0.0


def sample_checkpoints(route: RouteGeometry, interval_miles: float, departure: datetime) -> list[Checkpoint]:
    """Checkpoints at 0, interval, 2·interval, … plus the destination.

    Each checkpoint represents the stretch of road nearest to it, so the
    `covers_miles` of all checkpoints sums exactly to the route length.
    """
    total = route.distance_miles
    miles: list[float] = []
    m = 0.0
    while m < total - 1e-6:
        miles.append(m)
        m += interval_miles
    # Always include the destination; drop a sample that would sit < 1 mile before it.
    if miles and total - miles[-1] < 1.0 and len(miles) > 1:
        miles.pop()
    miles.append(total)

    checkpoints: list[Checkpoint] = []
    for i, mile in enumerate(miles):
        (lat, lon), secs = route.locate(mile)
        checkpoints.append(Checkpoint(i, mile, lat, lon, departure + timedelta(seconds=secs)))

    for i, cp in enumerate(checkpoints):
        left = (cp.mile - checkpoints[i - 1].mile) / 2 if i > 0 else 0.0
        right = (checkpoints[i + 1].mile - cp.mile) / 2 if i < len(checkpoints) - 1 else 0.0
        cp.covers_miles = left + right
    return checkpoints


def simplify(coords: list[LatLon], tolerance_deg: float = 0.0005) -> list[LatLon]:
    """Douglas–Peucker (iterative) to shrink polylines sent to the browser."""
    if len(coords) < 3:
        return list(coords)
    keep = [False] * len(coords)
    keep[0] = keep[-1] = True
    stack = [(0, len(coords) - 1)]
    tol2 = tolerance_deg**2
    while stack:
        start, end = stack.pop()
        (y1, x1), (y2, x2) = coords[start], coords[end]
        dx, dy = x2 - x1, y2 - y1
        norm = dx * dx + dy * dy
        best_i, best_d = -1, -1.0
        for i in range(start + 1, end):
            y, x = coords[i]
            if norm == 0:
                d = (x - x1) ** 2 + (y - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / norm))
                d = (x - (x1 + t * dx)) ** 2 + (y - (y1 + t * dy)) ** 2
            if d > best_d:
                best_i, best_d = i, d
        if best_d > tol2:
            keep[best_i] = True
            stack.append((start, best_i))
            stack.append((best_i, end))
    return [c for c, k in zip(coords, keep) if k]


def overlap_fraction(a: RouteGeometry, b: RouteGeometry, cell_deg: float = 0.02) -> float:
    """Share of route `b`'s length that runs within ~1–2 km of route `a`."""

    def cell(p: LatLon) -> tuple[int, int]:
        return (math.floor(p[0] / cell_deg), math.floor(p[1] / cell_deg))

    a_cells: set[tuple[int, int]] = set()
    for p in a.coords:
        ci, cj = cell(p)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                a_cells.add((ci + di, cj + dj))

    shared = 0.0
    for i in range(len(b.coords) - 1):
        if cell(b.coords[i]) in a_cells:
            shared += b.cum_miles[i + 1] - b.cum_miles[i]
    return shared / b.distance_miles if b.distance_miles else 1.0
