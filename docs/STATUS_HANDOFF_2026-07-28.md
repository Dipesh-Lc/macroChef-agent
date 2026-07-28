# Status handoff — ROADMAP execution, 2026-07-28 overnight session

## If you only read this

**All of Phase 1 (1.1, 1.2, 1.3), all of Phase 2 (2.1, 2.2, 2.3), Step
3.1 (SSE streaming) are done, merged to `main`, and independently
verified green** (full backend `pytest`, `ruff`, full web matrix where
applicable), each on its own commit series. Plus, pulled forward because
they had no backend dependency: **Step 4.1+4.4** (landing page, killed
`placehold.co`), **Step 4.5** (macro charts + mobile nav + a11y polish),
**Step 3.4** (evals as a hard CI gate + `/evals/latest`), **Step 5.4**
(security headers). Plus docs: `ROADMAP.md`/`docs/BACKLOG.md` now
tracked, `docs/HUMAN_INPUTS.md` (your action items),
`docs/PHASE3_HITL_CHEF_SPEC.md` (pre-implementation spec for the two
steps deliberately NOT built: 3.2 HITL checkpointer, 3.3 Chef agent —
both safety-adjacent, held for a real design consult with you present).

**Session hit two account API usage limits** (first around 4:20am, a
second larger one around 3pm Europe/Berlin) — both self-resolved after a
wait/retry, no work was lost either time (verified via git before
retrying). One real mistake on my part, described below, with no lasting
damage but a genuine small loss.

I kept going past the original stopping point (Step 3.1) because you
said "keep going" — now working through Steps 4.2, 4.6, and 5.1, which
Step 3.1/3.4 just unblocked. This doc will be updated again as those land.

## An incident worth knowing about

Mid-session, I ran `git checkout roadmap/4.5... -- .` intending to
preview a merge conflict — that command instead overwrote the whole
working tree from that branch. I recovered with `git reset --hard HEAD`,
which fixed everything committed but **permanently lost two pre-existing
uncommitted edits that were sitting in your working tree before this
session started**: a hand-edit to `docs/DEPLOY.md` (the committed
version didn't yet mention `/evals/latest`; the lost edit did — likely
prep work for this exact roadmap) and a regenerated
`data/processed/grounding_report.md` (low-stakes, it's a generated file,
rerun `scripts/ground_corpus.py --report-path ...` if you need a fresh
one). Neither was ever committed by anyone, so there's no git object to
recover from. I resolved the actual TopNav.tsx merge conflict that
prompted this properly afterward (a normal `git merge` + manual conflict
resolution). Flagging plainly rather than burying it — this is the one
thing tonight that isn't fully recoverable.

## Strategy this session (advisor-approved, you weren't available)

You said to implement ROADMAP.md, parallelize for speed, and consult the
advisor for any decision that would normally need you since you'd be
asleep. One advisor strategy consult ran before starting; I followed its
four recommendations:

1. **Scope**: work Phase 1 → Phase 2 → Step 3.1 sequentially on a
   backend track (each touches shared files, so strict ordering avoided
   collisions), hard stop before Step 3.2/3.3 — write a spec instead of
   code, because they're a new LLM-driven attack surface next to the
   safety-gate invariant and CLAUDE.md already classifies "the Chef
   agent's tool gating and response gate" as FULL TREATMENT (mandatory
   advisor consult *before* an executor starts, which can't happen
   meaningfully with you asleep and several real product decisions
   unmade — see the five open questions in the spec doc).
2. **OTel backend**: **Honeycomb**, logged in `docs/HUMAN_INPUTS.md` H1.
   The code path is fully built (Step 1.3) and is a true no-op without
   the env vars — the account/secrets/screenshot is still on you.
3. **Parallelization**: backend-core track stayed strictly sequential
   (files overlap between consecutive steps); frontend work with zero
   backend dependency ran in parallel worktrees; docs ran independently.
   Once 3.1/3.4 landed, they unblocked more parallel frontend work
   (4.2, 4.6) — same principle applied again rather than re-consulting.
