import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CheckpointTable from "./components/CheckpointTable";
import MapView from "./components/MapView";
import RouteCard from "./components/RouteCard";
import TimeBar from "./components/TimeBar";
import TripForm from "./components/TripForm";
import { fetchHeatmap, fetchTrip, fetchTrips, planTrip } from "./lib/api";
import { fmtDayTime } from "./lib/format";

export default function App() {
  const [plan, setPlan] = useState(null);
  const [planning, setPlanning] = useState(false);
  const [error, setError] = useState("");
  const [weatherNotice, setWeatherNotice] = useState("");
  const [selectedId, setSelectedId] = useState(null);

  const [heat, setHeat] = useState(null);
  const [heatLoading, setHeatLoading] = useState(false);
  const [heatError, setHeatError] = useState("");
  const [hour, setHour] = useState(0);
  const [mode, setMode] = useState("risk");

  const [focus, setFocus] = useState(null);
  const [showAllCheckpoints, setShowAllCheckpoints] = useState(true);
  const [savedTrips, setSavedTrips] = useState([]);
  const requestId = useRef(0);

  const refreshSaved = useCallback(() => {
    fetchTrips().then(setSavedTrips).catch(() => {});
  }, []);

  useEffect(() => {
    refreshSaved();
  }, [refreshSaved]);

  const showPlan = useCallback((id, result) => {
    setPlan(result);
    setSelectedId(result.recommended_route_id);
    setHour(0);
    setHeatLoading(true);
    fetchHeatmap({ start: result.departure, load_lb: result.load_lb, cells: result.corridor.cells })
      .then((h) => {
        if (id !== requestId.current) return;
        if (h.weather_notice) setWeatherNotice(h.weather_notice);
        setHeat(h);
      })
      .catch((e) => id === requestId.current && setHeatError(e.message))
      .finally(() => id === requestId.current && setHeatLoading(false));
  }, []);

  const onSubmit = useCallback(async (payload) => {
    const id = ++requestId.current;
    setPlanning(true);
    setError("");
    setWeatherNotice("");
    setHeat(null);
    setHeatError("");
    setFocus(null);
    try {
      const result = await planTrip(payload);
      if (id !== requestId.current) return; // a newer search started
      setWeatherNotice(result.weather_notice || "");
      showPlan(id, result);
      refreshSaved();
    } catch (e) {
      if (id === requestId.current) setError(e.message);
    } finally {
      if (id === requestId.current) setPlanning(false);
    }
  }, [refreshSaved, showPlan]);

  const openSaved = useCallback(async (tripId) => {
    const id = ++requestId.current;
    setPlanning(true);
    setError("");
    setHeat(null);
    setHeatError("");
    setFocus(null);
    try {
      const result = await fetchTrip(tripId);
      if (id !== requestId.current) return;
      showPlan(id, result);
    } catch (e) {
      if (id === requestId.current) setError(e.message);
    } finally {
      if (id === requestId.current) setPlanning(false);
    }
  }, [showPlan]);

  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null;
  const ordered = useMemo(() => (plan ? [...plan.routes].sort((a, b) => a.rank - b.rank) : []), [plan]);
  const maxMiles = useMemo(() => Math.max(1, ...ordered.map((r) => r.distance_miles)), [ordered]);
  const recommended = ordered[0];
  const focusCheckpoint = useCallback((cp) => setFocus({ cp, routeName: cp.routeName }), []);

  return (
    <div className="app">
      <aside className="panel">
        <header className="brand">
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M4 4h24v14c0 6-6 9-12 11C10 27 4 24 4 18z" />
            <path d="M9 13h11M12 18h10" className="gust" />
          </svg>
          <div>
            <h1>Crosswind</h1>
            <p>Compare three truck routes by the weather you'll meet when you get there.</p>
          </div>
        </header>

        {savedTrips.length > 0 && (
          <section className="recent-searches" aria-label="Recent searches">
            <h2>Recent searches</h2>
            <ul>
              {savedTrips.map((t) => {
                const from = t.origin_label?.split(",")[0] || "Origin";
                const to = t.destination_label?.split(",")[0] || "Destination";
                return (
                  <li key={t.id}>
                    <button
                      type="button"
                      className={plan?.trip_id === t.id ? "is-open" : ""}
                      onClick={() => openSaved(t.id)}
                      disabled={planning}
                      title={`${t.origin_label || from} to ${t.destination_label || to}, ${fmtDayTime(t.departure)}, ${Number(t.load_lb).toLocaleString()} lb`}
                    >
                      {from} to {to}
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        <TripForm onSubmit={onSubmit} busy={planning} />

        {error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}

        {weatherNotice && (
          <div className="notice" role="status">
            {weatherNotice}
          </div>
        )}

        {!plan && !planning && !error && (
          <p className="empty-state">
            Enter a trip to get three route options. Each one is checked against hourly forecasts at the time your truck reaches every
            checkpoint, using your load weight.
          </p>
        )}

        {plan && recommended && (
          <section className={`verdict level-${recommended.stats.max_level}`} aria-live="polite">
            <h2>Take {recommended.name}</h2>
            <p>{plan.recommendation_reason}</p>
          </section>
        )}

        {plan && (
          <section className="routes" aria-label="Route options">
            <div className="section-head">
              <h2>Route options</h2>
              <label className="toggle">
                <input type="checkbox" checked={showAllCheckpoints} onChange={(e) => setShowAllCheckpoints(e.target.checked)} />
                All checkpoints on map
              </label>
            </div>
            {ordered.map((r) => (
              <RouteCard key={r.id} route={r} maxMiles={maxMiles} selected={r.id === selectedId} onSelect={setSelectedId} />
            ))}
            <p className="method">
              Ranked by fewest No Travel, then Severe, then High miles, then lowest average risk, then shortest drive time. Drive
              times cap truck speed at 65 mph.
            </p>
          </section>
        )}

        {selected && <CheckpointTable route={selected} onFocus={focusCheckpoint} />}
      </aside>

      <main className="map-wrap">
        <MapView
          plan={plan}
          selectedId={selectedId}
          onSelect={setSelectedId}
          heat={heat}
          hour={hour}
          mode={mode}
          focusCheckpoint={focus}
          showAllCheckpoints={showAllCheckpoints}
        />
        {plan && (
          <TimeBar
            heat={heat}
            loading={heatLoading}
            error={heatError}
            hour={hour}
            setHour={setHour}
            mode={mode}
            setMode={setMode}
            selectedRoute={selected}
          />
        )}
        {planning && <div className="map-busy" role="status">Checking routes and forecasts…</div>}
      </main>
    </div>
  );
}
