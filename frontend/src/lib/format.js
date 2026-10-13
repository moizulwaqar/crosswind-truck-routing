const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
const dayTimeFmt = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
});
const tzFmt = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" });

export const fmtTime = (iso) => timeFmt.format(new Date(iso));
export const fmtDayTime = (iso) => dayTimeFmt.format(new Date(iso));
export const tzName = () =>
  tzFmt.formatToParts(new Date()).find((p) => p.type === "timeZoneName")?.value ?? "";

export function fmtDuration(seconds) {
  const m = Math.round(seconds / 60);
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}

export const fmtMiles = (mi) =>
  mi >= 100 ? `${Math.round(mi).toLocaleString()} mi` : `${mi.toFixed(1)} mi`;

export const fmtNum = (v, digits = 0) => (v == null ? "–" : v.toFixed(digits));

// <input type="datetime-local"> wants local "YYYY-MM-DDTHH:mm".
export function toLocalInput(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
