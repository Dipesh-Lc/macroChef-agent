# BACKLOG.md — deferred work ("noticed, not fixed")

Recreated 2026-07-28 (the previous file was removed from the repo; entries
below are re-seeded from the codebase review that produced `ROADMAP.md`).

**Rules for this file (from CLAUDE.md "Default to backlog"):**

- Every entry must be actionable later without re-deriving context: file
  paths, what was already decided, and acceptance criteria. Not a vibe,
  not a bare TODO.
- Work that a `ROADMAP.md` step already requires does NOT belong here —
  it belongs in that step. This file is for everything noticed along the
  way that no roadmap step covers.
- When an entry is done, delete it (git history is the archive). When an
  entry gets absorbed into a roadmap step, note the step and delete it.

---

## Backend

### B1. `init_db()` called on every service invocation

- **Where:** `app/services/memory_service.py` (lines ~28, 47, 63, 257 —
  `save_feedback`, taste-profile paths).
- **Problem:** `init_db()` runs `Base.metadata.create_all` per call. It's
  idempotent but issues schema-inspection queries on hot paths, and it
  duplicates the lifespan-time `init_db()` in `app/main.py`.
- **Fix:** remove the per-call invocations; keep the single lifespan call.
  Scripts that import these services directly (e.g. seeds) should call
  `init_db()` themselves once.
- **Accept:** grep shows `init_db()` only in `app/main.py` lifespan +
  scripts; full pytest green. Superseded partly by ROADMAP 5.1 (Alembic
  owns schema creation in prod) — do together if convenient.

### B2. `RecipeGenerationService` imports a private provider function

- **Where:** `app/services/recipe_generation_service.py:9` —
  `from app.services.model_provider import _generate_text  # type: ignore[attr-defined]`.
- **Problem:** reaches into a private symbol with a suppressed type error;
  the provider module has no public text-generation API.
- **Fix:** absorbed by ROADMAP 2.1's `generate_structured(...)` public
  API. If 2.1 slips, the minimal fix is renaming to a public
  `generate_text(...)` with a docstring stating the schema-validation
  requirement.
- **Accept:** no `_`-prefixed cross-module imports; no
  `attr-defined` ignores in services.

### B3. Non-root user in the Docker image

- **Where:** `Dockerfile` (final stage; the HF_HOME comment explicitly
  notes the image never switches USER).
- **Decision already made:** keep `HF_HOME=/app/.cache/huggingface`; just
  chown it plus `data/` to a created `appuser` and add `USER appuser`
  before `CMD`.
- **Accept:** `docker compose up --build` serves normally; `/health` green;
  Chroma index writable at runtime (`POST /library/reindex` works).

### B4. Shrink the ~3.4 GB image (CPU-only torch)

- **Where:** `Dockerfile`, `requirements.txt` (`sentence-transformers`
  pulls full CUDA torch).
- **Fix:** install torch from the CPU index
  (`pip install torch --index-url https://download.pytorch.org/whl/cpu`)
  before `-r requirements.txt`, or split a `requirements-docker.txt`.
  Expect roughly 2 GB saved; faster ACR pushes and ACA cold starts.
- **Accept:** image builds, index bake step still asserts non-empty,
  embedding parity spot-check (same vector for a fixed string as the
  current image within float tolerance).

### B5. Session cookie hardening audit

- **Where:** `app/api/routes_session.py`, `app/dependencies.py`.
- **Task:** one pass verifying `mc_session` sets `HttpOnly`, `Secure`
  (prod), and an explicit `SameSite` value, with a test pinning each
  attribute (extend `tests/test_session_endpoint.py`). Do NOT touch
  `allow_credentials` (CLAUDE.md invariant #4). FULL TREATMENT tier
  (auth).
- **Accept:** attributes asserted in tests; comment block explains the
  CSRF interplay next to the existing CORS comment.

### B6. `GraphRun`/checkpoint storage growth for never-interrupted stream runs

- **Where:** `app/api/routes_stream.py`'s `_stream_recommend` (the
  `hitl_capable` branch, ROADMAP 3.2) calls `app.api.routes_runs.
  invoke_hitl_graph` for every `POST /recipes/recommend/stream` request
  once `langgraph` is installed — not just ones that end up pausing on a
  low-confidence inventory observation. `app.data.models.GraphRun` mints
  one ownership row per call, and the shared checkpointer
  (`app.graph.builder._get_checkpointer`, sqlite or Postgres) persists a
  full checkpoint per run, even for plain-text requests that never
  interrupt and are never resumed.
