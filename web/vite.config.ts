/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev-only proxy: forwards exactly the backend API prefixes to the FastAPI
// dev server (`python -m uvicorn app.main:app --port 8000`). Deliberately
// NOT `/shared` -- that is a client-side React Router route
// (`/shared/:shareId`), not a backend prefix; proxying it would swallow the
// SPA's own route in dev. See app/spa.py's SPA_ROUTES for the authoritative
// list of client routes this must never collide with.
const API_PROXY_PREFIXES = [
  "/health",
  "/api-info",
  "/session",
  "/inventory",
  "/recipes",
  "/library",
  "/feedback",
  "/plan",
  "/tools",
  "/share",
  "/docs",
  "/openapi.json",
];

const API_TARGET = "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(
      API_PROXY_PREFIXES.map((prefix) => [prefix, { target: API_TARGET, changeOrigin: true }]),
    ),
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
