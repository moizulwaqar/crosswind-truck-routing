import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the Django API runs on :8000; Vite proxies /api to it so the
// browser sees a single origin (same as production, where Django serves dist/).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.API_PROXY || "http://127.0.0.1:8000" },
  },
  build: { outDir: "dist", sourcemap: false },
});
