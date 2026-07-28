# HUMAN_INPUTS.md — action items that need Dip, not an agent

Per CLAUDE.md's human gates (secrets & accounts, money, public actions,
licenses, safety regressions), some ROADMAP steps have a code portion an
agent can finish and a "create an account / paste a secret / spend money"
portion that only the maintainer can do. This file is the durable home
for those outstanding items — cheaper than burying them in commit
messages or BACKLOG.md entries that are really about deferred code.

When an item is resolved, delete it (git history is the archive).

---

## H1. OpenTelemetry hosted backend account + secrets (ROADMAP Step 1.3)

- **What's blocked:** the code path (conditional tracer-provider init,
  FastAPI + `requests` instrumentation, node/LLM spans) ships without
  needing this — it's a documented no-op when `OTEL_EXPORTER_OTLP_ENDPOINT`
  is unset, so local dev and CI are unaffected. What's blocked is the
  *live* trace: exporting real spans to a hosted backend, screenshotting
  a waterfall trace for the README, and (if wired into CI) the deploy
  step's env vars actually having values.
- **Recommended backend: Honeycomb.** Chosen (via an advisor consult,
  2026-07-28) over Grafana Cloud and Langfuse because its OTLP setup is
  literally two env vars with no vendor SDK, a generous free tier (20M
  events/month), and nothing about the code changes if you later prefer
  a different backend — it's standard OTLP throughout. Langfuse is a
  reasonable alternative if you want more AI-specific trace semantics
  (worth it if you already use it elsewhere); Grafana Cloud's OTLP auth
  is one extra moving part (Basic auth from an Instance ID + token) for
  no benefit here.
- **What to do:**
  1. Create a free Honeycomb account at honeycomb.io, create an
     environment, grab its API key.
  2. Set two secrets — the code (`app/observability/tracing.py`,
     `app/config.py`) lands on the standard OTel env var names, no
     Honeycomb-specific ones:
     - `OTEL_EXPORTER_OTLP_ENDPOINT` = `https://api.honeycomb.io` (the app
       appends `/v1/traces` itself; see `.env.example`)
     - `OTEL_EXPORTER_OTLP_HEADERS` = `x-honeycomb-team=<API_KEY>`
       (comma-separated `key=value` pairs, OTel spec format; optionally
       add `,x-honeycomb-dataset=<name>`)
  3. For local/dev: add them to your `.env`. For prod: add them as GitHub
     repo secrets named exactly `OTEL_EXPORTER_OTLP_ENDPOINT` and
     `OTEL_EXPORTER_OTLP_HEADERS` — the deploy workflow
     (`.github/workflows/ci.yml`'s `deploy` job) already wires
     `az containerapp secret set` + `--set-env-vars` for them (same
     optional-secret pattern as `POSTHOG_API_KEY`: an unset GitHub secret
     just deploys with tracing off, not a broken deploy). Nothing left
     to change in the workflow once the two secrets exist.
  4. Run one real `/recipes/recommend` request against a deployment with
     the env vars set, screenshot the resulting waterfall trace in the
     Honeycomb UI, save it to `docs/img/trace-waterfall.png` for the
     README (per Step 1.3's acceptance criteria).
- **Cost:** $0 on Honeycomb's free tier for this project's traffic scale.

---
