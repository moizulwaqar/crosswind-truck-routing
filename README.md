# Crosswind

A React and Django app that gives a truck driver three routes and recommends the safest one. Weather is sampled along each route at the truck’s estimated arrival time, then scored with the wind, rain, snow, and load rules.

**Live app:** https://crosswind-truck-routing-ec233.containers.snapdeploy.app/

The first load after the host has been idle can take about a minute.

## How a trip is planned

1. The driver enters origin, destination, departure time, and load weight, and chooses checkpoints every 10, 25, or 50 miles.
2. OSRM returns three distinct driving routes. When its own alternatives are too similar, the planner adds via-point routes and keeps only those that differ in path and stay within a reasonable detour.
3. Each route is sampled at the chosen spacing. Segment times from the router are capped at 65 mph, and each checkpoint gets the truck’s ETA.
4. Open-Meteo supplies the hourly forecast for that ETA. Wind uses the nearest hour. Rain and snow are hourly accumulations, so the hour containing the ETA is used. Rain is rain plus showers. Snow is snowfall depth.
5. Each checkpoint is classified Low, Moderate, High, Severe, or No Travel. The checkpoint level is the worst of load-adjusted wind, rain, and snow.
6. Routes are ranked, and the map draws every route, its risk stretches, checkpoints, ETAs, and road summary.
7. A corridor heatmap covers 0 to 48 hours. All 49 frames load in one response, so the slider does not call the network again. It also moves a truck marker along each route.

## Risk

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Load rules apply to wind:

- ≥ 55 mph is No Travel for any load
- 45–54 mph and a load above 30,000 lb is No Travel
- 35–44 mph and a load above 40,000 lb is Severe

A value on a shared boundary belongs to the higher band, matching “≥ 55 mph”. Exactly 1.00 in/hr of rain and exactly 3.0 in/hr of snow stay Severe, because No Travel is strictly above those rates. Gusts are shown next to sustained wind and are not classified. Thresholds live in `backend/trips/risk.py` and are unit tested at every boundary.

## Recommendation

Routes are compared in this order (`backend/trips/recommend.py`):

1. Fewest No Travel miles. No Travel is worse than Severe, so any No Travel stretch loses to a route that has none.
2. Fewest Severe miles
3. Fewest High miles
4. Lowest average risk, the distance-weighted mean from 0 (Low) to 4 (No Travel)
5. Shortest travel time

Miles are rounded to 0.1, average risk to 0.001, and time to the nearest minute before comparison. Each checkpoint owns the road halfway to its neighbors, so the miles in each level add up to the route length. The result names the first criterion that separates the winner from the next route, and it warns when that winner still crosses Severe or No Travel conditions.

## Map

The selected route is colored by risk. The other routes stay visible and can be selected from the map. Checkpoints open to show ETA, wind, gusts, rain, snow, and the factor that set the level. The heatmap is a Leaflet canvas layer over the cells within 30 miles of the routes. It interpolates the forecast values, so a color change sits on a threshold. Route geometry and markers stay put while the slider runs. Only the canvas and the truck markers update.

## Run locally

Python 3.12 and Node 20 or newer.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py runserver
```

```bash
cd frontend
npm ci
npm run dev
```

The UI is at http://localhost:5173 and proxies `/api` to http://127.0.0.1:8000. Tests:

```bash
cd backend && pytest
```

`FAKE_PROVIDERS=1 python manage.py runserver` serves the same API with deterministic routing and weather, including a storm on the Dallas to Chicago example. The tests use those fakes.

Production is the `Dockerfile`. SnapDeploy builds it on every push to `main` (`snapdeploy.yaml`). The same image runs anywhere with `docker build -t crosswind .` and `docker run -p 8000:8000 -e DJANGO_SECRET_KEY=change-me -e DJANGO_ALLOWED_HOSTS='*' crosswind`.

## Layout

```
backend/trips/
  risk.py            thresholds and load rules
  recommend.py       ranking
  geo.py             distance, ETAs, checkpoint sampling
  providers/         OSRM, Open-Meteo, geocoding
  services/          planning pipeline and corridor heatmap
frontend/src/
  components/        trip form, route cards, map, forecast slider
  lib/CorridorHeatLayer.js
```

## Scope

- Routing uses OSRM’s car profile. Bridge height, hazmat, and weight limits are not applied. A truck router can replace `providers/routing.py`.
- ETAs do not insert hours-of-service breaks.
- Departure must be within 7 days so the trip stays inside the forecast horizon.
- Very short trips can return fewer than three routes when no distinct alternative exists.
