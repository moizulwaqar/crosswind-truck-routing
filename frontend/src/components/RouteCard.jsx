import { memo } from "react";
import { fmtDayTime, fmtDuration, fmtMiles } from "../lib/format";
import { LEVELS, levelOf } from "../lib/risk";

/**
 * The whole trip as one bar, coloured by forecast risk mile by mile, drawn
 * to a shared scale so a shorter route is visibly shorter. Ticks mark the
 * weather checkpoints.
 */
export function StripMap({ route, maxMiles }) {
  const W = 1000;
  const scale = W / maxMiles;
  const width = route.distance_miles * scale;
  return (
    <svg className="strip" viewBox={`0 0 ${W} 22`} preserveAspectRatio="none" role="img"
      aria-label={`Risk along ${route.name}: ${LEVELS.map((l, i) => `${l.label} ${route.stats.miles_by_level[i]} miles`).join(", ")}`}>
      <rect x="0" y="5" width={width} height="12" rx="2" fill="#D5DCE2" />
      {route.risk_segments.map((s, i) => (
        <rect key={i} x={s.from_mile * scale} y="5" width={Math.max(1.5, (s.to_mile - s.from_mile) * scale)} height="12"
          fill={levelOf(s.level).color} />
      ))}
      {route.checkpoints.map((cp) => (
        <line key={cp.index} x1={cp.mile * scale} x2={cp.mile * scale} y1="18" y2="22" stroke="#1E252B" strokeOpacity="0.45"
          strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      ))}
    </svg>
  );
}

function RouteCard({ route, maxMiles, selected, onSelect }) {
  const miles = route.stats.miles_by_level;
  return (
    <button type="button" className={`route-card${selected ? " is-selected" : ""}`} onClick={() => onSelect(route.id)}
      aria-pressed={selected}>
      <div className="route-card-head">
        <span className={`shield${route.recommended ? " is-rec" : ""}`} aria-hidden="true">{route.name.slice(-1)}</span>
        <div className="route-title">
          <strong>{route.name}</strong>
          <span className="roads">{route.summary ? `via ${route.summary}` : "Alternative route"}</span>
        </div>
        {route.recommended && <span className="badge-rec">Recommended</span>}
      </div>
      <dl className="route-facts">
        <div><dt>Distance</dt><dd>{fmtMiles(route.distance_miles)}</dd></div>
        <div><dt>Drive time</dt><dd>{fmtDuration(route.duration_seconds)}</dd></div>
        <div><dt>Arrives</dt><dd>{fmtDayTime(route.arrival)}</dd></div>
      </dl>
      <StripMap route={route} maxMiles={maxMiles} />
      <ul className="risk-miles">
        {LEVELS.map((l, i) => (
          <li key={l.level} className={miles[i] > 0 ? "" : "is-zero"}>
            <i style={{ background: l.color }} />
            <span>{l.label}</span>
            <b>{miles[i] >= 100 ? Math.round(miles[i]) : miles[i].toFixed(miles[i] % 1 ? 1 : 0)} mi</b>
          </li>
        ))}
        <li className="avg">
          <span>Avg risk</span>
          <b>{route.stats.average_risk.toFixed(2)}</b>
        </li>
      </ul>
    </button>
  );
}

export default memo(RouteCard);
