import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  ZoomControl,
  useMap,
  useMapEvent,
} from "react-leaflet";
import { CorridorHeatLayer } from "../lib/CorridorHeatLayer";
import { fmtDayTime, fmtDuration, fmtMiles, fmtNum } from "../lib/format";
import { hoverStore } from "../lib/hoverStore";
import { levelOf } from "../lib/risk";

const US_CENTER = [39.5, -98.35];
const HEAT_KEY = { risk: "risk", wind: "wind_mph", rain: "rain_in_hr", snow: "snow_in_hr" };

/* ---------- Icons are built once and reused (setIcon replaces DOM) ---------- */
const shieldIcon = (letter, active) =>
  L.divIcon({
    className: "",
    html: `<div class="map-shield${active ? " is-active" : ""}">${letter}</div>`,
    iconSize: [30, 32],
    iconAnchor: [15, 16],
  });
const TRUCK_SVG =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 6h11v9H2zM13 9h4.5l3.5 3.5V15h-8z" fill="currentColor"/><circle cx="6" cy="17" r="2" fill="currentColor"/><circle cx="17" cy="17" r="2" fill="currentColor"/></svg>';
const TRUCK_ICON = {
  active: L.divIcon({ className: "", html: `<div class="map-truck is-active">${TRUCK_SVG}</div>`, iconSize: [30, 30], iconAnchor: [15, 15] }),
  idle: L.divIcon({ className: "", html: `<div class="map-truck">${TRUCK_SVG}</div>`, iconSize: [20, 20], iconAnchor: [10, 10] }),
};
const END_ICON = {
  start: L.divIcon({ className: "", html: '<div class="map-end map-end--start">Start</div>', iconSize: [52, 24], iconAnchor: [26, 12] }),
  end: L.divIcon({ className: "", html: '<div class="map-end map-end--end">End</div>', iconSize: [52, 24], iconAnchor: [26, 12] }),
};

/* ---------- Heatmap: only this and the trucks change with the slider ---------- */
function HeatLayer({ corridor, heat, hour, mode }) {
  const map = useMap();
  const layerRef = useRef(null);

  useEffect(() => {
    const layer = new CorridorHeatLayer();
    layer.addTo(map);
    layerRef.current = layer;
    return () => layer.remove();
  }, [map]);

  useEffect(() => {
    if (corridor) layerRef.current?.setGrid(corridor.cells, corridor.lat_step, corridor.lon_step);
  }, [corridor]);

  useEffect(() => {
    if (heat) layerRef.current?.setFrame(heat[HEAT_KEY[mode]].map((row) => row[hour]), mode);
  }, [heat, hour, mode]);

  // Readout under the cursor, at most once per animation frame.
  const frame = useRef(0);
  const latest = useRef({ heat, hour });
  latest.current = { heat, hour };
  useMapEvent("mousemove", (e) => {
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      const { heat: h, hour: hr } = latest.current;
      const k = h ? layerRef.current?.cellIndexAt(e.latlng.lat, e.latlng.lng) : -1;
      hoverStore.set(
        k >= 0 ? { risk: h.risk[k][hr], wind: h.wind_mph[k][hr], rain: h.rain_in_hr[k][hr], snow: h.snow_in_hr[k][hr] } : null,
      );
    });
  });
  useMapEvent("mouseout", () => hoverStore.set(null));
  return null;
}

function Trucks({ routes, hour, selectedId }) {
  return routes.map((r) => (
    <Marker
      key={`truck-${r.id}`}
      position={r.timeline[hour]}
      icon={r.id === selectedId ? TRUCK_ICON.active : TRUCK_ICON.idle}
      zIndexOffset={r.id === selectedId ? 1000 : 400}
      interactive={false}
      keyboard={false}
    />
  ));
}