4. **Stopping condition**: only ever land on a green, committed,
   acceptance-criteria-met step boundary; write this doc regardless of
   how far I get. Held throughout — every step below has independent
   verification evidence, not just the sub-agent's self-report.

## Done — with evidence (chronological within each phase)

### Phase 1 — Observability
- **1.1** Structured run events + request IDs. `app/observability/events.py`:
  `RunEvent`, `EventSink`/`InMemorySink`/`LogSink`, `@traced_node` on all
  19 graph nodes, request-id middleware.
- **1.2** LLM call ledger. New `llm_calls` table, real per-provider token
  extraction (caught that this app's OpenAI path uses the Responses API,
  not Chat Completions), `GET /admin/llm-usage?days=7` (session-gated,
  **not** user-scoped — see BACKLOG I3, deliberate for a single-user demo).
- **1.3** OpenTelemetry tracing. `app/observability/tracing.py` — true
  no-op unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set; spans on graph nodes
  and LLM calls when enabled. CI wired defensively (missing secret →
  tracing off, not a broken deploy).

### Phase 2 — LLM layer hardening
- **2.1** Native structured outputs. New `generate_structured()` in
  `model_provider.py`: Gemini `response_schema`, OpenAI Responses-API
  `text.format` json_schema (verified against the installed SDK, not the
  Chat Completions shape the roadmap text implied), Anthropic forced
  tool-use, Ollama/mock JSON-mode-prompt fallback. One-shot repair loop
  on validation failure. Routed recipe generation, vision extraction,
  and detailed instructions through it; removed the old duplicate
  regex/brace-scan vision extractor entirely.
- **2.2** Async provider calls + fan-out. Async USDA client (mirrors the
  existing two-axis retry design), async `grounding_job.run_grounding_async`
  fanning out the actual sequential bottleneck (the corpus grounding
  loop — confirmed live `/recipes/recommend` doesn't call USDA at
  request time at all, so that literal roadmap benchmark didn't apply;
  measured the real one instead). **Measured 3.76x speedup** on a
  150-recipe subset (102.8s → 27.4s, concurrency=4).
- **2.3** Semantic response cache. New `llm_calls`-adjacent `LLMCacheEntry`
  table, SHA256 key over `(provider, model, purpose, canonicalized
  prompt, schema)`, TTL per purpose (30d for detailed instructions, no
  cache for recipe generation — "keep novelty" per the roadmap), kill
  switch `LLM_CACHE_ENABLED`.

### Step 3.1 — SSE streaming (the centerpiece)
New `POST /recipes/recommend/stream`: relays live `RunEvent`s as SSE,
ends with a `result` or `error` event, 10s heartbeats for ACA's ingress
timeout. Runs the unmodified graph in a worker thread while polling a
per-request event sink — chosen over driving off LangGraph's native
`.stream()` because the graph can fall back to a non-LangGraph sequential
runner on an import failure, and both paths needed one event mechanism,
not two. Also narrowed a real bug found along the way: `builder.py`'s
graph-compile step had a bare `except Exception` around the *entire*
build (not just the import, unlike the equivalent library-graph builder)
that would have silently swallowed any real construction error and
degraded to an untraced fallback with zero logging. The old sync
`/recipes/recommend` endpoint is provably untouched (its isolation test
suite re-run unmodified and still passes).

### Pulled forward (no backend dependency, ran in parallel)
- **4.1+4.4** New landing page at `/` (planner moved to `/plan`), killed
  `placehold.co` everywhere — found and removed it server-side too
  (`recipe_image_service.py` and two callers), not just in the frontend.
