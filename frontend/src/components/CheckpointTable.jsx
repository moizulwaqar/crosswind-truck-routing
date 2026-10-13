import { memo, useState } from "react";
import { fmtDayTime, fmtNum } from "../lib/format";
import { levelOf } from "../lib/risk";

function CheckpointTable({ route, onFocus }) {
  const pick = (cp) => onFocus({ ...cp, routeName: route.name });
  const [onlyRisky, setOnlyRisky] = useState(false);
  const rows = onlyRisky ? route.checkpoints.filter((c) => c.level > 0) : route.checkpoints;

  return (
    <section className="checkpoints" aria-label={`Checkpoints on ${route.name}`}>
      <div className="section-head">
        <h2>Checkpoints on {route.name}</h2>
        <label className="toggle">
          <input type="checkbox" checked={onlyRisky} onChange={(e) => setOnlyRisky(e.target.checked)} />
          Hide Low
        </label>
      </div>
      {rows.length === 0 ? (
        <p className="empty">Every checkpoint on this route is Low risk at its arrival time.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Mile</th>
                <th scope="col">Arrive</th>
                <th scope="col">Wind</th>
                <th scope="col">Rain</th>
                <th scope="col">Snow</th>
                <th scope="col">Risk</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((cp) => {
                const lvl = levelOf(cp.level);
                return (
                  <tr key={cp.index} tabIndex={0} onClick={() => pick(cp)}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), pick(cp))}
                    title={cp.reasons.join("; ") || "No hazards"}>
                    <td>{Math.round(cp.mile)}</td>
                    <td>{fmtDayTime(cp.eta)}</td>
                    <td className={cp.wind_level === cp.level && cp.level ? "drives" : ""}>
                      {fmtNum(cp.wind_mph)}
                      {cp.load_escalated && <sup title="Escalated by load rules">load</sup>}
                    </td>
                    <td className={cp.rain_level === cp.level && cp.level ? "drives" : ""}>{fmtNum(cp.rain_in_hr, 2)}</td>
                    <td className={cp.snow_level === cp.level && cp.level ? "drives" : ""}>{fmtNum(cp.snow_in_hr, 2)}</td>
                    <td>
                      <span className="risk-pill" style={{ background: lvl.color, color: lvl.ink }}>{lvl.label}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="units">Wind in mph, rain and snow in inches per hour, forecast for the hour the truck arrives. Bold values set the risk level.</p>
    </section>
  );
}

export default memo(CheckpointTable);
