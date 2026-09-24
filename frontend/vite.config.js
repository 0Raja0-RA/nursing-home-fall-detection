import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy API calls ke backend saat development
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      // Proxy WebSocket
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
});
