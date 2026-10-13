# Crosswind: weather-aware truck routing

A React + Django app that gives a truck driver three route options and recommends the safest one, using hourly forecasts for wind, rain and snow **at the time the truck will actually reach each point**, and the risk and load rules from the brief.

**Live app:** _add your hosted URL here_
**Walkthrough:** _add your Loom link here_

## What it does

1. The driver enters origin, destination, departure time, load weight, and a checkpoint spacing of 10, 25 or 50 miles.
2. The backend gets **three distinct routes** from OSRM.
3. Each route is sampled every N miles. Each checkpoint gets a **truck ETA** (router segment times, capped at 65 mph for a truck).
4. Open-Meteo hourly forecasts are looked up **for the hour the truck arrives** at each checkpoint.
5. Each checkpoint is classified **Low / Moderate / High / Severe / No Travel** using the thresholds and load rules.
6. Each route gets miles-per-risk-level and an average risk, then the routes are ranked using the brief's preference order.
7. The map shows all routes, colored risk segments, checkpoints with ETAs and conditions, route summaries, and a **smooth forecast heatmap over the trip corridor with a 0 to 48 hour slider**. The slider also moves a truck marker along every route.

## Risk logic (`backend/trips/risk.py`)

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | < 25 mph | 25 to 34 | 35 to 44 | 45 to 54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10 to 0.25 | 0.25 to 0.50 | 0.50 to 1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5 to 1.0 | 1.0 to 2.0 | 2.0 to 3.0 | > 3.0 |

**Load rules** (applied to wind only, since they model tip-over risk for heavy trailers):

- ≥ 55 mph → No Travel for any load
- 45 to 54 mph and load > 30,000 lb → No Travel
- 35 to 44 mph and load > 40,000 lb → Severe

**Checkpoint risk** is the worst of the load-adjusted wind level, rain level and snow level. Each checkpoint records which factor drove its level, and the UI shows that in bold.

**Boundary interpretation.** The brief's ranges share endpoints (0.10 to 0.25, then 0.25 to 0.50). A value exactly on a shared endpoint goes to the **higher** band, consistent with the explicit "≥ 55 mph". The exception is the top of Severe for rain and snow: the brief says No Travel is "> 1.00" and "> 3.0", so exactly 1.00 in/hr of rain is still Severe. Every boundary has a unit test.

## Recommendation logic (`backend/trips/recommend.py`)

Routes are compared **lexicographically**, as the brief lists:

1. Fewest **No Travel** miles. The brief doesn't list No Travel explicitly, but it is strictly worse than Severe, so it is compared first. A route with any No Travel stretch can never beat one without.
2. Fewest **Severe** miles
3. Fewest **High** miles
4. Lowest **average risk**: the distance-weighted mean level on a 0 (Low) to 4 (No Travel) scale
5. Shortest **travel time**

Values are rounded before comparing (0.1 mi, 0.001 avg risk, whole minutes) so float noise never decides the winner. The app explains its choice in one sentence by naming the first criterion where the winner beats the runner-up, for example "Route C has the fewest No Travel miles (0 mi vs 125 mi for Route B)". It also warns when even the best route crosses Severe or No Travel conditions.

**Miles per level.** Each checkpoint "owns" the road halfway to its neighbours, so a route's miles-by-level always add up exactly to its length.

## How the hard parts work

**Three distinct routes.** OSRM's `alternatives` often returns only one or two routes. `providers/routing.py` tops up the list with **via-point alternatives**: it routes through points pushed sideways from the midpoint of the trip (±18%, then ±35% of the straight-line distance). A candidate is kept only if it shares less than 85% of its length with an existing option, and is at most 60% slower than the fastest. Very short trips may legitimately return fewer than three routes.

**ETAs.** OSRM returns per-segment distance and duration. Each segment's time is raised to at least `distance / 65 mph` (configurable with `TRUCK_MAX_SPEED_MPH`), because OSRM uses a car profile. A checkpoint's ETA is interpolated along the cumulative time array.

**Forecast at ETA.** Open-Meteo returns hourly series in mph and inches directly. Wind is instantaneous, so the nearest hour is used. Precipitation is an accumulation over the *preceding* hour, so the hour that contains the ETA is used. That makes the value a true in/hr rate, matching the thresholds. Rain is `rain + showers`, and snow is `snowfall` depth.

**Efficient weather calls.** Checkpoints are snapped to a 0.05° (~5 km) grid, which is roughly the model's resolution. Duplicates are removed across all three routes, and the rest are batched 100 locations per request, fetched in parallel and cached for 15 minutes. A 900-mile, 3-route plan typically needs one or two weather requests.

**Corridor heatmap.** `services/corridor.py` builds a regular lat/lon grid of cells within 30 miles of any route. Cell size grows with trip length so there are never more than about 120 cells. The `/api/heatmap` call returns all 49 hourly frames (wind, rain, snow, and risk with your load applied) in one gzip-compressed response, so **moving the slider never hits the network**.

