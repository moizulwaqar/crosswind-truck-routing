// Same-origin in production (Django serves the app); Vite proxies /api in dev.
// VITE_API_BASE lets the frontend be hosted separately from the API.
const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE}/api/${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new Error("Can't reach the server. Check your connection and try again.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `Request failed (HTTP ${res.status}).`);
  return body;
}

export const searchPlaces = (q, signal) =>
  request(`geocode?q=${encodeURIComponent(q)}`, { signal }).then((b) => b.results);

export const planTrip = (payload) =>
  request("plan", { method: "POST", body: JSON.stringify(payload) });

export const fetchTrips = () => request("trips").then((b) => b.trips);

export const fetchTrip = (id) => request(`trips/${id}`);

export const fetchHeatmap = (payload) =>
  request("heatmap", { method: "POST", body: JSON.stringify(payload) });
