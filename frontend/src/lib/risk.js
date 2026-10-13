// Mirrors backend/trips/risk.py RiskLevel. Colors are the only place risk is
// encoded visually, so every component reads them from here.
export const LEVELS = [
  { level: 0, label: "Low", color: "#3A9D5D", ink: "#ffffff" },
  { level: 1, label: "Moderate", color: "#E3B505", ink: "#2a2200" },
  { level: 2, label: "High", color: "#EE7F2D", ink: "#2b1300" },
  { level: 3, label: "Severe", color: "#D1342B", ink: "#ffffff" },
  { level: 4, label: "No Travel", color: "#6A2C91", ink: "#ffffff" },
];

export const levelOf = (n) => LEVELS[Math.max(0, Math.min(4, n ?? 0))];

const hexToRgb = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
export const LEVEL_RGB = LEVELS.map((l) => hexToRgb(l.color));

// Continuous ramps for the wind / rain / snow heatmap layers. Stops are placed
// on the risk thresholds so a color change means a category change.
export const RAMPS = {
  wind: {
    unit: "mph",
    stops: [
      [10, [180, 214, 240], 0],
      [25, [104, 168, 222], 0.35],
      [35, [44, 104, 190], 0.5],
      [45, [36, 46, 150], 0.6],
      [55, [106, 44, 145], 0.7],
    ],
  },
  rain: {
    unit: "in/hr",
    stops: [
      [0.01, [150, 220, 170], 0],
      [0.1, [72, 180, 110], 0.35],
      [0.25, [230, 190, 40], 0.5],
      [0.5, [220, 90, 40], 0.6],
      [1.0, [170, 30, 60], 0.7],
    ],
  },
  snow: {
    unit: "in/hr",
    stops: [
      [0.05, [210, 225, 245], 0],
      [0.5, [150, 180, 235], 0.4],
      [1.0, [100, 130, 220], 0.5],
      [2.0, [90, 70, 190], 0.6],
      [3.0, [150, 50, 170], 0.7],
    ],
  },
};

export function rampColor(ramp, v) {
  const s = ramp.stops;
  if (v <= s[0][0]) return [s[0][1], 0];
  for (let i = 1; i < s.length; i++) {
    if (v <= s[i][0]) {
      const t = (v - s[i - 1][0]) / (s[i][0] - s[i - 1][0]);
      const a = s[i - 1][1], b = s[i][1];
      return [
        [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t],
        s[i - 1][2] + (s[i][2] - s[i - 1][2]) * t,
      ];
    }
  }
  const last = s[s.length - 1];
  return [last[1], last[2]];
}
