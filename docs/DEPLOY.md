# DEPLOY.md — Azure Container Apps

> **STATUS: LIVE since 2026-07-18** at
> <https://ca-macrochef.orangeplant-d8bf2180.italynorth.azurecontainerapps.io/>
> (region `italynorth`, 1 vCPU / 2 GiB, min=max=1 replica). First-deploy
> fixes that are now baked in: SP needs subscription-scope Contributor +
> RG-scoped RBAC Administrator (for the AcrPull self-grant);
> `psycopg2-binary` in requirements; `ENV PYTHONPATH=/app` in the
> Dockerfile; explicit `--cpu 1.0 --memory 2.0Gi` in the workflow.

How MacroChef gets from a green `pytest` run to a live public URL. What's
automated, what's manual, and the exact `az` fallback commands if the
automated create-if-absent steps ever fail on permissions.

The pipeline lives in `.github/workflows/ci.yml` (jobs: `test` + `web` ->
`preflight` -> `build-and-push` -> `deploy`). **SPA rebuild W6 cutover:** the
container now runs a SINGLE process — FastAPI/uvicorn, binding
`0.0.0.0:${PORT}` (default 8000) — serving both the JSON API and the built
React SPA (`web/`, via `app/spa.py`'s `mount_spa`) from the same origin.
There is no more Streamlit, no more `docker-entrypoint.sh` two-process
supervisor, and no more internal-vs-public port split: `PORT` is the one
port, and it is the public ingress port. `docker-entrypoint.sh` was deleted
in this cutover; the image's `CMD` runs uvicorn directly.

## What's automated

On a manual **`workflow_dispatch`** run of the CI workflow, on the `main`
branch, with the `deploy` input left at its default `true`:

1. `test` — pytest + `scripts/audit_diet_leaks.py` (unchanged gate; runs on
   every push/PR too).
2. `web` — the React SPA's own toolchain job (Node 22): `npm ci`, lint,
   typecheck, `vitest run`, `npm run build` (runs on every push/PR too, same
   as `test`).
3. `preflight` — Azure login, then an explicit role-assignment check that
   fails **loudly and in the first few seconds** if `AZURE_CREDENTIALS`
   doesn't have `Contributor`/`Owner` on the subscription, before any
   resource is touched. Gated on BOTH `test` and `web` passing. Then
   registers required resource providers (`Microsoft.App`,
   `Microsoft.ContainerRegistry`, `Microsoft.OperationalInsights`), and
   creates the resource group and ACR **if absent** (guarded with
   `az ... show || az ... create` so re-runs are idempotent).
4. `build-and-push` — builds the existing root `Dockerfile` image (which now
   builds `web/` in its own stage before baking the built SPA into the
   final image — see "Topology" below), tags it with the commit SHA and
   `latest`, pushes both to ACR.
5. `deploy` — creates the Container Apps environment and the app **if
   absent**, updates the ingress `--target-port` to 8000 (SPA cutover, see
   below), then always runs `az containerapp secret set` +
   `az containerapp update` so every dispatch ships the latest image,
   secrets, and env vars as a new revision.

Ordinary `git push` / pull requests only ever run the `test`/`web` jobs —
nothing builds, pushes, or deploys automatically. Deploys are a deliberate,
human-triggered action, never a side effect of pushing to `main`: everything
is prepared by CI, a human clicks "Run workflow".

**Database migrations (ROADMAP.md Phase 5, Step 5.1):** as of this step, the
`deploy` job runs `alembic upgrade head` against the prod Postgres (Neon,
`DATABASE_URL` secret) directly from the GitHub Actions runner, before the
traffic-shifting `az containerapp secret set`/`az containerapp update` steps
— see the `Run database migrations` step in `.github/workflows/ci.yml`. This
repo has no ACA init-container or pre-traffic-hook infra, so the runner talks
to Neon over the network the same way any other Postgres client would; that
assumes the runner can reach Neon directly (no VPC/private-networking
boundary in front of it), which has not been independently verified. Local
dev and the test suite still use `Base.metadata.create_all` under sqlite
only (see `app/data/db.py`'s `init_db`) — Postgres is Alembic-only from here
on.

## Topology — single container, single process (SPA rebuild W6 cutover)

**Changed in this cutover** (previously: two processes, Streamlit public +
internal FastAPI, orchestrated by a now-deleted `docker-entrypoint.sh` — see
git history before this commit for that topology). The deployed image now
runs ONE container with ONE process:

- **FastAPI/uvicorn** (port `0.0.0.0:${PORT}`, default 8000): the only
  process, and the only ingress. It serves the JSON API routes AND the
  built React SPA (`web/dist`, baked into the image by the Dockerfile's
  `webbuild` stage; served via `app/spa.py`'s `mount_spa`) from the same
  origin. Container Apps injects `PORT` at runtime; the workflow's
  `--target-port` (and the explicit `az containerapp ingress update` step
  for the already-existing app, since `create`'s `--target-port` only takes
  effect the first time an app is created) is 8000, replacing the old 8501.

**Process supervision and health checks:**

- There is nothing left to supervise between two processes — uvicorn dying
  is the container dying, which the platform detects natively.
- The Dockerfile's `HEALTHCHECK` still curls `/health` directly (now on the
  same port as public ingress, `127.0.0.1:${PORT}`, not a separate internal
  port) — kept for the same defense-in-depth reason as before, just
  simplified to one port.

**Vector index and embeddings:**

- The MiniLM embedding model is baked into the image at build time (`RUN
  python -c "... SentenceTransformer(...)"` in the Dockerfile) — no runtime
  download.
- The Chroma vector index (`data/chroma/`) is **rebuilt from scratch inside
  every image build**, not copied in from whatever `data/chroma` happens to
  exist on the machine/runner running `docker build`. `data/chroma/` is
  gitignored AND `.dockerignore`d (as of 2026-07-19 — see "Corpus
  provenance and index freshness" below for the staleness bug this closes);
  a Dockerfile `RUN` step calls
  `RecipeIndexingService().rebuild_index_clean(include_base=True,
  include_user=False)` against the TRACKED corpus files
  (`data/processed/sample_recipes.jsonl` + `imported_recipes.jsonl`) that
  `COPY . .` just placed in the image, and asserts the resulting index is
  non-empty (build fails loudly rather than shipping an empty index).
  `include_user=False` is required, not just preferred: there is no live
  `DATABASE_URL` at build time, and baking one user's saved recipes into a
  shared image would be architecturally wrong regardless. User-saved
  recipes are added to the already-populated index at runtime via upsert
  (the recipe-save flow, and `POST /library/reindex`), unaffected by this
  step.
- Scaling to multiple replicas is blocked: the embedded Chroma is a single-writer
  store; multiple replicas would corrupt the index. `min-replicas=1 /
  max-replicas=1` is deliberate (see "Cost implication" below).
- Image size: ~3.42 GB (PyTorch dominates).

**pgvector backend — an external, multi-writer-safe alternative (ROADMAP
5.2, 2026-07-29):**

- `app.rag.pgvector_store` implements the same `VectorStore` interface
  (`app.rag.vector_store`) over Postgres + the `vector` extension, selected
  via `VECTOR_BACKEND=pgvector` (default remains `chroma` — nothing above
  changes unless this is set). Schema: `alembic/versions/
  0002_pgvector_recipe_embeddings.py`, a no-op on sqlite. Seeding a
  Postgres instance: `scripts/seed_pgvector.py` (a release-job step, not a
  build-time step, since the data lives in the external DB, not the image).
- Retrieval-quality parity verified (`scripts/evaluate_retrieval.py`, both
  backends, `EMBEDDING_PROVIDER=hash`, 10,011-recipe corpus): aggregate
  Recall@10 within 0.77 points (both HNSW/approximate-NN, so a small,
  explainable delta on tiny-n categories is expected, not a regression) --
  see `data/evaluation/vector_backend_parity_20260729.md` for the full
  per-category breakdown and how to reproduce.
- This alone does **not** unblock `max-replicas>1` — the per-process
  in-memory rate limiter (`app.services.rate_limiter`) was the other half
  of that blocker. ROADMAP 5.2 also added a Postgres-backed shared limiter
  (same module, selected automatically when `DATABASE_URL` is
  non-sqlite) so that blocker is cleared too, but **`max-replicas` in
  `.github/workflows/ci.yml` was deliberately left at 1** — raising it is
  a production topology change reserved for the maintainer (CLAUDE.md
  invariant #8), now a one-line edit (`--max-replicas 1` → the desired
  value, in both the `preflight`-adjacent deploy steps) once
  `VECTOR_BACKEND=pgvector` is actually live in prod.

**Corpus provenance and index freshness (2026-07-19):**

- The corpus (`data/processed/imported_recipes.jsonl`,
  `quarantined_recipes.jsonl`, `sample_recipes.jsonl`) is generated from the
  scraped Food.com archive (`data/scraped/foodcom/*.md`, local-only — see
  "Scraped-archive licensing" below). As originally rebuilt at commit
  `d93e07a` ("A1: rebuild the corpus from the scraped Food.com archive"):
  3,853 active imported recipes + 25 curated seeds = 3,878 indexed; 379
  quarantined (historical figure for that specific rebuild). **Current
  corpus size: 10,011 recipes**, after the corpus-expansion-10k merge
  (commit `652e1e0`, "grow recipe corpus from 3,884 to 10,011" — see
  `data/processed/grounding_report.md`'s "total recipes processed" for the
  authoritative live count). These processed outputs ARE tracked in git
  (unlike the raw archive/scraper), so they are present in any checkout,
  including a CI runner's.
- **Staleness bug found and fixed 2026-07-19 (this item).** Before this
  fix, nothing in the Dockerfile, `docker-entrypoint.sh`, or
  `.github/workflows/ci.yml` ever populated `data/chroma/` inside the
  image. `.dockerignore` had `!data/chroma/**` (re-including it despite
  the general `*.sqlite3` exclusion), so a **local** `docker build` would
  silently bake in whatever pre-built local index happened to be on the
  developer's disk (correct only if that person had just run
  `scripts/ingest_recipes.py` by hand against the current corpus) — but
  the CI-driven `build-and-push` job (the one that actually ships via
  `workflow_dispatch`) builds from an `actions/checkout@v4` working tree,
  which never has a populated `data/chroma/` at all (it's gitignored, so a
  fresh checkout has none). That build would have shipped an image with an
  **empty** vector index — not merely stale, unusable — silently, since
  nothing checked the index was non-empty. Fixed by generating the index
  inside the image at build time (above), from the tracked corpus, with a
  non-empty assertion; `data/chroma/` is now fully excluded from the
  Docker build context (`.dockerignore`) so no local/CI copy can leak in.
  This makes every image build reproducible and tied to whatever corpus is
  currently committed — no manual regeneration step required.

**Local development (two terminals, no Docker needed):**

```bash
uvicorn app.main:app --reload --port 8000   # terminal 1: API
cd web && npm run dev                         # terminal 2: Vite dev server
```

Open the Vite dev server's URL (default `http://localhost:5173`), not
`:8000` directly — Vite's dev proxy (`web/vite.config.ts`'s
`API_PROXY_PREFIXES`) forwards the backend API prefixes to `:8000` so the
browser only ever talks to one origin, matching the production
same-origin topology in spirit even though the SPA isn't baked into the
API process yet in this mode. The root `docker-compose.yml`'s `api`
service runs the built image's single FastAPI/uvicorn process only (no
`web/` dev loop) — useful for smoke-testing the production topology, not
for day-to-day SPA development (see that file's own comment).

## SSE / long-lived connections (ROADMAP.md Phase 3, Step 3.1)

`POST /recipes/recommend/stream` (`app/api/routes_stream.py`) holds one HTTP
connection open for the duration of a full graph run (20-45s is typical
today; a slow LLM provider call or USDA grounding lookup could push this
longer) while relaying `RunEvent`s as Server-Sent Events, ending with a
terminal `result`/`error` event. Two ACA ingress behaviors matter for this:

- **Idle timeout:** ACA's HTTP ingress (Envoy-based) closes a connection
  after a period with no bytes sent, independent of total connection
  duration. The stream endpoint sends an SSE comment line (`: heartbeat`)
  every ~10s of silence between node events specifically to stay under
  this — see `HEARTBEAT_INTERVAL_SECONDS` in `routes_stream.py`. If a
  future change ever needs a *longer* per-request wall-clock timeout (not
  just idle), Container Apps ingress does not currently expose that as a
  first-class Terraform/`az containerapp` setting the way, e.g., Azure
  Application Gateway does — this would need re-checking against the
  Container Apps ingress docs before relying on any specific number.
- **`X-Accel-Buffering: no`:** set on the stream response so an
  nginx-style intermediary (not currently in this app's own path — ACA's
  ingress is Envoy, not nginx — but relevant if a CDN/reverse proxy is ever
  added in front of it) doesn't buffer the whole response before sending
  it, which would defeat "live" streaming entirely.
- Because `min-replicas=1`/`max-replicas=1` is already the deployed
  topology (see "Cost implication" below), an SSE connection pinned to the
  single replica is not a new scaling concern this step introduces — it's
  the same single-writer/single-process posture the rest of this document
  already documents.

## LangGraph checkpointer / true HITL (ROADMAP.md Phase 3, Step 3.2)

`POST /runs` (`app/api/routes_runs.py`) is the checkpointed, pausable
sibling of `POST /recipes/recommend` — additive, not a replacement; the
existing sync/stream endpoints are provably unchanged (see that module's
docstring for the full isolation argument: a `MacroChefState.hitl_enabled`
flag, settable only from Python inside the `/runs` handler, never from any
request body).

- **Two compiled-graph singletons, one checkpointed, one not.**
  `app.graph.builder.build_macrochef_graph()` (no checkpointer, used by the
  old endpoints) and `get_compiled_macrochef_graph()` (checkpointed, used
  only by `/runs`) are both `@lru_cache`d process-wide singletons built
  from the same node/edge wiring. Compiling twice, rather than routing
  every call through one checkpointed graph, means calls that can never
  pause (the old endpoints) never write a checkpoint row at all — no
  orphaned-row cleanup job needed.
- **Checkpointer backend derives from `DATABASE_URL`, dialect-switched --**
  no new env var. sqlite gets `SqliteSaver` (a real file, matching
  `DATABASE_URL`'s path — never `:memory:`, so a paused run survives a
  process restart); any Postgres `DATABASE_URL` gets `PostgresSaver`. Same
  pattern ROADMAP 5.2 already applied to `app.rag.vector_store` and
  `app.services.rate_limiter`.
- **Checkpointer tables are NOT Alembic-managed.** `checkpoints`,
  `checkpoint_writes`, etc. are created by the upstream
  `langgraph-checkpoint-sqlite`/`-postgres` packages' own `.setup()`
  (idempotent, migration-based) — advisor-reviewed decision: hand-copying
  that DDL into this app's own Alembic revisions would silently drift the
  moment the upstream package's schema changes on a version bump, and Step
  5.1's schema-drift gate diffs the live DB against `Base.metadata`, which
  never needs to see these tables either way. **`app.data.models.GraphRun`
  (the `thread_id -> owner_user_id` ownership mapping) is different** — it
  IS this app's own data, and does go through Alembic (`alembic/versions/
  0004_graph_runs.py`).
- **Cross-user resume returns 404, not 403** (advisor-reviewed): mirrors
  `app.services.share_service.get_share`'s existing "no oracle for
  exists-but-not-yours" collapse. `thread_id`s are `secrets.token_urlsafe(16)`
  (128 bits), so hiding existence costs little, and no legitimate client
  needs to tell "doesn't exist" from "isn't yours" apart.
- **Real Postgres path not independently load-tested here** — same caveat
  as ROADMAP 5.1's Alembic migrations before Step 5.2 closed that gap for
  the vector store; worth a real verification pass (a live `psycopg`
  connection via `PostgresSaver`) before this feature is relied on against
  prod Postgres.

## Safety-benchmark gate status

The release gate is **zero adjudicated-true `inherent` violations** on the
adversarial benchmark (`scripts/run_safety_benchmark.py`), and the raw
judge-flagged count is always published alongside the adjudicated one —
never just the friendlier number. Every judge flag gets a written,
per-case adjudication (matched term, matched field, the served recipe's
actual ingredients, a citable rule) before it counts as a real violation;
see `data/evaluation/` for the full adjudication history. The judge is
never modified to close the gap between the raw and adjudicated numbers —
judge false positives stay in the raw count forever. Until the adjudicated
number is verified zero on a clean run, the deployed app carries a
prominent disclaimer and no unqualified "0 violations" claim is published
anywhere (UI, README, blog post).

**Latest verified status:** see the README's benchmark section for the
current judge-flagged/adjudicated-true numbers and the run they came from.

## Scraped-archive licensing — RESOLVED (hobby scope)

**Decided by the human, 2026-07-19 (same convention as the existing Kaggle
Food.com CC0 clearance):** the corpus derived from re-scraping Food.com's
own recipe pages is cleared for the current hobby scope. Only the
processed/derived corpus (`data/processed/imported_recipes.jsonl`,
`quarantined_recipes.jsonl`, `sample_recipes.jsonl`, committed to git) ships
in the deploy image. The raw scraper code
(`app/services/recipe_scraping/`, `scripts/scrape_recipe_pages.py`) and the
captured raw HTML/Markdown archive pages (`data/scraped/`,
`tests/fixtures/scrape/`) stay **local-only** — untracked as of this item
(git rm --cached + `.gitignore` entries), never shipped in the image, never
part of any package published from this repo. **This decision re-opens if
the project's scope moves toward commercial or public-commercial
deployment** — re-raise it as a human gate at that point, don't assume the
hobby-scope clearance still applies.

## What's manual (you)

- **Trigger the deploy.** Actions tab -> this workflow -> "Run workflow" ->
  branch `main` -> leave `deploy: true` -> Run. This is the literal
  "pull the trigger" step; nothing deploys without it.
- **Provide the four GitHub repo secrets** used by the deploy jobs (see
  below) — `AZURE_CREDENTIALS` and `DATABASE_URL` are already set per the
  task brief; add `GEMINI_API_KEY`, `SESSION_SECRET`, `POSTHOG_API_KEY`
  when ready. Missing `GEMINI_API_KEY`/`POSTHOG_API_KEY` degrade sanely at
  runtime (model provider falls back to `mock`; analytics is a silent
  no-op — see `app/services/analytics.py`) but the ACA secret itself will
  just be set to an empty string if the GitHub secret doesn't exist, which
  is fine.
- **Approve the cost** of `min_replicas=1` before the first real deploy —
  see "Cost implication" below. This is a real, ongoing spend, not a
  one-time cost — treat it as a deliberate decision, not a default.
- **(Optional, extra protection)** the `deploy` job references a GitHub
  Environment named `production`. Configure required reviewers on it
  (Settings -> Environments -> production) if you want a second
  human-approval gate in addition to `workflow_dispatch`. Without that
  configuration the environment reference is a no-op label, not a gate —
  `workflow_dispatch` is the real gate here, don't rely on the environment
  alone.

## Required GitHub repo secrets

| Secret | Status | Used for |
|---|---|---|
| `AZURE_CREDENTIALS` | set (confirmed 2026-07-17) | SP JSON for `azure/login`; needs Contributor on the subscription |
| `DATABASE_URL` | set (confirmed 2026-07-17) | Neon Postgres connection string -> ACA secret `database-url`; also consumed directly (as a job env var, not an ACA secret) by the `deploy` job's `alembic upgrade head` step (ROADMAP.md Step 5.1) |
| `GEMINI_API_KEY` | set (confirmed 2026-07-17) | LLM phrasing/explanation only, never safety or nutrition -> ACA secret `gemini-api-key` |
| `SESSION_SECRET` | set (confirmed 2026-07-17) | signs/verifies the anonymous session token (`app/dependencies.py`) -> ACA secret `session-secret`; falls back to an insecure dev default with a logged warning if unset — never leave unset in production |
| `POSTHOG_API_KEY` | set (confirmed 2026-07-17) | analytics; absent = silent no-op -> ACA secret `posthog-api-key` |

(Also confirmed present in GitHub repo secrets 2026-07-17: `FDC_API_KEY`
and `HUGGING_FACE_TOKEN` — not consumed by the deploy workflow today;
the HF token is for the Batch 2 dataset publication human gate.)

## Resource naming (in the workflow's `env:` block — change there, not here)

```yaml
AZURE_REGION: italynorth
(was westeurope; changed 2026-07-18 to italynorth — Azure declined new-customer resource creation in westeurope: RequestDisallowedByAzure)
RESOURCE_GROUP: rg-macrochef
ACA_ENV_NAME: cae-macrochef
ACA_APP_NAME: ca-macrochef
ACR_NAME: acrmacrochef01   # must be globally unique across all of Azure
```

If `acrmacrochef01` is already taken by someone else, ACR creation fails
loudly with a name-conflict error (not silently) — pick a new suffix in the
workflow's `env:` block and re-run.

## Manual `az` fallback (if the automated create-if-absent steps fail on permissions)

Run these yourself (as a user/principal with Contributor), then re-run the
workflow — it will find everything already present and skip straight to
build/push/deploy:

```bash
az login
az account set --subscription <SUBSCRIPTION_ID>

# 1. Resource group
az group create --name rg-macrochef --location italynorth

# 2. Container registry
az acr create --name acrmacrochef01 --resource-group rg-macrochef --sku Basic --admin-enabled false

# 3. Resource providers (only needed once per subscription)
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.OperationalInsights --wait

# 4. Container Apps environment
az extension add --name containerapp --upgrade
az containerapp env create --name cae-macrochef --resource-group rg-macrochef --location italynorth

# 5. Grant the CI service principal Contributor, scoped narrowly to this RG
#    if you don't want subscription-wide access:
az role assignment create \
  --assignee <CI_SERVICE_PRINCIPAL_CLIENT_ID> \
  --role Contributor \
  --scope "$(az group show --name rg-macrochef --query id -o tsv)"
```

The Container App itself (`ca-macrochef`) is left for the workflow to
create on its next run — it needs the pushed image tag, which only exists
after `build-and-push` runs once.

## Cost implication of `min_replicas=1` — money gate

`min_replicas=1` (and `max_replicas=1`, set for the same reason) means the
container never scales to zero and is billed continuously, unlike the ACA
consumption plan's free grant which assumes scale-to-zero idle time.
The container runs at **1.0 vCPU / 2.0 GiB, always on** — bumped up from the
default 0.5 vCPU / 1 GiB class, which crash-looped (OOM / probe-fail) on the
first real deploy (2026-07-18): torch + MiniLM + Chroma need more than 1 GiB.
**Estimated cost: roughly $30-60/month** for the 1.0 vCPU / 2.0 GiB
always-on container, plus negligible Log Analytics ingestion, well
above the ACA free monthly grant — a real, ongoing spend that needs
explicit approval before the first real (non-`workflow_dispatch`-test)
deploy. (The ACR Basic SKU adds a small, separate ~$5/month regardless of
replica count — not the focus of this gate, but worth knowing.)

**Why not `min_replicas=0` or `max_replicas>1`:** the app's vector index
(embedded ChromaDB, `data/chroma`) is a **single-writer store** persisted on
local container disk. Scaling to zero would mean a cold rebuild delay (and
the local disk is ephemeral across revisions/replicas in ACA — writes don't
persist reliably across restarts anyway). Scaling above one replica risks
two processes fighting over the same on-disk Chroma segments. Both are
open items for whenever traffic justifies horizontal scaling — the real
fix is an external, multi-writer-safe vector store.

**Update (ROADMAP 5.2, 2026-07-29): the real fix now exists but is not
switched on.** `VECTOR_BACKEND=pgvector` (see "pgvector backend" above)
plus the new Postgres-backed shared rate limiter together clear both
technical blockers behind `max-replicas=1`. Neither `DATABASE_URL` nor
`VECTOR_BACKEND` nor `--max-replicas` were changed in this deploy config —
flipping all three (Postgres already provisioned for the app's other
tables, `VECTOR_BACKEND=pgvector`, `scripts/seed_pgvector.py` run once,
then raising `--max-replicas` in `.github/workflows/ci.yml`'s deploy step)
is a deliberate production-topology change for the maintainer to make when
traffic justifies it, not something this step did unilaterally.

**Money gate resolved 2026-07-17: APPROVED by the human.** `min_replicas=1`/
`max_replicas=1` is accepted (decision 4A); the resource size was then
bumped to 1.0 vCPU / 2.0 GiB (~$30-60/month) on 2026-07-18 after the
default-size crash-loop, also human-approved by running the resource-bump
deploy. The external-model comparison arms (~$12.21 estimated) are DEFERRED until the
safety gate (zero adjudicated-true inherent violations) is met. The
production deploy itself remains a separate "Public actions" human gate —
prepare everything; the human pulls the trigger.

## What could not be tested here

This document and the workflow were written and schema-validated
(`check-jsonschema --builtin-schema vendor.github-workflows`), but the
actual Azure deploy path (login, RG/ACR/env/app creation, image push,
revision update) has **not been run** — there are no `AZURE_CREDENTIALS` in
this execution environment and running it would touch a real subscription.
The first real `workflow_dispatch` run is the actual test of this pipeline;
watch the `preflight` job output closely on that first run.
