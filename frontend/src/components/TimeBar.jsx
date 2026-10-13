import { useEffect, useRef, useState } from "react";
import { fmtDayTime, fmtNum } from "../lib/format";
import { useHover } from "../lib/hoverStore";
import { LEVELS, RAMPS, levelOf } from "../lib/risk";

const MODES = [
  { id: "risk", label: "Risk" },
  { id: "wind", label: "Wind" },
  { id: "rain", label: "Rain" },
  { id: "snow", label: "Snow" },
];

function Legend({ mode }) {
  if (mode === "risk") {
    return (
      <ul className="legend">
        {LEVELS.map((l) => (
          <li key={l.level}><i style={{ background: l.color }} />{l.label}</li>
        ))}
      </ul>
    );
  }
  const ramp = RAMPS[mode];
  const stops = ramp.stops;
  const gradient = stops.map(([, c], i) => `rgb(${c.join(",")}) ${(i / (stops.length - 1)) * 100}%`).join(", ");
  return (
    <div className="legend ramp">
      <div className="ramp-bar" style={{ background: `linear-gradient(90deg, ${gradient})` }} />
      <div className="ramp-labels">
        {stops.map(([v]) => <span key={v}>{v}</span>)}
        <span className="unit">{ramp.unit}</span>
      </div>
    </div>
  );
}

function HoverReadout() {
  const hover = useHover();
  return (
    <span className="hover" aria-live="polite">
      {hover && hover.risk != null ? (
        <>
          <i style={{ background: levelOf(hover.risk).color }} />
          {levelOf(hover.risk).label}: wind {fmtNum(hover.wind)} mph, rain {fmtNum(hover.rain, 2)}, snow {fmtNum(hover.snow, 2)} in/hr
        </>
      ) : (
        "Point at the corridor to read the forecast"
      )}
    </span>
  );
}

export default function TimeBar({ start, heat, loading, error, hour, setHour, mode, setMode, selectedRoute }) {
  const [playing, setPlaying] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => {
      setHour((h) => (h >= 48 ? 0 : h + 1));
    }, 450);
    return () => clearInterval(timer.current);
  }, [playing, setHour]);

  const startMs = new Date(heat?.start || start).getTime();
  const frameTime = startMs ? new Date(startMs + hour * 3600 * 1000).toISOString() : null;
  const arrivedAt = selectedRoute ? selectedRoute.duration_seconds / 3600 : null;

  return (
    <div className="timebar" aria-label="Forecast along the trip corridor">
      <div className="timebar-top">
        <div className="segmented small" role="radiogroup" aria-label="Heatmap layer">
          {MODES.map((m) => (
            <label key={m.id} className={mode === m.id ? "is-on" : ""}>
              <input type="radio" name="mode" checked={mode === m.id} onChange={() => setMode(m.id)} />
              {m.label}
            </label>
          ))}
        </div>
        <Legend mode={mode} />
      </div>

      {loading && <p className="timebar-status">Loading the 48-hour corridor forecast…</p>}
      {error && <p className="timebar-status is-error">{error}</p>}

      {Number.isFinite(startMs) && (
        <>
          <div className="timebar-row">
            <button type="button" className="play" onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? "Pause forecast animation" : "Play forecast animation"}>
              {playing ? (
                <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="2" width="3.5" height="12" /><rect x="9.5" y="2" width="3.5" height="12" /></svg>
              ) : (
                <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2l10 6-10 6z" /></svg>
              )}
            </button>
            <div className="slider-wrap">
              <input type="range" min="0" max="48" step="1" value={hour}
                onChange={(e) => { setPlaying(false); setHour(Number(e.target.value)); }}
                aria-label="Hours after departure" aria-valuetext={`${hour} hours after departure, ${fmtDayTime(frameTime)}`} />
              <div className="ticks" aria-hidden="true">
                {[0, 6, 12, 18, 24, 30, 36, 42, 48].map((h) => <span key={h} style={{ left: `${(h / 48) * 100}%` }}>{h}h</span>)}
                {arrivedAt != null && arrivedAt <= 48 && (
                  <span className="arrive-tick" style={{ left: `${(arrivedAt / 48) * 100}%` }} title="Selected route arrives" />
                )}
              </div>
            </div>
          </div>
          <div className="timebar-readout">
            <span className="when">
              <strong>+{hour} h</strong> {fmtDayTime(frameTime)}
              {arrivedAt != null && hour > arrivedAt && <em>, {selectedRoute.name} has arrived</em>}
            </span>
            <HoverReadout />
          </div>
        </>
      )}
    </div>
  );
}
