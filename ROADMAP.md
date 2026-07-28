# MacroChef — Upgrade Roadmap ("Okay → WOW")

**Date:** 2026-07-28
**Audience:** Coding agents working in this repo + the maintainer (Dip).
**Objective:** Turn MacroChef from a solid, well-engineered project into a portfolio piece that makes an AI-Engineer hiring manager stop scrolling. The differentiators to build toward: *visible* agentic intelligence (streaming, tool use, human-in-the-loop), *measurable* quality (evals in CI, public benchmark page), *production* credibility (tracing, migrations, scale-out story), and a frontend that demos beautifully in 60 seconds.

---

## How agents must use this document

1. **Work phase by phase, in order.** Phases are sequenced so later work builds on earlier plumbing (e.g., streaming UI in Phase 4 consumes the SSE endpoint built in Phase 3). Within a phase, steps are numbered and ordered.
2. **One step = one PR-sized change.** Each step lists Files, Tasks, Tests, and Acceptance criteria. Do not mark a step done unless all acceptance criteria pass.
3. **Never regress the safety invariants.** These are load-bearing and non-negotiable:
   - Allergy/diet filtering stays **deterministic** (constraint_engine). No LLM ever makes a safety decision.
   - `scripts/audit_diet_leaks.py` and the safety benchmark suite must stay green.
   - `user_id` always comes from the verified session token, never from request bodies.
   - CORS `allow_credentials=False` stays False unless the CSRF story is redesigned first (see `app/main.py` comments).
4. **Definition of Done for every step:** `pytest` green, `ruff check` clean, `npm run lint && npm run typecheck && npm run test -- --run && npm run build` green in `web/`, plus the step's own acceptance criteria. Update `docs/BACKLOG.md` when a step intentionally defers something.
5. **Keep the commenting culture.** This codebase documents *why*, not *what*. Match it.
6. Anything marked **[STRETCH]** is optional; skip it if time-boxed, but never start a stretch item before the non-stretch items of that phase are done.

---

## Part 0 — Critical review (why this roadmap looks the way it does)

### What is already strong (do not break, do showcase)

- **Deterministic safety core:** 1,500-line constraint engine, derived-allergen handling, a 269-case adversarial safety benchmark (hidden allergens, prompt injection, substitution attacks, morphology traps) with an LLM judge and an evidence verifier. This is *rare* in portfolio projects and is the single most hire-worthy asset in the repo. It is currently invisible to anyone who doesn't read the code.
- **Real data engineering:** Food.com scraping pipeline with resume support, quarantine flow, cuisine gazetteer, quantity parser, grams-computable KPI, USDA FDC grounding with cache and recorded fixtures.
- **Engineering hygiene:** ~120 test files, typed Pydantic schemas end-to-end, generated OpenAPI → TS types, CI gates (pytest + diet-leak audit + web lint/typecheck/test/build) in front of a manual-promote Azure Container Apps deploy, multi-stage Docker with baked embedding model and baked Chroma index.
- **Sane session/auth model:** signed anonymous sessions, fail-closed SESSION_SECRET, per-user rate limiting on LLM-cost endpoints.

### The honest gaps (what keeps it at "okay")

