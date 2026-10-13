import L from "leaflet";
import { LEVEL_RGB, RAMPS, rampColor } from "./risk";

/**
 * Smooth weather heatmap for the trip corridor.
 *
 * The backend sends forecast values on a regular lat/lon grid. For the
 * current hour we:
 *   1. bilinearly interpolate the *values* (not colors) onto a grid UPSAMPLE×
 *      finer, so color boundaries fall where the thresholds are crossed;
 *   2. color each pixel (discrete risk colors, or a continuous ramp);
 *   3. on map move/zoom, draw that image onto one canvas in horizontal strips,
 *      each placed at its true Web-Mercator y-position.
 *
 * Step 1–2 only run when the hour/layer changes (a few ms); step 3 is a
 * handful of drawImage calls. Panning and zoom animation are handled by
 * Leaflet moving/scaling the canvas, exactly like a tile layer.
 */
const UPSAMPLE = 6;
const RISK_ALPHA = [0.12, 0.42, 0.5, 0.58, 0.68];

export const CorridorHeatLayer = L.Layer.extend({
  initialize() {
    this._grid = null;
    this._image = null;
  },

  onAdd(map) {
    this._map = map;
    if (!map.getPane("heat")) {
      const pane = map.createPane("heat");
      pane.style.zIndex = 350; // above tiles, below route lines and markers
      pane.style.pointerEvents = "none";
    }
    const canvas = (this._canvas = L.DomUtil.create("canvas", "corridor-heat"));
    const animated = map.options.zoomAnimation && L.Browser.any3d;
    L.DomUtil.addClass(canvas, `leaflet-zoom-${animated ? "animated" : "hide"}`);
    map.getPane("heat").appendChild(canvas);
    map.on("moveend resize", this._reset, this);
    if (animated) map.on("zoomanim", this._animateZoom, this);
    this._reset();
  },

  onRemove(map) {
    L.DomUtil.remove(this._canvas);
    map.off("moveend resize", this._reset, this);
    map.off("zoomanim", this._animateZoom, this);
  },

  /** cells: [[lat, lon], …] (cell centres); latStep/lonStep: cell size in degrees. */
  setGrid(cells, latStep, lonStep) {
    const ij = cells.map(([lat, lon]) => [Math.round(lat / latStep - 0.5), Math.round(lon / lonStep - 0.5)]);
    const is = ij.map((p) => p[0]);
    const js = ij.map((p) => p[1]);
    const iMin = Math.min(...is), iMax = Math.max(...is);
    const jMin = Math.min(...js), jMax = Math.max(...js);
    const rows = iMax - iMin + 1, cols = jMax - jMin + 1;
    const slot = new Int32Array(cells.length);
    const lookup = new Map();
    ij.forEach(([i, j], k) => {
      slot[k] = (iMax - i) * cols + (j - jMin); // row 0 = northernmost
      lookup.set(`${i},${j}`, k);
    });
    this._grid = { latStep, lonStep, iMin, iMax, jMin, jMax, rows, cols, slot, lookup };
    this._image = null;
  },

  /** values: one number (or null) per cell for the current hour. */
  setFrame(values, mode) {
    if (!this._grid) return;
    const { rows, cols, slot } = this._grid;
    const field = new Float32Array(rows * cols).fill(NaN);
    values.forEach((v, k) => {
      if (v != null) field[slot[k]] = v;
    });
    this._image = renderImage(field, rows, cols, mode);
    this._redraw();
  },

  /** Index of the cell under a lat/lon, or -1. */
  cellIndexAt(lat, lon) {
    if (!this._grid) return -1;
    const { latStep, lonStep, lookup } = this._grid;
    const k = lookup.get(`${Math.floor(lat / latStep)},${Math.floor(lon / lonStep)}`);
    return k ?? -1;
  },

  _reset() {
    const map = this._map;
    const size = map.getSize();
    const dpr = window.devicePixelRatio || 1;
    L.DomUtil.setPosition(this._canvas, map.containerPointToLayerPoint([0, 0]));
    this._canvas.width = Math.round(size.x * dpr);
    this._canvas.height = Math.round(size.y * dpr);
    this._canvas.style.width = `${size.x}px`;
    this._canvas.style.height = `${size.y}px`;
    this._redraw();
  },

  _redraw() {
    if (!this._map || !this._canvas) return;
    const ctx = this._canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
    if (!this._image || !this._grid) return;

    const map = this._map;
    const { latStep, iMax, jMin, jMax, rows, lonStep } = this._grid;
    const north = (iMax + 1) * latStep;
    const west = jMin * lonStep;
    const east = (jMax + 1) * lonStep;
    const x0 = map.latLngToContainerPoint([north, west]).x;
    const x1 = map.latLngToContainerPoint([north, east]).x;
    const img = this._image;
    const stripPx = UPSAMPLE; // one source strip per grid row
    const degPerPx = (rows * latStep) / img.height;

    ctx.imageSmoothingEnabled = true;
    for (let py = 0; py < img.height; py += stripPx) {
      const latTop = north - py * degPerPx;
      const latBot = north - (py + stripPx) * degPerPx;
      // Snap strip edges to device pixels so neighbouring strips neither
      // overlap (dark seams) nor leave hairline gaps.
      const yTop = Math.round(map.latLngToContainerPoint([latTop, west]).y * dpr) / dpr;
      const yBot = Math.round(map.latLngToContainerPoint([latBot, west]).y * dpr) / dpr;
      if (yBot > yTop) ctx.drawImage(img, 0, py, img.width, stripPx, x0, yTop, x1 - x0, yBot - yTop);
    }
  },

  _animateZoom(e) {
    const map = this._map;
    const scale = map.getZoomScale(e.zoom);
    const offset = map._getCenterOffset(e.center)._multiplyBy(-scale).subtract(map._getMapPanePos());
    L.DomUtil.setTransform(this._canvas, offset, scale);
  },
});

