"""Weather heatmap along the trip corridor.

The corridor is a regular lat/lon grid restricted to cells within
CORRIDOR_MILES of any route. Cell size grows with trip length so the number
of forecast locations stays bounded (fast API calls, light payload) whatever
the distance. The browser receives all 49 hourly frames at once, so moving
the 0–48 h slider never triggers a network request.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from ..geo import LatLon, haversine_miles
from ..providers import weather
from ..risk import assess

CORRIDOR_MILES = 30.0
# Kept small so the 48-hour fetch fits a 512 MB host. A larger grid
# (Dallas–Chicago was ~420 cells) made that host drop the connection.
MAX_CELLS = 120
STEP_CANDIDATES_DEG = (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.65, 0.8, 1.0, 1.25, 1.5)
HEATMAP_HOURS = 48
MILES_PER_DEG_LAT = 69.0


def _cells_for_step(paths: list[list[LatLon]], step: float, lon_step: float) -> set[tuple[int, int]]:
    radius_i = math.ceil((CORRIDOR_MILES / MILES_PER_DEG_LAT) / step)
    cells: set[tuple[int, int]] = set()
    for path in paths:
        last: LatLon | None = None
        for p in path:
            # Only stamp a point every ~half cell; dense OSRM geometry would be wasteful.
            if last is not None and haversine_miles(last, p) < step * MILES_PER_DEG_LAT / 2:
                continue
            last = p
            ci, cj = math.floor(p[0] / step), math.floor(p[1] / lon_step)
            for di in range(-radius_i, radius_i + 1):
                for dj in range(-radius_i, radius_i + 1):
                    if di * di + dj * dj <= radius_i * radius_i:
                        cells.add((ci + di, cj + dj))
    return cells


def build_corridor(paths: list[list[LatLon]]) -> dict:
    all_pts = [p for path in paths for p in path]
    mean_lat = sum(p[0] for p in all_pts) / len(all_pts)
    cos_lat = max(math.cos(math.radians(mean_lat)), 0.2)

    for step in STEP_CANDIDATES_DEG:
        lon_step = step / cos_lat  # roughly square cells on the ground
        cells = _cells_for_step(paths, step, lon_step)
        if len(cells) <= MAX_CELLS:
            break

    centers = sorted(((i + 0.5) * step, (j + 0.5) * lon_step) for i, j in cells)
    return {
        "lat_step": round(step, 5),
        "lon_step": round(lon_step, 5),
        "cells": [[round(lat, 4), round(lon, 4)] for lat, lon in centers],
    }


def corridor_heatmap(cells: list[LatLon], start: datetime, load_lb: float) -> dict:
    """Hourly wind / rain / snow / risk for each cell, hours 0…48 from `start`."""
    start = start.replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=HEATMAP_HOURS)
    forecasts = weather.get_forecasts(cells, start, end)

    risk, wind, rain, snow = [], [], [], []
    for cell in cells:
        series = forecasts.get(weather.snap(cell))
        r_row, w_row, ra_row, s_row = [], [], [], []
        for h in range(HEATMAP_HOURS + 1):
            cond = series.at(start + timedelta(hours=h)) if series else None
            if cond is None:
                r_row.append(None)
                w_row.append(None)
                ra_row.append(None)
                s_row.append(None)
                continue
            a = assess(cond["wind_mph"], cond["rain_in_hr"], cond["snow_in_hr"], load_lb)
            r_row.append(int(a.level))
            w_row.append(round(cond["wind_mph"], 1))
            ra_row.append(round(cond["rain_in_hr"], 3))
            s_row.append(round(cond["snow_in_hr"], 3))
        risk.append(r_row)
        wind.append(w_row)
        rain.append(ra_row)
        snow.append(s_row)

    return {
        "start": start.isoformat(),
        "hours": HEATMAP_HOURS,
        "cells": [[c[0], c[1]] for c in cells],
        "risk": risk,
        "wind_mph": wind,
        "rain_in_hr": rain,
        "snow_in_hr": snow,
        "weather_notice": weather.take_notice(),
    }