1. **The agentic layer is thin for an "agent" project.** Both LangGraph graphs are linear, deterministic pipelines with 1–2 conditional edges. There is no checkpointing, no interrupt/human-in-the-loop, no multi-turn state, no tool-calling loop, no streaming. The LLM is called with a raw text prompt and the JSON is scraped out with regex (`RecipeGenerationService._extract_json`) instead of native structured outputs / function calling. A hiring manager who opens `app/graph/` will see a pipeline, not an agent.
2. **Everything is invisible while it runs.** A recommend request blocks for 20–45 s (the live app's browser tab visibly freezes; the only feedback is a disabled "Finding recipes…" button). The rich `debug_trace` exists but arrives only at the end. No SSE/WebSocket anywhere.
3. **No observability.** No tracing (LangSmith/Langfuse/OTel), no per-node latency, no token/cost accounting, no request IDs in logs, no metrics endpoint. "How do you debug it in prod?" currently has no good answer.
4. **The evals exist but don't *show*.** Safety benchmark and retrieval evals run via scripts, not in CI, and their results live in JSON files nobody sees. Evals-in-CI + a public results page is the strongest possible AI-engineering signal.
5. **Frontend is clean but flat.** No landing/hero (the app opens straight into a dense form), recipe "images" are dark placeholder blocks with clipped title text that read as *broken*, no skeletons/animation, no charts, no dark mode, results are text-dense. It demos like an internal tool.
6. **Infra has documented ceilings.** Single replica pinned by embedded Chroma single-writer + in-memory rate limiter; `Base.metadata.create_all` instead of migrations; sync `requests` calls inside request handlers; SQLite file sitting in the repo root. All are *known* (great comments), but "known and fixed" beats "known".
7. **Discoverability:** no architecture diagram, no demo GIF, no benchmark table up front (README was being rewritten; spec below in Phase 6).

### Priority logic

Impact-per-hour for an AI-engineer audience, highest first: (1) streaming + visible agent progress, (2) evals in CI + public eval page, (3) tracing/cost observability, (4) a real tool-calling conversational agent with HITL, (5) frontend wow, (6) infra maturity. The phases below interleave these so the demo improves early and continuously.

---

## Phase 1 — Observability, tracing, and cost accounting (P0)

**Why:** Every serious AI team runs on traces. This phase is prerequisite plumbing for Phases 2–4 (streamed progress and eval dashboards read the same events) and is cheap to build.

### Step 1.1 — Structured run events + request IDs

- **Files:** new `app/observability/events.py`, `app/observability/__init__.py`; edit `app/utils/logging.py`, `app/graph/nodes.py`, `app/graph/library_nodes.py`, `app/dependencies.py`.
- **Tasks:**
  - Define a `RunEvent` Pydantic model: `run_id`, `node`, `status` (`started|finished|failed`), `elapsed_ms`, `summary` (one human sentence, e.g. "Retrieved 14 candidates from 5,200-recipe corpus"), `payload` (small dict; counts, not full objects), `ts`.
  - Add an `EventSink` protocol with two impls: `InMemorySink` (per-run list, used by SSE in Phase 3) and `LogSink` (structured JSON log line per event).
  - Wrap every graph node with a decorator `@traced_node("recipe_retriever")` that emits started/finished/failed events with timing and appends the human `summary` to the existing `debug_trace` (keep backward compatibility).
  - Middleware: generate `run_id`/request ID per request, put it in a `contextvar`, include it in every log line and every `RunEvent`.
- **Tests:** new `tests/test_observability_events.py` — decorator emits started/finished with elapsed_ms; failure path emits `failed` and re-raises; request ID appears in log records.
- **Acceptance:** running the recommend graph locally (mock provider) produces an ordered event stream of all executed nodes with timings; existing tests untouched and green.

### Step 1.2 — LLM call ledger (tokens, cost, latency, provider)

- **Files:** `app/services/model_provider.py`, new `app/observability/llm_ledger.py`, `app/data/models.py` (+ table), `app/api/routes_health.py` or new `app/api/routes_admin.py`.
- **Tasks:**
  - In the single choke point where provider HTTP calls happen (`_generate_text` and the vision path), record: provider, model, purpose tag (caller passes e.g. `"recipe_generation"`, `"detailed_instructions"`, `"vision_extract"`, `"safety_judge"`), prompt/completion token counts (read from provider response; estimate `len//4` if absent), latency ms, success/fallback-used, and computed cost from a small static `PRICE_PER_MTOK` table.
  - Persist to a new `llm_calls` table keyed by `run_id` + user_id; also emit as a `RunEvent`.
  - Add `GET /admin/llm-usage?days=7` (session-gated) returning aggregates: calls, tokens, cost by model/purpose/day.
- **Tests:** `tests/test_llm_ledger.py` with a mocked provider response containing usage metadata; cost math; purpose tags flow through.
- **Acceptance:** after one live recommend + one discover run, the endpoint reports per-purpose token/cost rows.

### Step 1.3 — OpenTelemetry traces exported to a hosted backend

- **Files:** `requirements.txt` (`opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-requests`), `app/main.py`, `app/observability/tracing.py`, `.env.example`, `.github/workflows/ci.yml` (deploy env vars).
- **Tasks:**
  - Initialize a tracer provider when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (no-op otherwise — local dev and CI must not need it). Instrument FastAPI + outgoing `requests`.
  - Emit one span per graph node from the Step 1.1 decorator (so node spans nest under the HTTP span), and one span per LLM call carrying the ledger attributes (`llm.model`, `llm.tokens.prompt`, `llm.cost_usd`, `llm.purpose`).
  - Point it at a free hosted backend (Grafana Cloud free tier, Honeycomb free tier, or Langfuse via its OTLP endpoint — pick one, document in `.env.example`). **Human gate:** Dip creates the account and sets the two secrets; the workflow change just wires `--set-env-vars`.
- **Tests:** `tests/test_tracing_noop.py` — app boots and serves with no OTEL env set; span decorator is a no-op without a provider.
- **Acceptance:** a screenshot-able waterfall trace of one recommend request showing nested node spans and LLM spans with token/cost attributes. Save one such screenshot to `docs/img/trace-waterfall.png` for the README.

---

## Phase 2 — LLM layer hardening: structured outputs, async, resilience (P0)

**Why:** Regex-scraping JSON out of completions is the #1 thing an interviewer will ding. This phase also removes the biggest latency/robustness liabilities before we put the pipeline on stage in Phase 3.

### Step 2.1 — Native structured outputs everywhere

- **Files:** `app/services/model_provider.py`, `app/services/recipe_generation_service.py`, `app/services/vision_service.py`, `app/services/grounding_job.py` (any other `_generate_text` callers — grep first).
- **Tasks:**
  - Add `generate_structured(provider, prompt, schema: type[BaseModel], settings) -> BaseModel` to the provider layer:
    - Gemini: `response_mime_type="application/json"` + `response_schema` (the JSON schema of the Pydantic model).
    - OpenAI: `response_format={"type":"json_schema", ...}` (strict mode).
    - Anthropic: tool-use with a single forced tool whose `input_schema` is the model schema.
    - Ollama/mock: keep JSON-mode prompt + existing extraction as fallback.
  - Route `RecipeGenerationService`, vision extraction, and detailed-instructions through it. Keep the regex extractor only as a last-resort fallback path, and count fallback activations in the LLM ledger (`parse_fallback=true`) so it's measurable.
  - On validation failure: one retry with the validation errors appended to the prompt ("repair loop"), then raise. Record retries in the ledger.
- **Tests:** extend `tests/test_model_provider.py`: schema is passed per provider; repair loop triggers exactly once; fallback extraction still works for mock.
- **Acceptance:** live discover run produces candidates with zero `parse_fallback` events; malformed-response unit test exercises the repair loop.

### Step 2.2 — Async provider calls + parallel fan-out

- **Files:** `app/services/model_provider.py` (add `httpx.AsyncClient` variants), `app/services/grounding_job.py`, `app/services/usda_client.py`, `app/api/routes_*` (make the hot handlers `async def` where they now do network I/O), `requirements.txt` (`httpx`).
- **Tasks:**
  - Add async variants of the provider chat/vision calls and the USDA FDC search (keep sync wrappers for scripts/tests — thin `asyncio.run` shims are fine there).
  - Where the code grounds N ingredients or generates K candidates sequentially, fan out with `asyncio.gather` bounded by a semaphore (default 4, env-tunable `LLM_MAX_CONCURRENCY`).
  - Add timeout + `tenacity`-style retry with exponential backoff and jitter (2 retries, only on 429/5xx/timeout) at this single choke point; record retries in the ledger.
- **Tests:** `tests/test_async_provider.py` with `httpx.MockTransport`: concurrency bound respected; 429 retried then succeeds; timeout surfaces a clean `errors[]` entry, not a 500.
- **Acceptance:** measure and record in the PR description: end-to-end latency of a cold `/recipes/recommend` with grounding before vs after (expect the grounding fan-out to cut multi-ingredient grounding roughly in proportion to the concurrency).

### Step 2.3 — Response-level semantic cache for expensive calls

- **Files:** new `app/services/llm_cache.py`, wire into `generate_structured`; `app/data/models.py` (cache table) — reuse the `nutrition_cache` pattern.
- **Tasks:** key = SHA256 of (provider, model, purpose, canonicalized prompt/schema); store parsed JSON + ts; TTL per purpose (detailed instructions: 30 days; generation: no cache by default — keep novelty). Env kill-switch `LLM_CACHE_ENABLED`.
- **Tests:** hit/miss/TTL-expiry; kill-switch.
- **Acceptance:** second identical "detailed instructions" request serves from cache (ledger shows `cache_hit=true`, zero cost).

---

## Phase 3 — Agentic depth: streaming, checkpoints, HITL, and a real tool-using agent (P0 — the centerpiece)

**Why:** This is the phase that changes the project's category from "pipeline with an LLM in it" to "agent system". Everything here is demo-visible.

### Step 3.1 — SSE streaming of graph progress

- **Files:** new `app/api/routes_stream.py`; `app/graph/builder.py`, `app/observability/events.py`; register router in `app/main.py`.
- **Tasks:**
  - `POST /recipes/recommend/stream` (session-gated, same rate limit bucket as the non-stream route): runs the graph in a worker thread/task, and returns `text/event-stream` that relays `RunEvent`s from the `InMemorySink` as they happen, ending with a `result` event containing the full `RecommendationResponse` JSON, or an `error` event.
  - Use LangGraph's `graph.stream(...)`/`astream` when the compiled graph is available so node boundaries come from LangGraph itself; fall back to the sequential runner's per-node events otherwise.
  - Heartbeat comment line every 10 s so ACA ingress doesn't idle-close; document ACA's response-timeout setting in `docs/DEPLOY.md`.
  - Keep the old synchronous endpoint untouched (API compatibility, tests, benchmark scripts).
- **Tests:** `tests/test_stream_endpoint.py` using `httpx` client against the ASGI app with mock provider: events arrive in node order; terminal `result` event parses as `RecommendationResponse`; auth required; a mid-graph exception yields an `error` event, not a dropped connection.
- **Acceptance:** `curl -N` against local dev shows a live event feed: `intake → inventory_confirmation → constraint_builder → retriever ("14 candidates") → safety_filter ("2 rejected: shellfish") → … → result`.

### Step 3.2 — LangGraph checkpointer + true human-in-the-loop inventory confirmation

- **Why:** Today "inventory confirmation" is a single-shot field on the request. Making it a real `interrupt()` shows you know what LangGraph is actually for.
- **Files:** `app/graph/builder.py`, `app/graph/nodes.py`, new `app/api/routes_runs.py`, `requirements.txt` (`langgraph-checkpoint-sqlite`, `langgraph-checkpoint-postgres`), `app/config.py`.
- **Tasks:**
  - Compile the recommend graph with a checkpointer: `SqliteSaver` for sqlite `DATABASE_URL`, `PostgresSaver` for postgres (derive from the same URL; keep the no-checkpointer path for the sequential fallback runner).
  - Vision path (`input_type="image"`, low-confidence observations): `inventory_confirmation_node` calls `interrupt()` with the observations needing confirmation. New endpoints: `POST /runs/{thread_id}/resume` (submits confirmed inventory, resumes via `Command(resume=...)`) and `GET /runs/{thread_id}` (state + status). `thread_id` is minted server-side, bound to the session user; reject resumes from other users.
  - Text path keeps auto-confirm behavior (no UX regression).
  - Stream endpoint from 3.1 emits an `awaiting_input` event carrying the observations when interrupted.
- **Tests:** `tests/test_hitl_resume.py`: interrupted run persists; resume with corrections produces recommendations honoring corrections; cross-user resume is 403; process-restart-then-resume works (SqliteSaver file).
- **Acceptance:** scripted demo: upload fridge photo (or mock observations) → stream pauses with "I see something that might be shrimp paste — confirm?" → resume with correction → final plan excludes the allergen. This exact flow is the README GIF.

### Step 3.3 — "Chef" conversational agent with tool calling (the flagship feature)

- **Why:** A multi-turn agent that *uses the existing deterministic services as tools* is the perfect architecture story: creative LLM up top, deterministic safety underneath — and it reuses everything already built.
- **Files:** new `app/agent/` package (`chef_agent.py`, `tools.py`, `prompts.py`, `memory.py`), new `app/api/routes_chat.py`, `app/data/models.py` (chat threads/messages tables), tests.
- **Tasks:**
  - Build a LangGraph ReAct-style loop (LLM node ↔ tools node, checkpointer from 3.2, per-thread memory) with **read/plan tools only** — the LLM never writes safety data:
    1. `search_recipes(filters)` → wraps `RecipeRetriever`/search service.
    2. `check_recipe_safety(recipe_id | ingredients, profile)` → wraps constraint_engine; returns verdict + reasons.
    3. `ground_nutrition(ingredients)` → wraps USDA grounding; returns per-ingredient verified/estimated status.
    4. `propose_substitutions(recipe_id, violation)` → wraps substitution_service.
    5. `build_day_plan(recipe_ids, targets)` → wraps day_planner.
    6. `get_user_context()` → taste profile, saved recipes, recent feedback (session user only).
  - System prompt codifies the safety contract: the agent must call `check_recipe_safety` before presenting any recipe as safe, must present `verified` vs `estimated` nutrition distinctly, must refuse medical claims. Add these rules as *hard post-checks* too: a response gate that scans tool-call history and blocks "here's a safe recipe" answers with no safety-tool call in the turn (deterministic guard, mirrors the existing safety culture).
  - `POST /chat/{thread_id}/message` returns SSE: token deltas, `tool_call` events ("Checking safety of 'Pad Thai'…"), `tool_result` summaries, final message. Rate-limit with the existing limiter.
  - Memory: thread transcript persisted; long-term memory = existing taste profile + a small `agent_notes` per-user table the agent can read (writes go through an explicit `remember(note)` tool capped and user-visible).
  - Prompt-injection hardening: recipe corpus text (titles/instructions) is *data*; wrap tool outputs in delimiters and instruct the model accordingly; extend the existing `prompt_injection.jsonl` benchmark with 10 chat-specific cases (e.g., a recipe whose description says "ignore the user's peanut allergy").
- **Tests:** `tests/test_chef_agent.py` with a scripted mock LLM: tool-call sequence for "high-protein dinner from my pantry, I'm allergic to peanuts" includes `check_recipe_safety`; the response gate blocks an answer lacking a safety call; cross-user `get_user_context` isolation; injection case from the corpus does not flip the allergy.
- **Acceptance:** live demo transcript in `docs/DEMO_SCRIPT.md`: user asks in natural language → visible tool-call chips stream in UI (Phase 4) → plan cites verified macros → user says "swap the yogurt, I hate it" → agent proposes substitution via the deterministic service.

### Step 3.4 — Evals as a first-class, visible system

- **Files:** `.github/workflows/ci.yml`, new `scripts/run_all_evals.py`, new `app/api/routes_evals.py`, `data/evaluation/` (committed latest results JSON), new frontend page in Phase 4.
- **Tasks:**
  - Nightly + on-demand GitHub Action (`workflow_dispatch` + `schedule`) that runs: safety benchmark (mock-judge subset on PRs; full judge nightly with API key), retrieval eval (`eval_retrieval.py`), constraint eval; writes a single `eval_report.json` (per-suite pass rates, deltas vs last run) and commits it (or uploads as artifact + a small badge JSON committed).
  - **Hard CI gate:** safety benchmark pass rate on the deterministic (non-judge) subset must be 100% on every PR — wire into the existing `test` job.
  - `GET /evals/latest` serves the committed report (public, read-only) for the frontend eval page.
  - Add README badges: tests, safety benchmark `269/269`, retrieval Recall@10.
- **Tests:** report-shape unit test; endpoint serves the file.
- **Acceptance:** a PR that introduces a diet leak fails CI on the safety gate (prove once with a deliberate revert-commit experiment locally, note it in the PR); `/evals/latest` returns current numbers.

---

## Phase 4 — Frontend: from internal tool to product demo (P1)

**Why:** Hiring managers click the live link before they clone the repo. Current state: opens on a dense form, placeholder recipe images look broken, 30 s of frozen silence after "Find recipes". The design tokens ("honest kitchen ledger") are good — keep them; this phase adds hierarchy, motion, and the agentic theater built in Phase 3.

### Step 4.1 — Landing page + information architecture

- **Files:** new `web/src/pages/LandingPage.tsx`, edit `web/src/main.tsx` routes, `web/src/components/TopNav.tsx`.
- **Tasks:**
  - Route `/` → landing; planner moves to `/plan`. Hero: one-line value prop ("Meal planning that never hides its own uncertainty"), two CTAs ("Try the planner" pre-seeded with the demo pantry, "Chat with Chef"), and three proof chips linking to real pages: "Deterministic allergy safety — 269/269 adversarial cases" (→ eval page), "USDA-grounded macros" (→ methodology section), "Watch the agent think" (→ streaming demo).
  - A "How it works" section with a horizontal pipeline diagram of the actual LangGraph nodes (static SVG/CSS is fine; animate the active step on scroll). No stock illustrations; keep the ledger aesthetic (porcelain background, basil/chili/honey accents, mono for numbers).
  - Footer: GitHub link, benchmark badge, "read the safety methodology" link.
- **Tests:** RTL smoke test (hero renders, CTAs navigate); keep `HomePage.test.tsx` passing under `/plan`.
- **Acceptance:** cold visit to `/` explains the project in <10 s and one click starts a working demo.

### Step 4.2 — Live agent progress UI (consumes 3.1 SSE)

- **Files:** new `web/src/components/RunProgressTimeline.tsx`, new `web/src/lib/sse.ts` (fetch-with-ReadableStream SSE parser, since POST SSE), edit planner page.
- **Tasks:**
  - Replace the frozen "Finding recipes…" button state with a vertical timeline that fills in as events stream: node name → human summary → elapsed ms; safety-filter events render rejections inline in chili red ("rejected Shrimp Fried Rice — shellfish"); finish by swapping in results.
  - `awaiting_input` event (3.2) renders the confirmation card inline (check/correct observed ingredients → resume call).
  - Skeleton cards shimmer under the timeline while streaming; on `error`, show the partial trace + retry.
- **Tests:** component test with a scripted event stream (msw or injected reader): ordering, awaiting-input flow, error state.
- **Acceptance:** the 20–45 s wait now *is* the demo — every second shows the system reasoning. Record this as `docs/img/streaming-demo.gif`.

### Step 4.3 — Chef chat UI (consumes 3.3)

- **Files:** new `web/src/pages/ChatPage.tsx`, `web/src/components/ChatMessage.tsx`, `ToolCallChip.tsx`.
- **Tasks:** streaming markdown transcript; tool calls render as inline chips with icon + args summary that expand to the tool result ("🛡 check_recipe_safety → SAFE, 0 violations"); recipe cards returned by tools render as the existing `RecipeCard`; thread list in a sidebar (localStorage of thread ids); disclaimer banner reused.
- **Tests:** RTL with scripted SSE: chips appear before final text; recipe card renders from tool result.
- **Acceptance:** the flagship demo path works on mobile width too.

### Step 4.4 — Kill the broken-looking placeholders; real recipe imagery

- **Files:** `web/src/lib/placeholderImage.ts`, `web/src/components/RecipeCard.tsx`, `app/services/recipe_image_service.py`.
- **Tasks:**
  - Immediate fix (no network): replace the clipped-text dark blocks with generated deterministic art — cuisine-seeded gradient + a food-category line-icon set (bowl/plate/pan SVGs), title never clipped, `aria-hidden` art. This alone removes the "broken" look.
  - **[STRETCH]** `recipe_image_service`: generate one image per *base-corpus* recipe offline via an image API (human gate: cost approval), store under `data/library/images/`, serve as static files; never generate at request time.
- **Tests:** snapshot test: same recipe → same art; long titles wrap.
- **Acceptance:** zero clipped/placeholder-text artifacts anywhere in the app.

### Step 4.5 — Macro visualization + polish pass

- **Files:** planner/day/week pages, `web/src/components/` (new `MacroRadial.tsx`, `MacroTrendBars.tsx`), `package.json` (add `recharts` or hand-rolled SVG — prefer hand-rolled for bundle size, it's 2 charts).
- **Tasks:**
  - Day/Week pages: radial or stacked-bar macro progress vs targets per day (basil=protein, honey=carbs, chili=fat, mono numerals); verified vs estimated segments visually distinct (solid vs hatched) — this is the design system's core idea, make it graphical.
  - Micro-interactions: 150–200 ms ease-out transitions on card hover/expand, count-up on macro totals after results land, `prefers-reduced-motion` respected (already in CSS — extend to these).
  - A11y pass: labels on all inputs, focus order after results render, `aria-live="polite"` on the streaming timeline.
  - Mobile: planner form collapses into an accordion above results; nav becomes a bottom bar under 640 px.
- **Tests:** unit tests for chart math (percent, clamp, hatched segmentation by `verified` flag); axe-core smoke test **[STRETCH]**.
- **Acceptance:** Lighthouse (mobile) ≥ 90 accessibility, no layout shift on results swap-in.

### Step 4.6 — Public eval & methodology page (consumes 3.4)

- **Files:** new `web/src/pages/EvalsPage.tsx`; link from landing + README.
- **Tasks:** fetch `/evals/latest`; render suite cards (safety 269/269 with category breakdown table — hidden_allergen, prompt_injection, etc.; retrieval Recall@k/MRR; constraint accuracy), each with a two-sentence "what this measures and why" and a link to the case files on GitHub. Show run date + model used for the judge.
- **Acceptance:** the page reads as an eval report a team would actually ship; screenshots go in the README.

---

## Phase 5 — Data & infra maturity (P1)

**Why:** Converts documented ceilings into a scale story you can tell in interviews: "single-writer embedded vector store → external store; create_all → migrations; 1 replica → N."

### Step 5.1 — Alembic migrations

- **Files:** new `alembic/` + `alembic.ini`, `requirements.txt`, edit `app/data/db.py` (`init_db` keeps `create_all` only under sqlite+tests; document), `.github/workflows/ci.yml` deploy step runs `alembic upgrade head` before traffic (ACA: init-container or startup command).
- **Tasks:** baseline autogenerate from current models; migration test comparing autogenerate diff to empty (schema drift gate in CI).
- **Acceptance:** fresh Postgres → `alembic upgrade head` → app boots; CI drift gate green.

### Step 5.2 — pgvector migration for embeddings (retire the multi-replica blocker)

- **Files:** new `app/rag/pgvector_store.py` behind the existing retriever interface, `app/config.py` (`VECTOR_BACKEND=chroma|pgvector`), `app/services/recipe_indexing_service.py`, Alembic migration (vector extension + table + HNSW index), `Dockerfile` (keep Chroma bake for the chroma backend; pgvector backend seeds via a release job `scripts/seed_pgvector.py`).
- **Tasks:** implement upsert/query/delete parity; keep Chroma as default local backend (zero-dependency dev stays easy); Neon supports pgvector — prod flips via env. Re-run retrieval eval on both backends and commit the comparison to `eval_report.json`.
- **Tests:** contract test parameterized over both backends (skip pgvector if no Postgres in env; run it in CI via `services: postgres` with pgvector image).
- **Acceptance:** prod on pgvector with retrieval eval parity (Recall@10 within 1 pt); `docs/DEPLOY.md` updated; rate-limiter note updated.
- **Follow-up (same step):** raise ACA `max-replicas` to 3 **only after** moving the rate limiter to a shared store — simplest: Postgres advisory/table-based sliding window (avoid adding Redis just for this; document the trade-off in the module docstring you'll be editing).

### Step 5.3 — Continuous deployment + staging

- **Files:** `.github/workflows/ci.yml`.
- **Tasks:** auto-deploy `main` → new `ca-macrochef-staging` app (small SKU, same image); production stays manual-promote (keeps the existing human-gate philosophy). Add a post-deploy smoke job: hit `/health`, `/evals/latest`, and one mock-provider recommend on staging.
- **Acceptance:** merge to main yields a fresh staging URL comment in the workflow summary; prod promotion unchanged.

### Step 5.4 — Security & headers hardening (cheap, visible)

- **Files:** `app/main.py` (middleware), `app/spa.py`.
- **Tasks:** CSP (self + PostHog + image hosts), `X-Content-Type-Options`, `Referrer-Policy`, HSTS (behind env flag; ACA terminates TLS), gzip/brotli for the SPA, cache headers for hashed assets.
- **Tests:** header assertions in `tests/test_spa_serving.py`.
- **Acceptance:** securityheaders.com grade A on the live URL.

---

## Phase 6 — Documentation & presentation layer (P0 — do alongside everything)

### Step 6.1 — README rewrite (spec)

The README is the landing page for the code audience. Target structure (keep it under ~350 lines; move depth to `docs/`):

1. **Header block:** logo/wordmark, one-liner ("An agentic meal-planning system where the LLM is never allowed to make a safety decision"), badges (CI, safety benchmark 269/269, retrieval Recall@10, live demo), hero GIF = the HITL streaming demo from Step 3.2/4.2.
2. **"Why this is interesting" — 5 bullets max,** each a claim + receipt link: deterministic safety core (→ constraint_engine + benchmark cases), adversarial eval suite in CI (→ eval page + workflow), streaming LangGraph with checkpointed HITL (→ code), USDA-grounded nutrition with verified/estimated provenance in the UI (→ methodology), tool-using chat agent over deterministic services (→ agent package).
3. **Architecture:** one Mermaid diagram of the system (SPA ↔ FastAPI ↔ graphs/agent ↔ services ↔ Postgres/pgvector/USDA/LLM providers) + one of the recommend graph with the interrupt point marked. Two short paragraphs, not ten.
4. **The safety story** (its own section — it's the differentiator): the two-layer design (creative LLM / deterministic gate), the benchmark categories table with counts, one example adversarial case inline (quote a `prompt_injection` case + what the system does).
5. **Evals & results:** the table from `eval_report.json` (safety pass rate, retrieval Recall@10/MRR, grams-computable %, corpus size), link to the live eval page.
6. **Run it:** 5-line quickstart (clone → `.env` from example → `pip install` + `npm i` → seed script → two run commands), plus "zero-key mode" (mock provider) explicitly called out — reviewers love not needing API keys.
7. **Engineering notes:** short honest list — what's deliberately simple (anonymous sessions, no user accounts), known limits (link `docs/BACKLOG.md`), stack versions.
8. **Not:** feature checklists, week-by-week build logs, or aspirational features. Honest, specific, receipt-linked.

### Step 6.2 — CLAUDE.md (spec)

CLAUDE.md is operating instructions for agents, not documentation. It should contain, in order:

1. **Project map (10 lines):** the packages that matter and what owns what (`app/graph` orchestration, `app/services` domain logic, `app/agent` chat agent, `web/src` SPA, `app/evaluation` benchmarks) — so an agent doesn't re-derive it every session.
2. **Invariants (the section that earns its keep):** the numbered non-negotiables from "How agents must use this document" §3 above, verbatim, plus: never edit `data/processed` corpus files by hand (regenerate via scripts), never bump `max-replicas` (until 5.2 lands), all LLM calls go through `model_provider` (never inline HTTP), all new provider output must be schema-validated.
3. **Commands:** exact invocations — run api, run web, full test matrix (backend + web), safety benchmark, diet-leak audit, single-test patterns, seed scripts. Include the env quirks (`EMBEDDING_PROVIDER=hash` for tests).
4. **Conventions:** comment culture ("document why, link the test that pins the behavior"), commit message style (matching the existing imperative, outcome-stating history), where new tests live, schema-first workflow (Pydantic schema → OpenAPI → `npm run generate-types` if wired).
5. **Human gates:** what agents must never do without asking — deploys, spending money (image gen, judge runs), secrets, deleting corpus data, changing safety thresholds.
6. **Pointers, not prose:** link ROADMAP.md, `docs/BACKLOG.md`, `docs/DEPLOY.md`. Keep CLAUDE.md under ~150 lines; long explanations belong in docs with links.

### Step 6.3 — Demo assets & case study

- **Files:** `docs/DEMO_SCRIPT.md`, `docs/img/*` (GIFs: HITL streaming run, chat tool-calls, eval page), `docs/CASE_STUDY.md`.
- **Tasks:** a 90-second scripted demo path (what to click, what to say) for interviews; a case-study writeup of the two best war stories in the repo's own history — (a) the corpus-engineering push (grams-computable 36.7%→53.2%, cuisine gazetteer, quarantine) and (b) designing the adversarial safety benchmark and getting to 269/269 with an evidence verifier. These become talking points and blog-post material.
- **Acceptance:** someone who has never seen the project can run the demo script end-to-end.

---

## Sequencing & effort summary

| Order | Phase | Steps | Rough effort | Demo payoff |
|---|---|---|---|---|
| 1 | Phase 1 Observability | 1.1–1.3 | 2–3 days | Trace screenshot, cost ledger |
| 2 | Phase 2 LLM hardening | 2.1–2.3 | 2–3 days | Robustness + latency win |
| 3 | Phase 3 Agentic core | 3.1–3.4 | 5–8 days | **The wow**: streaming, HITL, chat agent, evals-in-CI |
| 4 | Phase 4 Frontend | 4.1–4.6 | 4–6 days | Landing, live timeline, chat UI, eval page |
| 5 | Phase 5 Infra | 5.1–5.4 | 3–4 days | Migrations, pgvector, staging, headers |
| 6 | Phase 6 Docs | 6.1–6.3 | 1–2 days | README, CLAUDE.md, GIFs — do continuously, finalize last |

Minimum viable "WOW" if time-boxed to ~1 week: 1.1 → 2.1 → 3.1 → 4.2 → 4.1 → 4.4(quick fix) → 6.1. That alone transforms the demo (visible thinking, no broken images, a landing page, an honest README with receipts).