In the browser, `CorridorHeatLayer.js` is a custom Leaflet canvas layer. It bilinearly interpolates the **values** (not the colors), so color edges land where thresholds are crossed. It draws the result in Web-Mercator-correct strips and lets Leaflet pan and zoom-animate the canvas like a tile layer. Pixels are only recomputed when the hour or layer changes, about 5 ms per slider step.

**UI performance.** Route lines and checkpoint markers are memoized, so the slider only touches the heatmap canvas and three truck markers. The cursor readout lives in a tiny external store, so mouse movement doesn't re-render the app. Leaflet uses its canvas renderer for the hundreds of checkpoint markers.

## Assumptions and limitations

- **Routing uses a car profile** (OSRM public server). Truck restrictions such as bridge heights, hazmat and weight limits aren't modelled. Swapping in a truck-aware router (OpenRouteService `driving-hgv`, HERE, TomTom) only means replacing `providers/routing.py`.
- **No Hours-of-Service breaks** in ETAs. For trips over 11 hours of driving, real arrival times would be later.
- **Sustained wind** is classified, since the thresholds read as sustained speeds. Gusts are shown alongside for context.
- **Departure must be within 7 days** so the whole trip stays inside Open-Meteo's forecast horizon.
- The **public OSRM, Open-Meteo and Photon** services are free, need no API keys, and are rate-limited. Each one's base URL is an env var so it can point at a self-hosted or paid instance.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness |
| `GET` | `/api/geocode?q=dallas` | Place suggestions (Photon / OpenStreetMap) |
| `POST` | `/api/plan` | Routes, checkpoints, risk, recommendation, corridor grid |
| `POST` | `/api/heatmap` | 0 to 48 h corridor forecast frames |

```json
POST /api/plan
{
  "origin":      { "lat": 32.7767, "lon": -96.797,  "label": "Dallas, TX" },
  "destination": { "lat": 41.8781, "lon": -87.6298, "label": "Chicago, IL" },
  "departure": "2026-10-14T13:00:00Z",
  "load_lb": 42000,
  "interval_miles": 25
}
```

Validation errors return `400 {"error": "...", "details": {...}}`. Upstream failures return `502` (or `422` for "no route"), with a message the UI shows as is.

## Project structure

```
backend/
  config/                 Django settings & URLs (serves the built SPA in production)
  trips/
    risk.py               thresholds + load rules (pure functions)
    recommend.py          ranking + explanation (pure functions)
    geo.py                distances, ETAs, checkpoint sampling, polyline utils
    providers/            OSRM, Open-Meteo, Photon, shared HTTP + retries, offline fakes
    services/planner.py   the pipeline: routes → checkpoints → weather → risk → ranking
    services/corridor.py  corridor grid + 48 h heatmap frames
    serializers.py        input validation
    views.py, urls.py     REST endpoints
    tests/                67 tests: thresholds, load rules, sampling, ranking, API
frontend/
  src/App.jsx             page state and data flow
  src/components/         TripForm, PlaceInput, RouteCard (strip map), CheckpointTable, MapView, TimeBar
  src/lib/                API client, risk colors, formatting, CorridorHeatLayer (canvas heatmap)
Dockerfile, render.yaml   single-service deploy (Django serves the React build)
Makefile                local setup, API, frontend, tests (uses uv)
```

## Run locally

Requirements: [uv](https://docs.astral.sh/uv/) (Python 3.12) and Node 20+.

```bash
make setup        # uv sync in backend/, npm ci in frontend/
make backend      # http://127.0.0.1:8000
make frontend     # http://localhost:5173 (proxies /api to :8000)
make test
make demo         # same API, with the offline weather and routing fakes
```

Python dependencies live in `backend/pyproject.toml` and `backend/uv.lock`. `make setup` creates `backend/.venv` from that lockfile.

**Offline demo mode.** `make demo` swaps the three APIs for deterministic fakes, with a storm parked across the Dallas to Chicago corridor. Use it to show every risk level on demand, or when a public API is down. The tests use the same fakes.

## Deploy

**Render (free tier):** push the repo to GitHub, then in Render go to **New → Blueprint** and pick the repo. `render.yaml` builds the Dockerfile, which compiles the React app and serves it from Django with WhiteNoise behind gunicorn. No API keys are needed.

**Any Docker host:**

```bash
docker build -t crosswind .
docker run -p 8000:8000 -e DJANGO_SECRET_KEY=change-me -e DJANGO_ALLOWED_HOSTS='*' crosswind
```

| Env var | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev key | Set in production |
| `DJANGO_DEBUG` | `1` (`0` in Docker) | |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,.onrender.com` | |
| `TRUCK_MAX_SPEED_MPH` | `65` | Truck speed cap used for ETAs |
| `OSRM_BASE_URL`, `OPEN_METEO_URL`, `PHOTON_URL` | public instances | Point at self-hosted or paid services |
| `FAKE_PROVIDERS` | `0` | Offline demo / tests |
| `VITE_API_BASE` (frontend build) | same origin | Only if the frontend is hosted separately |
