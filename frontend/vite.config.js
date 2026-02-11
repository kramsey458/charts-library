import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://localhost:5000";

export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      usePolling: true,
      interval: Number(process.env.CHOKIDAR_INTERVAL || 300),
    },
    proxy: {
      "/api": apiProxyTarget,
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.js"],
  },
});