/* ---------- Routes and checkpoints: re-render only when the plan/selection changes ---------- */
const RouteLayers = memo(function RouteLayers({ plan, selectedId, onSelect, showAllCheckpoints, onPickCheckpoint }) {
  const routes = plan.routes;
  const selected = routes.find((r) => r.id === selectedId);
  const others = routes.filter((r) => r.id !== selectedId);
  const labelPoints = useMemo(
    () => Object.fromEntries(routes.map((r) => [r.id, r.coords[Math.floor(r.coords.length * 0.45)]])),
    [routes],
  );

  return (
    <>
      {others.map((r) => (
        <Polyline
          key={`alt-${r.id}-${selectedId}`}
          positions={r.coords}
          pathOptions={{ color: "#56677A", weight: 5, opacity: 0.6, lineCap: "round" }}
          eventHandlers={{ click: () => onSelect(r.id) }}
        >
          <Tooltip sticky>
            <strong>{r.name}</strong> {fmtMiles(r.distance_miles)}, {fmtDuration(r.duration_seconds)}
            <br />
            Severe {r.stats.miles_by_level[3]} mi, High {r.stats.miles_by_level[2]} mi. Click to select.
          </Tooltip>
        </Polyline>
      ))}

      {selected && (
        <>
          <Polyline
            key={`casing-${selected.id}`}
            positions={selected.coords}
            pathOptions={{ color: "#1E252B", weight: 11, opacity: 0.85, lineCap: "round" }}
          />
          {selected.risk_segments.map((seg, i) => (
            <Polyline
              key={`seg-${selected.id}-${i}`}
              positions={seg.coords}
              pathOptions={{ color: levelOf(seg.level).color, weight: 6, opacity: 1, lineCap: "butt" }}
            >
              <Tooltip sticky>
                {levelOf(seg.level).label}: miles {Math.round(seg.from_mile)} to {Math.round(seg.to_mile)}
              </Tooltip>
            </Polyline>
          ))}
        </>
      )}

      {routes.map((r) => {
        const active = r.id === selectedId;
        if (!active && !showAllCheckpoints) return null;
        return r.checkpoints.map((cp) => (
          <CircleMarker
            key={`cp-${r.id}-${cp.index}-${active}`}
            center={[cp.lat, cp.lon]}
            radius={active ? 5 : 3}
            pathOptions={{
              color: active ? "#ffffff" : levelOf(cp.level).color,
              weight: active ? 1.5 : 0,
              fillColor: levelOf(cp.level).color,
              fillOpacity: active ? 1 : 0.75,
            }}
            eventHandlers={{ click: () => onPickCheckpoint({ cp, routeName: r.name }) }}
          />
        ));
      })}

      {routes.map((r) => (
        <Marker
          key={`shield-${r.id}-${selectedId}`}
          position={labelPoints[r.id]}
          icon={shieldIcon(r.name.slice(-1), r.id === selectedId)}
          eventHandlers={{ click: () => onSelect(r.id) }}
          zIndexOffset={r.id === selectedId ? 500 : 0}
          keyboard={false}
        />
      ))}

      <Marker position={[plan.origin.lat, plan.origin.lon]} icon={END_ICON.start} zIndexOffset={1500} keyboard={false} />
      <Marker position={[plan.destination.lat, plan.destination.lon]} icon={END_ICON.end} zIndexOffset={1500} keyboard={false} />
    </>
  );
});

/* ---------- Camera ---------- */
function FitToPlan({ plan }) {
  const map = useMap();
  useEffect(() => {
    if (!plan) return;
    map.flyToBounds(L.latLngBounds(plan.routes.flatMap((r) => r.coords)), { padding: [48, 48], duration: 0.8 });
  }, [plan, map]);
  return null;
}

function FlyToCheckpoint({ checkpoint }) {
  const map = useMap();
  useEffect(() => {
    if (checkpoint) map.flyTo([checkpoint.lat, checkpoint.lon], Math.max(map.getZoom(), 8), { duration: 0.6 });
  }, [checkpoint, map]);
  return null;
}

function PopupCloseWatcher({ onClose }) {
  useMapEvent("popupclose", onClose);
  return null;
}

function CheckpointPopup({ cp, routeName }) {
  const lvl = levelOf(cp.level);
  return (
    <div className="cp-popup">
      <div className="cp-popup-head">
        <span className="risk-pill" style={{ background: lvl.color, color: lvl.ink }}>
          {lvl.label}
        </span>
        <span>
          {routeName}, mile {Math.round(cp.mile)}
        </span>
      </div>
      <dl>
        <dt>Arrive</dt>
        <dd>{fmtDayTime(cp.eta)}</dd>
        <dt>Wind</dt>
        <dd>
          {fmtNum(cp.wind_mph)} mph <span className="muted">(gusts {fmtNum(cp.gust_mph)})</span>
        </dd>
        <dt>Rain</dt>
        <dd>{fmtNum(cp.rain_in_hr, 2)} in/hr</dd>
        <dt>Snow</dt>
        <dd>{fmtNum(cp.snow_in_hr, 2)} in/hr</dd>
      </dl>
      {cp.reasons.length > 0 && <p className="cp-reason">{cp.reasons.join("; ")}</p>}
    </div>
  );
}

export default function MapView({ plan, selectedId, onSelect, heat, hour, mode, focusCheckpoint, showAllCheckpoints }) {
  const [popup, setPopup] = useState(null); // { cp, routeName }
  useEffect(() => setPopup(null), [plan]);
  useEffect(() => {
    if (focusCheckpoint) setPopup(focusCheckpoint);
  }, [focusCheckpoint]);
  const closePopup = useCallback(() => setPopup(null), []);

  return (
    <MapContainer center={US_CENTER} zoom={4} minZoom={3} preferCanvas zoomControl={false} className="map">
      <ZoomControl position="topright" />
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        attribution="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
        maxNativeZoom={16}
        maxZoom={19}
      />
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
        maxNativeZoom={16}
        maxZoom={19}
      />
      <HeatLayer corridor={plan?.corridor} heat={heat} hour={hour} mode={mode} />
      <FitToPlan plan={plan} />
      <FlyToCheckpoint checkpoint={focusCheckpoint?.cp} />
      {plan && (
        <RouteLayers
          plan={plan}
          selectedId={selectedId}
          onSelect={onSelect}
          showAllCheckpoints={showAllCheckpoints}
          onPickCheckpoint={setPopup}
        />
      )}
      {plan && <Trucks routes={plan.routes} hour={hour} selectedId={selectedId} />}
      <PopupCloseWatcher onClose={closePopup} />
      {popup && (
        <Popup position={[popup.cp.lat, popup.cp.lon]} offset={[0, -4]}>
          <CheckpointPopup cp={popup.cp} routeName={popup.routeName} />
        </Popup>
      )}
    </MapContainer>
  );
}