function renderImage(field, rows, cols, mode) {
  const W = cols * UPSAMPLE;
  const H = rows * UPSAMPLE;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(W, H);
  const px = img.data;
  const ramp = RAMPS[mode];

  const at = (r, c) => (r < 0 || c < 0 || r >= rows || c >= cols ? NaN : field[r * cols + c]);

  for (let y = 0; y < H; y++) {
    const gy = (y + 0.5) / UPSAMPLE - 0.5;
    const r0 = Math.floor(gy), fy = gy - r0;
    for (let x = 0; x < W; x++) {
      const gx = (x + 0.5) / UPSAMPLE - 0.5;
      const c0 = Math.floor(gx), fx = gx - c0;
      // Bilinear interpolation that ignores missing neighbours; the share of
      // weight that *was* available becomes a soft corridor edge.
      let sum = 0, wsum = 0;
      const add = (v, w) => {
        if (!Number.isNaN(v)) {
          sum += v * w;
          wsum += w;
        }
      };
      add(at(r0, c0), (1 - fx) * (1 - fy));
      add(at(r0, c0 + 1), fx * (1 - fy));
      add(at(r0 + 1, c0), (1 - fx) * fy);
      add(at(r0 + 1, c0 + 1), fx * fy);
      if (wsum < 0.05) continue;
      const v = sum / wsum;
      const edge = Math.min(1, wsum * 1.6);

      let rgb, alpha;
      if (mode === "risk") {
        const level = Math.max(0, Math.min(4, Math.round(v)));
        rgb = LEVEL_RGB[level];
        alpha = RISK_ALPHA[level];
      } else {
        [rgb, alpha] = rampColor(ramp, v);
      }
      const o = (y * W + x) * 4;
      px[o] = rgb[0];
      px[o + 1] = rgb[1];
      px[o + 2] = rgb[2];
      px[o + 3] = Math.round(255 * alpha * edge);
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}
