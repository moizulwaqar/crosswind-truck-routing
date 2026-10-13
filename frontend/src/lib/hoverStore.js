import { useSyncExternalStore } from "react";

// The heatmap readout changes on every mouse move. Keeping it in a tiny
// external store means only the readout re-renders, not the whole app/map.
let value = null;
const listeners = new Set();

export const hoverStore = {
  set(next) {
    if (next === value || (next && value && next.risk === value.risk && next.wind === value.wind && next.rain === value.rain && next.snow === value.snow)) return;
    value = next;
    listeners.forEach((l) => l());
  },
  subscribe(l) {
    listeners.add(l);
    return () => listeners.delete(l);
  },
  get: () => value,
};

export const useHover = () => useSyncExternalStore(hoverStore.subscribe, hoverStore.get);
