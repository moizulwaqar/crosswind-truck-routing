"""Trip planning pipeline.

    routes ─► checkpoints every N miles (with truck ETAs)
           ─► weather forecast at each checkpoint *at its ETA*
           ─► risk level per checkpoint (thresholds + load rules)
           ─► miles per risk level per route
           ─► ranking + recommendation
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..geo import Checkpoint, LatLon, RouteGeometry, sample_checkpoints, simplify
from ..providers import routing, weather
from ..providers.http import ProviderError
from ..recommend import RouteScore, rank
from ..risk import RiskLevel, assess
from .corridor import build_corridor

log = logging.getLogger(__name__)

ROUTE_NAMES = ("Route A", "Route B", "Route C")
TIMELINE_HOURS = 48  # matches the heatmap slider range


def _r(x: float, nd: int = 5) -> float:
    return round(x, nd)


def _risk_segments(route: RouteGeometry, checkpoints: list[Checkpoint], levels: list[int]) -> list[dict]:
    """Split the route into stretches coloured by the owning checkpoint's level."""
    spans: list[list[float]] = []  # [start_mile, end_mile, level]
    for i, (cp, level) in enumerate(zip(checkpoints, levels)):
        start = 0.0 if i == 0 else (checkpoints[i - 1].mile + cp.mile) / 2
        end = route.distance_miles if i == len(checkpoints) - 1 else (cp.mile + checkpoints[i + 1].mile) / 2
        if end <= start:
            continue
        if spans and spans[-1][2] == level:
            spans[-1][1] = end
        else:
            spans.append([start, end, level])
    return [
        {
            "level": int(level),
            "from_mile": _r(start, 1),
            "to_mile": _r(end, 1),
            "coords": [[_r(lat), _r(lon)] for lat, lon in simplify(route.slice(start, end))],
        }
        for start, end, level in spans
    ]


def _timeline(route: RouteGeometry, departure: datetime) -> list[list[float]]:
    """Truck position for each whole hour after departure (for the forecast slider)."""
    points = []
    for h in range(TIMELINE_HOURS + 1):
        lat, lon = route.locate_at_time(h * 3600)
        points.append([_r(lat), _r(lon)])
    return points


def plan_trip(origin: LatLon, destination: LatLon, departure: datetime, load_lb: float, interval_miles: int) -> dict:
    routes = routing.get_routes(origin, destination)

    per_route_cps = [sample_checkpoints(r, interval_miles, departure) for r in routes]
    window_end = departure + timedelta(seconds=max(r.duration_seconds for r in routes) + 3600)
    all_points = [(cp.lat, cp.lon) for cps in per_route_cps for cp in cps]
    forecasts = weather.get_forecasts(all_points, departure, window_end)

    scores: list[RouteScore] = []
    payloads: list[dict] = []
    for name, route, cps in zip(ROUTE_NAMES, routes, per_route_cps):
        miles_by_level = [0.0] * len(RiskLevel)
        cp_payload, levels = [], []
        worst: dict | None = None
        for cp in cps:
            series = forecasts.get(weather.snap((cp.lat, cp.lon)))
            cond = series.at(cp.eta) if series else None
            if cond is None:
                raise ProviderError(
                    "Weather forecast does not cover the whole trip. Choose an earlier departure time.",
                    status=422,
                )
            a = assess(cond["wind_mph"], cond["rain_in_hr"], cond["snow_in_hr"], load_lb)
            miles_by_level[a.level] += cp.covers_miles
            levels.append(int(a.level))
            item = {
                "index": cp.index,
                "mile": _r(cp.mile, 1),
                "lat": _r(cp.lat),
                "lon": _r(cp.lon),
                "eta": cp.eta.isoformat(),
                "covers_miles": _r(cp.covers_miles, 2),
                "wind_mph": _r(cond["wind_mph"], 1),
                "gust_mph": _r(cond["gust_mph"], 1),
                "rain_in_hr": _r(cond["rain_in_hr"], 3),
                "snow_in_hr": _r(cond["snow_in_hr"], 3),
                "forecast_hour": cond["forecast_hour"],
                **a.as_dict(),
            }
            cp_payload.append(item)
            if worst is None or item["level"] > worst["level"]:
                worst = item

        route_id = name[-1].lower()
        score = RouteScore(route_id, name, route.duration_seconds, miles_by_level)
        scores.append(score)
        payloads.append(
            {
                "id": route_id,
                "name": name,
                "summary": route.summary,
                "source": route.source,
                "distance_miles": _r(route.distance_miles, 1),
                "duration_seconds": round(route.duration_seconds),
                "departure": departure.isoformat(),
                "arrival": (departure + timedelta(seconds=route.duration_seconds)).isoformat(),
                "coords": [[_r(lat), _r(lon)] for lat, lon in simplify(route.coords)],
                "risk_segments": _risk_segments(route, cps, levels),
                "checkpoints": cp_payload,
                "timeline": _timeline(route, departure),
                "stats": {
                    "miles_by_level": [_r(m, 1) for m in miles_by_level],
                    "average_risk": _r(score.average_risk, 3),
                    "max_level": max(levels),
                    "worst_checkpoint": worst["index"] if worst else None,
                    "checkpoint_count": len(cps),
                },
            }
        )

    ordered, reason = rank(scores)
    rank_of = {s.route_id: i + 1 for i, s in enumerate(ordered)}
    for p in payloads:
        p["rank"] = rank_of[p["id"]]
        p["recommended"] = p["rank"] == 1

    return {
        "origin": {"lat": origin[0], "lon": origin[1]},
        "destination": {"lat": destination[0], "lon": destination[1]},
        "departure": departure.isoformat(),
        "load_lb": load_lb,
        "interval_miles": interval_miles,
        "recommended_route_id": ordered[0].route_id,
        "recommendation_reason": reason,
        "routes": payloads,
        "corridor": build_corridor([r.coords for r in routes]),
        "weather_notice": weather.take_notice(),
    }
