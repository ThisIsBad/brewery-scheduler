import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

const backendUrl = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["pwa-192.png", "pwa-512.png", "pwa-maskable-512.png"],
      manifest: {
        name: "Brauerei Kellerblick",
        short_name: "Kellerblick",
        description:
          "Sudplanung und Kellerbuch — Tanks, Umdrücken, Fassabfüllung.",
        lang: "de",
        start_url: "/",
        display: "standalone",
        background_color: "#f5f3ef",
        theme_color: "#226644",
        icons: [
          { src: "pwa-192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "pwa-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // Offline READ cache (ROADMAP §2.8): API GETs go network-first with
        // a short timeout so radio dead spots fall back to the last known
        // cellar state quickly. Mutations are NOT intercepted — the queued-
        // mutation strategy lands with TanStack Query (issue #10); Workbox
        // Background Sync is deliberately avoided (no iOS support, silently
        // drops 409 replies).
        runtimeCaching: [
          {
            urlPattern: ({ url, request }) =>
              request.method === "GET" && url.pathname.startsWith("/api/"),
            handler: "NetworkFirst",
            options: {
              cacheName: "api-read-cache",
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 * 24 * 7 },
            },
          },
        ],
      },
    }),
  ],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": { target: backendUrl, changeOrigin: true },
      "/health": { target: backendUrl, changeOrigin: true },
    },
  },
});