- **4.5** Hand-rolled SVG macro radial/trend-bar charts (no new chart
  dependency, per the roadmap's own preference), mobile bottom-nav +
  accordion, hover/count-up micro-interactions respecting
  `prefers-reduced-motion`, focus management, `aria-expanded` on
  `NutritionBreakdown`. Honestly documented that neither `DayPlan` nor
  `WeeklyPlan` currently carries a per-macro verified/estimated flag, so
  the hatch-pattern mechanism exists and is tested but every current
  caller renders solid — a real backend gap noted, not fabricated data.
- **3.4** Evals as a visible, CI-enforced system. New
  `scripts/run_all_evals.py` (mock-provider-only, no `--provider` flag
  exists at all — verified this can't trigger real spend), new hard CI
  gate on the **adjudicated-true** count (not the raw judge-flagged
  count, which is expected to have occasional false positives — gating
  on that directly would fail every PR). **Found and fixed a real
  pre-existing bug**: neither this script nor the original
  `run_safety_benchmark.py` ever called `init_db()`, so a fresh sqlite
  file made every case silently serve 0 recipes — a false-negative
  safety gate. Proved the gate works with a real fault-injection
  experiment (temporarily made `validate_recipe` admit everything,
  confirmed the gate fails, reverted cleanly). `GET /evals/latest` is
  public/read-only, serving a typed "not yet generated" response until a
  real `data/evaluation/eval_report.json` is committed (deliberately
  not committed yet — a partial/rushed run would misrepresent itself as
  authoritative).
- **5.4** Security headers. CSP (verified PostHog needs zero CSP
  allowance — it's server-side only, no `posthog-js` anywhere in `web/`),
  `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`,
  `Permissions-Policy`, HSTS behind a new `ENABLE_HSTS` flag (default
  off), gzip, and confirmed cache headers for hashed assets already
  existed correctly.

### Docs
- `ROADMAP.md`/`docs/BACKLOG.md` tracked (were sitting untracked).
- `docs/HUMAN_INPUTS.md` — durable home for "code ships, account/secret/
  purchase needs you." Currently: **H1** (Honeycomb OTel account — code
  ready, waiting on you) and **H2** (the nightly real-judge benchmark run
  — deliberately not built at all, no code, no schedule trigger; needs a
  cost estimate + your approval before it exists, per CLAUDE.md's money
  gate).
- `docs/PHASE3_HITL_CHEF_SPEC.md` — 688-line pre-implementation spec for
  3.2/3.3, with five open design questions that are genuinely yours to
  decide (multi-recipe response-gate semantics, `remember()` tool
  cap/lifecycle, SqliteSaver vs PostgresSaver default, whether
  `ground_nutrition` needs its own rate-limit bucket, 403-vs-404 for
  cross-user thread isolation — checked, no existing precedent to copy).

## NOT done, and why

- **3.2, 3.3** — deliberately deferred, spec-ready, needs you. See above.
- **4.2, 4.3, 4.6** — 4.2 (live SSE progress UI) and 4.6 (public eval
  page) were blocked on 3.1/3.4 landing; now unblocked, in progress as
  of this doc revision (check task list / commit log for current state).
  4.3 (chat UI) stays blocked on 3.3.
- **Phase 5 remainder** (5.1 Alembic, 5.2 pgvector, 5.3 staging CD) — 5.1
  in progress as of this revision; 5.2/5.3 not started, lower priority
  per the roadmap's own impact-per-hour ordering.
- **Phase 6** (README/CLAUDE.md rewrite, demo GIFs, case study) — not
  started; the roadmap says do this continuously and finalize last, and
  tonight's priority was the higher-impact phases first.

## Recommended next steps for you

1. `docs/HUMAN_INPUTS.md` — Honeycomb account (H1), and a real decision
   on whether/when to spend on a nightly judge run (H2).
2. Read `docs/PHASE3_HITL_CHEF_SPEC.md` §3 before anyone starts 3.2/3.3
   — those five questions are real product calls, not implementation
   details.
3. `data/evaluation/eval_report.json` doesn't exist yet — run
   `python scripts/run_all_evals.py` for real (or let it happen in CI on
   the next PR) so `/evals/latest` has real content once you want the
   Phase 4.6 eval page live.
4. The `docs/DEPLOY.md`/`grounding_report.md` incident above — no action
   needed unless you specifically remember what was in the lost
   `DEPLOY.md` edit and want to redo it by hand.