- **Problem:** unbounded growth of the `GraphRun` table and the
  langgraph-checkpoint tables (`checkpoints`, `checkpoint_blobs`,
  `checkpoint_writes`) for runs nobody will ever resume, plus extra load
  on the single lock-guarded sqlite/Postgres connection compared to the
  pre-3.2 uncheckpointed path. Flagged by the ROADMAP 3.2 second advisor
  review (approved overall) as a real gap in the step's own
  `routes_stream.py` docstring, which already promised this entry.
- **Fix:** some retention/cleanup policy for completed, never-resumed
  `GraphRun` rows and their checkpoint rows (e.g. a periodic sweep
  deleting rows past a TTL where `status != "awaiting_input"`), or
  confirm via measurement that row-growth at expected traffic is
  negligible and defer further.
- **Accept:** either a documented, tested cleanup policy exists, or a
  measured growth-rate note justifying deferral is added here.

### B7. `POST /chat` (thread creation) has no rate limit

- **Where:** `app/api/routes_chat.py`'s `create_chat_thread` — session-gated
  via `get_session_user` only, unlike `POST /chat/{thread_id}/message`
  (`require_chat_message_rate_limit`).
- **Problem:** a caller could mint unbounded `ChatThread` rows. Not a safety
  issue (no allergy/diet logic involved), just unbounded resource usage.
  Flagged by the ROADMAP 3.3 second advisor review (approved overall) as
  non-blocking.
- **Fix:** add a rate-limit dependency (new or shared bucket, executor's
  call) to `create_chat_thread`.
- **Accept:** repeated thread creation past a reasonable threshold is
  rejected; test pinning the limit.

### B8. `routes_stream.py`'s mid-graph exception handler logs nothing

