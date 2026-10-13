# Loom walkthrough script (about 8 minutes)

A suggested outline for the 5 to 10 minute video. Talk through it in your own words; the points under each section are what evaluators score, so make sure each gets said. Timings are approximate.

Before recording:
- Open the hosted app in one tab and the GitHub repo in another.
- Have a terminal ready with `cd backend && pytest` (and, optionally, `FAKE_PROVIDERS=1 python manage.py runserver` for a guaranteed storm).
- Pick a real trip that has weather today. Check a national forecast map for a windy or stormy region and route through it. The Dallas to Chicago example works well in offline demo mode.

---

## 1. The problem and the result (0:00 to 0:45)
- One sentence: a driver picks between three routes by forecast weather at the time they'll be at each point, adjusted for load.
- Fill in a trip and press **Plan routes**. Point out that routes appear first and the forecast heatmap follows a moment later.

## 2. Reading the answer (0:45 to 2:00)
- The blue sign: the recommended route and the one-sentence reason (the first criterion where it beats the runner-up).
- Route cards: distance, drive time, arrival, and the **strip map**. It's the whole trip as one bar colored by risk, on a shared scale so shorter routes look shorter. The ticks are checkpoints.
- Miles at each risk level, plus average risk.

## 3. The map (2:00 to 3:30)
- Selected route is colored by risk segment; other routes are grey. Click a grey route or its shield to switch.
- Click a checkpoint: ETA, wind with gusts, rain, snow, level, and the factor that set it.
- Checkpoint table: bold values mark the factor that drove the level, and "load" marks a load-rule escalation. Clicking a row flies the map there.
- Change spacing between 10, 25 and 50 miles and re-plan to show checkpoint density changing.

## 4. Heatmap and slider (3:30 to 4:45)
- Drag the 0 to 48 h slider, or press play. The storm moves and the truck markers move along each route. The tick on the slider marks when the selected route arrives.
- Switch between Risk, Wind, Rain and Snow layers. Hover the corridor for the readout.
- Performance: all 49 frames load in one request, so the slider never waits on the network. The heatmap is a custom canvas layer that interpolates values and redraws in about 5 ms.

## 5. Load weight matters (4:45 to 5:30)
- Re-plan the same trip at 25,000 lb and then 45,000 lb. Show 45 to 54 mph winds going from Severe to **No Travel**, and the recommendation changing if it does.

## 6. Code tour (5:30 to 7:30)
- `trips/risk.py`: thresholds as data, load rules, and the boundary interpretation (a value on a shared endpoint goes to the higher band; exactly 1.00 in/hr rain is still Severe).
- `trips/recommend.py`: lexicographic ranking. No Travel is compared before Severe, and values are rounded so float noise can't decide.
- `trips/geo.py`: truck ETAs (65 mph cap on OSRM segment times) and checkpoints that own half the gap to each neighbour, so miles add up exactly.
- `trips/providers/routing.py`: OSRM plus via-point alternatives filtered by overlap and detour.
- `trips/providers/weather.py`: forecast at the ETA hour. Wind uses the nearest hour; precipitation uses the hour containing the ETA because it's an accumulation. Also grid snapping, batching and caching.
- `frontend/src/lib/CorridorHeatLayer.js`: briefly, how the heatmap is drawn.
- Run `pytest` and show 67 passing tests.

## 7. Trade-offs and next steps (7:30 to 8:15)
- OSRM is a car profile. A truck router (ORS `driving-hgv`, HERE) is a drop-in change to one module.
- No Hours-of-Service breaks in ETAs yet.
- Possible next steps: suggest a later departure when every route has No Travel miles, and use gusts as an extra signal.
