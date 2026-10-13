from datetime import datetime, timedelta, timezone

import pytest

from trips.geo import METERS_PER_MILE, RouteGeometry, haversine_miles, sample_checkpoints, simplify

DEP = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def straight_route(miles: float, mph: float, max_speed: float = 65) -> RouteGeometry:
    """A due-north route made of 1-mile segments driven at `mph` by the router."""
    n = int(miles)
    lat_per_mile = 1 / 69.0
    coords = [(30 + i * lat_per_mile, -97.0) for i in range(n + 1)]
    seg_m = [haversine_miles(coords[i], coords[i + 1]) * METERS_PER_MILE for i in range(n)]
    seg_s = [m / METERS_PER_MILE / mph * 3600 for m in seg_m]
    return RouteGeometry.from_segments(coords, seg_m, seg_s, max_speed_mph=max_speed)


def test_haversine_known_distance():
    # Dallas → Chicago is ~803 miles great-circle
    assert haversine_miles((32.7767, -96.7970), (41.8781, -87.6298)) == pytest.approx(803, abs=5)


def test_truck_speed_cap_slows_fast_segments():
    fast = straight_route(100, mph=80, max_speed=65)
    assert fast.duration_seconds == pytest.approx(fast.distance_miles / 65 * 3600, rel=1e-6)
    slow = straight_route(100, mph=50, max_speed=65)  # already below the cap: unchanged
    assert slow.duration_seconds == pytest.approx(slow.distance_miles / 50 * 3600, rel=1e-6)


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_checkpoints_every_interval_plus_destination(interval):
    route = straight_route(120, mph=60)
    cps = sample_checkpoints(route, interval, DEP)
    miles = [cp.mile for cp in cps]
    assert miles[0] == 0
    assert miles[-1] == pytest.approx(route.distance_miles)
    for a, b in zip(miles[:-2], miles[1:-1]):
        assert b - a == pytest.approx(interval)
    # coverage partitions the route exactly
    assert sum(cp.covers_miles for cp in cps) == pytest.approx(route.distance_miles)


def test_checkpoint_eta_matches_drive_time():
    route = straight_route(100, mph=50)
    cps = sample_checkpoints(route, 25, DEP)
    cp = next(c for c in cps if c.mile == 50)
    assert cp.eta - DEP == pytest.approx(timedelta(hours=1), abs=timedelta(seconds=30))
    assert all(a.eta <= b.eta for a, b in zip(cps, cps[1:]))


def test_no_tiny_last_gap():
    route = straight_route(50.5 * 69 / 69, mph=60)  # 50 one-mile segments
    cps = sample_checkpoints(route, 25, DEP)
    assert [round(c.mile) for c in cps] == [0, 25, 50]


def test_locate_at_time_and_slice():
    route = straight_route(100, mph=50)
    lat, _ = route.locate_at_time(3600)
    assert (lat - 30) * 69 == pytest.approx(50, abs=0.5)
    piece = route.slice(10, 20)
    assert haversine_miles(piece[0], piece[-1]) == pytest.approx(10, abs=0.1)


def test_simplify_keeps_endpoints_and_shrinks_straight_line():
    route = straight_route(100, mph=60)
    s = simplify(route.coords)
    assert s[0] == route.coords[0] and s[-1] == route.coords[-1]
    assert len(s) == 2