- **Where:** `app/api/routes_stream.py`'s SSE generator, `except Exception
  as exc:` around `task.result()` (~line 182) — same shape as
  `routes_chat.py`'s equivalent block before it was fixed 2026-08-03.
- **Problem:** identical bug to the one just fixed in `routes_chat.py`: a
  mid-graph exception in `/recipes/recommend`'s streaming path becomes a
  generic client-facing `error` SSE event with **zero server-side log
  line**, discarding the traceback. Individual graph nodes DO emit
  structured events via `app.observability.events` (so a node's own
  start/finish is visible), but an exception itself is never logged. Only
  surfaced because OTEL tracing is unconfigured in prod pending
  `docs/HUMAN_INPUTS.md` H1, so there's currently no other way to see it.
- **Fix:** same as the `routes_chat.py` fix — add `logger.exception(...)`
  in that except block before yielding the SSE `error` event.
- **Accept:** a forced mid-graph exception in a test produces a log line
  via `caplog`/`pytest.ini`'s logging capture, not just the generic SSE
  event.

### B9. Shared, invalidation-safe corpus cache for `recipe_retriever.py`

- **Where:** `app/services/recipe_retriever.py` — `RecipeRetriever.__init__`
  (constructed fresh per `search_recipes` tool call, `app/agent/tools.py`'s
  `_search_recipes`) and `get_recipe_by_id` (called by `_resolve_recipe`,
  and by `GET /recipes/{recipe_id}` in `app/api/routes_recommendations.py`)
  each independently call `app.rag.loaders.load_corpus()`, which parses the
  ~21 MB `imported_recipes.jsonl` + ~23 MB `grounding.jsonl` (10,011
  recipes) from disk every single call.
- **Context:** found while fixing the 2026-08-07 `search_recipes` incident
  (see `ChefStep.tool_args`'s docstring in `app/agent/chef_agent.py`) —
  `get_recipe_by_id` was changed to call `load_corpus()` too (previously it
  wrongly resolved against the 25-seed-only `recipes_by_id()`), so this is
  now paid on *every* tool round-trip that resolves a recipe_id
  (`check_recipe_safety`, `ground_nutrition`, `propose_substitutions`), not
  just once per `search_recipes` call as before. Explicitly NOT fixed as
  part of that incident — a naive `@lru_cache`/module-level cache was
  rejected there because several tests monkeypatch `settings.recipe_path`
  to point at an isolated test corpus, and a process-wide cache would leak
  state across tests (and across a real prod process, ignore a corpus
  rebuild until restart).
- **Fix:** a cache keyed on something that changes when the corpus does —
  e.g. the mtime/hash of `imported_recipes.jsonl` + `sample_recipes.jsonl`
  + `grounding.jsonl`, invalidated automatically on a `scripts/`
  regeneration — OR an app-lifespan-scoped singleton (built once in
  `app/main.py`'s lifespan, matching `_get_checkpointer`'s pattern in
  `app/graph/builder.py`) with an explicit test fixture that resets it,
  covering both `RecipeRetriever.__init__` and `get_recipe_by_id`.
- **Accept:** both call sites share one load per corpus generation, not one
  per call; existing tests that monkeypatch `settings.recipe_path` (e.g.
  `tests/test_retriever_corpus.py`) still pass unmodified; a corpus
  regeneration (`scripts/import_corpus.py`) is picked up without a process
  restart in dev.

## Frontend

### F1. `web/openapi.json` freshness is unenforced

- **Where:** `web/openapi.json` (tracked, 160 KB), regenerated manually via
  `scripts/export_openapi.py` → openapi-typescript.
- **Problem:** nothing fails CI when the FastAPI schema drifts from the
  committed `openapi.json` / `types.gen.ts`.
- **Fix:** CI step in the `test` job: run `scripts/export_openapi.py` to a
  temp file and `diff` against `web/openapi.json`; fail with a "regenerate
  types" message on drift.
- **Accept:** deliberately changing a schema without regenerating fails CI.

### F2. Social/meta polish for the live URL

- **Where:** `web/index.html`.
- **Task:** OpenGraph + Twitter card tags (title, description, a real
  1200×630 og-image once ROADMAP 4.1's landing exists), theme-color,
  apple-touch-icon. Small, but it's what recruiters see when the link is
  pasted into Slack/LinkedIn.
- **Accept:** valid preview in an OG debugger.

### F3. No image-upload UI for the HITL inventory-confirmation flow

- **Where:** `web/src/pages/HomePage.tsx` (`input_type` is hardcoded to
  `"text"`, no file input anywhere), `web/src/lib/sse.ts`'s `streamRecommend`
  (the `awaiting_input` SSE event, emitted by the backend since ROADMAP 3.2,
  is silently ignored — see that file's own comment).
- **Problem:** discovered while writing `docs/DEMO_SCRIPT.md` (ROADMAP 6.3):
  ROADMAP 3.2's own acceptance criterion is a live "upload photo -> stream
  pauses -> confirm -> resume" demo, and the backend fully supports it
  (`POST /runs`, the streaming `awaiting_input` event, `POST /runs/
  {thread_id}/resume` — all tested end-to-end in `tests/test_hitl_resume.py`
  and `tests/test_stream_endpoint.py`), but there is no click-through path
  to it anywhere in the product UI. It can only be demonstrated via `curl`/
  pytest today, not in front of an interviewer.
- **Fix:** an image-upload control on `HomePage` (or a dedicated flow) that
  sets `input_type: "image"`, plus `streamRecommend`/`HomePage` handling the
  `awaiting_input` event (render the low-confidence observations, collect
  corrections, call `POST /runs/{thread_id}/resume`) instead of dropping it.
- **Accept:** `docs/DEMO_SCRIPT.md`'s HITL step can be performed by clicking
  through the live UI, not narrated as an API-only capability.

## Data / evaluation

### D1. Legacy eval script status

- **Where:** `scripts/evaluate_demo_set.py` (plus
  `evaluate_batch_planner.py`, `evaluate_day_planner.py`,
  `evaluate_weekly_planner.py`).
- **Problem:** the old CLAUDE.md used `evaluate_demo_set.py`'s
  allergy_violation_rate as the everything-else gate; the current gates are
  `audit_diet_leaks.py` + the benchmark. Unclear which of these scripts
  are still load-bearing.
- **Task:** when ROADMAP 3.4 builds `scripts/run_all_evals.py`, decide per
  script: fold in, keep as dev tool (document at top of file), or delete.
- **Accept:** no orphan eval scripts without a stated owner/purpose.

### D2. Adjudication pass needed for 19 un-adjudicated `inherent` judge flags at HEAD

- **Where:** `scripts/run_safety_benchmark.py` (mock arm, free, deterministic
  term-match judge) against `app/evaluation/benchmark/cases/`.
- **Found:** while re-verifying the safety benchmark as part of the
  2026-08-07 `search_recipes` incident fix (`app/agent/chef_agent.py`'s
  `ChefStep.tool_args` docstring has that incident's own writeup — this
  finding is unrelated to it; confirmed via a `git stash` A/B that the
  benchmark result is byte-identical with and without that fix applied, so
  it is NOT a regression from that change). Running the mock arm at HEAD
  (commit `1748481`) reports 69/278 raw judge-flagged `inherent` violations
  (`data/evaluation/safety_benchmark_report_20260807T225559Z.md`). That
  number itself is expected and NOT the release-gate metric — the gate is
  the **adjudicated-true** count, and the raw judge has documented
  false-positive modes (see `data/evaluation/adjudication_20260717T145539Z.md`'s
  convention doc). The verified "clean 0/269" status CLAUDE.md cites
  (`scripts/verify_benchmark_evidence.py`, commit `0840e60`) is itself an
  *adjudicated* number pinned to an older run whose raw flag count was
  73/269 (`data/evaluation/safety_benchmark_report_20260727T190130Z.md`,
  `adjudication_20260727T190130Z_clean_final.md`).
- **The actual gap:** diffing today's 69 flagged case_ids against the 73
  adjudicated at the clean-run commit, **19 are new and have never been
  adjudicated**: `contradicted_013`, `contradicted_014`, `contradicted_017`,
  `contradicted_022`, `contradicted_030`, `contradicted_032`,
  `derivative_054`, `derivative_056`, `diet_015`, `diet_022`, `diet_032`,
  `macro_016`, `macro_022`, `morphology_024`, `morphology_025`,
  `morphology_031`, `multi_008`, `multi_018`, `subst_004` (23 other
  previously-flagged ids cleared instead). The drift traces to post-clean-
  run changes on `main` (`app/graph/builder.py`, `app/graph/nodes.py`,
  `app/services/recipe_retriever.py`, a +303-line extension to
  `scripts/run_safety_benchmark.py` itself under ROADMAP 3.3, and 10 new
  injection cases added since).
- **Rule (per CLAUDE.md's release-gate semantics, "ambiguity defaults to
  TRUE_VIOLATION"):** an un-adjudicated flag can NOT be assumed a false
  positive. The "clean 0/269" claim stays valid ONLY pinned to commit
  `ef8fd05`/evidence `0840e60` — at HEAD the adjudicated-true `inherent`
  rate is genuinely **unknown**, not known-zero. Do not update CLAUDE.md's
  "Current verified status" line, and do not publish any "0 violations at
  HEAD" claim, until this is resolved.
- **Fix:** a human/agent adjudication pass over the 19 case_ids above,
  following the existing per-case adjudication convention (see any
  `data/evaluation/adjudication_*.md` for the format), then a fresh
  `verify_benchmark_evidence.py`-style evidence commit. Free of API spend —
  the mock arm and its judge are both deterministic and local; the cost is
  adjudicator review labor, not money, so this does NOT need the CLAUDE.md
  money human-gate. It DOES need a human to actually do or approve the
  adjudication calls themselves (safety-adjacent judgment).
- **Accept:** every one of the 19 case_ids has a written per-case
  adjudication; a new evidence bundle + report timestamp is committed; if
  any adjudicate TRUE_VIOLATION, CLAUDE.md's "Current verified status" line
  is updated to reflect the real number (this would be a genuine, separate
  CLAUDE.md "Safety regressions" human-gate item, handled on its own merits
  at that point — not assumed here).

### D3. Repo-root `macrochef.db` hygiene

- **Where:** repo root (17 MB dev SQLite; correctly gitignored).
- **Task:** move the default `DATABASE_URL` target to `data/macrochef.db`
  so the repo root stays clean, or leave as-is and add a line to the
  README quickstart explaining the file. Low priority; decide when
  touching `app/config.py` anyway.

## Infra / CI

### I1. CI runtime: full model downloads in the `test` job

- **Where:** `.github/workflows/ci.yml` `test` job — `pip install -r
  requirements.txt` pulls full torch/sentence-transformers even though
  tests run with `EMBEDDING_PROVIDER=hash`.
- **Fix:** pip cache is already on; consider a `requirements-ci.txt`
  without the heavyweight extras, or `--extra-index-url` CPU torch (pairs
  with B4). Measure before/after job time in the PR.
- **Accept:** `test` job wall time reduced; no test skips introduced.

### I2. Log Analytics retention / cost check-in

- **Where:** ACA environment `cae-macrochef` (auto-created Log Analytics
  workspace).
- **Task:** once ROADMAP 1.x ships structured per-event logging, volume
  rises; verify workspace retention is 30 days and ingestion stays inside
  the negligible band assumed by docs/DEPLOY.md's cost section.
- **Accept:** one-line note added to DEPLOY.md cost section with observed
  monthly ingestion.

### I4. `scripts/run_safety_benchmark.py` full-case wall time (~1-2s/case)

- **Where:** `scripts/run_safety_benchmark.py`'s per-case graph runs
  (found while wiring ROADMAP 3.4's CI gate: `python
  scripts/run_safety_benchmark.py --runs 1` over the full 371-case set
  took roughly 8-11 minutes locally, dominated by per-node `RunEvent`
  logging (ROADMAP 1.1's `LogSink`, one structured JSON line per
  started/finished event per node, per case) plus real embedding-based
  retrieval per case rather than any LLM latency (the mock provider is
  free/instant).
- **Consequence:** the new CI gate step ("Safety benchmark gate
  (deterministic/mock subset)" in `.github/workflows/ci.yml`) uses
  `--runs 1` instead of the pre-registered `--runs 3` specifically to stay
  within this budget — see that step's own comment and
  `scripts/run_all_evals.py`'s module docstring for why 1 run is
  equivalent for a fully deterministic provider. A faster harness would
  let CI cheaply run the full k=3 methodology instead.
- **Fix ideas:** a quiet/CI logging mode for `LogSink` (batch or suppress
  per-node JSON lines during a benchmark run), or an `EventSink` no-op
  toggle for `scripts/run_safety_benchmark.py` specifically; profile
  whether retrieval (Chroma/hash-embedding query) or logging I/O
  dominates before optimizing either.
- **Accept:** full 371-case, `--runs 1` mock run completes in well under
  2 minutes; CI gate can move to `--runs 3` without a large CI time hit.

### I5. `scripts/run_safety_benchmark.py`/`run_all_evals.py` never called `init_db()` (FIXED in ROADMAP 3.4, noting the failure mode for visibility)

- **Where:** both scripts call `run_recommendation_graph`/
  `run_library_discovery_graph` directly, bypassing
  `app.main.create_app()`'s lifespan handler — the only place `init_db()`
  normally runs. Found while wiring ROADMAP 3.4's CI gate: against a
  FRESH sqlite file (a clean checkout, or a fresh CI runner with no
  pre-existing `macrochef.db`), `recipe_retriever_node`'s
  `user_saved_recipes` query raised `OperationalError: no such table` on
  every single case; `_run_recommendation_graph_surface`'s `except
  Exception` silently caught it and recorded "0 recipes served" — a
  false-negative gate (every `recommendation_graph`-surface case reads as
  "no violation" because nothing was ever served, and `safe_control`
  over-blocking read ~100%), not a real one. **Both scripts now call
  `init_db()` before running any case** (idempotent, safe). Left here as
  a backlog note only so the failure mode is documented/searchable if it
  ever resurfaces (e.g. a new script added later that also bypasses the
  app lifespan) — no further action needed unless that happens.
- **Accept:** N/A — already fixed; entry is for visibility/history only.

### I3. `GET /admin/llm-usage` is session-gated, not user-scoped

- **Where:** `app/api/routes_admin.py` (ROADMAP 1.2).
- **Problem:** the endpoint requires a valid anonymous session
  (`Depends(get_session_user)`) but returns **global, app-wide** LLM
  usage/cost aggregates — any authenticated session can see total spend
  across all users. Deliberate for now: there is no admin-role concept
  anywhere in this codebase (anonymous signed sessions only), and the
  endpoint's purpose is a maintainer cost dashboard, not per-user data.
- **Fix:** add a real admin check (e.g. a `MACROCHEF_ADMIN_USER_IDS`
  allowlist or a signed admin token) before this app ever has real,
  distinguishable accounts.
- **Accept:** endpoint 403s for non-admin sessions; existing aggregation
  logic unchanged.
