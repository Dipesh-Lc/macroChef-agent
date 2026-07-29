/// <reference types="vitest/config" />
import type { IncomingMessage } from "node:http";
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
  "/evals",
  "/docs",
  "/openapi.json",
];

const API_TARGET = "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      ...Object.fromEntries(
        API_PROXY_PREFIXES.map((prefix) => [prefix, { target: API_TARGET, changeOrigin: true }]),
      ),
      // "/chat" (ROADMAP.md Step 4.3) is BOTH a backend API prefix (`POST
      // /chat`, `GET /chat/{thread_id}`, `POST /chat/{thread_id}/message`,
      // `DELETE /chat/notes/{note_id}` -- app/api/routes_chat.py) AND the
      // SPA's own client route (`ChatPage`) -- unlike every prefix above,
      // these collide on the exact same path, so a blanket proxy entry
      // would swallow a browser's direct navigation/hard-refresh of `/chat`
      // (a bare GET) into a 404 against the backend, which has no such
      // route. (Production doesn't have this problem: `app/spa.py`'s
      // catch-all fallback only ever matches a GET no earlier, more
      // specific API route already claimed.) `bypass` lets exactly that one
      // case fall through to Vite's own SPA `index.html` serving instead of
      // being proxied; every other verb/sub-path under `/chat` is a real
      // backend call and proxies normally.
      "/chat": {
        target: API_TARGET,
        changeOrigin: true,
        bypass: (req: IncomingMessage) => {
          if (req.method === "GET" && (req.url === "/chat" || req.url === "/chat/")) {
            return req.url;
          }
          return undefined;
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
