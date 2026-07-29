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

### D2. Repo-root `macrochef.db` hygiene

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
