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

The pipeline lives in `.github/workflows/ci.yml` (jobs: `test` -> `preflight`
-> `build-and-push` -> `deploy`). A single container runs both Streamlit and
FastAPI, started by `docker-entrypoint.sh`. Streamlit is the only public
ingress (`0.0.0.0:8501`); FastAPI binds to `127.0.0.1:8000` (loopback only,
not reachable externally). If either process dies, the container exits
non-zero and is not reported healthy by the platform.

## What's automated

On a manual **`workflow_dispatch`** run of the CI workflow, on the `main`
branch, with the `deploy` input left at its default `true`:

1. `test` — pytest + `scripts/audit_diet_leaks.py` (unchanged gate; runs on
   every push/PR too).
2. `preflight` — Azure login, then an explicit role-assignment check that
   fails **loudly and in the first few seconds** if `AZURE_CREDENTIALS`
   doesn't have `Contributor`/`Owner` on the subscription, before any
   resource is touched. Then registers required resource providers
   (`Microsoft.App`, `Microsoft.ContainerRegistry`,
   `Microsoft.OperationalInsights`), and creates the resource group and ACR
   **if absent** (guarded with `az ... show || az ... create` so re-runs are
   idempotent).
3. `build-and-push` — builds the existing root `Dockerfile` image, tags it
   with the commit SHA and `latest`, pushes both to ACR.
4. `deploy` — creates the Container Apps environment and the app **if
   absent**, then always runs `az containerapp secret set` +
   `az containerapp update` so every dispatch ships the latest image,
   secrets, and env vars as a new revision.

Ordinary `git push` / pull requests only ever run the `test` job — nothing
builds, pushes, or deploys automatically. This matches CLAUDE.md's "Public
actions" human gate: everything is prepared, a human clicks "Run workflow".

## Topology — single container, Streamlit public + internal FastAPI

The deployed image runs one container with two processes orchestrated by
`docker-entrypoint.sh`:

- **Streamlit** (port `0.0.0.0:8501`): the only public ingress. Container Apps
  injects the `PORT` env var; locally, it defaults to 8501. The workflow
  deploys with `--target-port 8501`.
- **FastAPI/uvicorn** (port `127.0.0.1:8000`): loopback only, **not reachable
  from outside the container**. Streamlit reaches it via the `MACROCHEF_API_URL`
  env var. This avoids exposing the API to the internet.

**Process supervision and health checks:**

- If either process dies, `docker-entrypoint.sh` uses `wait -n` to exit the
  container with non-zero status, so the platform never reports a half-dead
  container as healthy.
- A `HEALTHCHECK` in the Dockerfile curls the internal FastAPI directly. This
  is necessary because Azure Container Apps' ingress probe only reaches
  Streamlit on port 8501 and cannot detect an API-only outage.

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

**Corpus provenance and index freshness (2026-07-19):**

- The corpus (`data/processed/imported_recipes.jsonl`,
  `quarantined_recipes.jsonl`, `sample_recipes.jsonl`) is generated from the
  scraped Food.com archive (`data/scraped/foodcom/*.md`, local-only — see
  "Scraped-archive licensing" below), commit `d93e07a` ("A1: rebuild the
  corpus from the scraped Food.com archive"): 3,853 active imported recipes
  + 25 curated seeds = 3,878 indexed; 379 quarantined. These processed
  outputs ARE tracked in git (unlike the raw archive/scraper), so they are
  present in any checkout, including a CI runner's.
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

**Local development differs intentionally:**

The root `docker-compose.yml` runs Streamlit and FastAPI as two separate
services (on ports 8501 and 8000 respectively), suitable for local development
with live reload and separate debugging. This is a separate, intentional path
from the production single-container topology — not an inconsistency to "fix".

## Safety-benchmark gate status

Per CLAUDE.md "Honest scope" (gate semantics fixed by the human 2026-07-17,
option "adjudicated zero" — see that section for the full definition, not
repeated here): the release gate is **zero adjudicated-true `inherent`
violations** on the adversarial benchmark, and the judge-flagged count is
always published alongside the adjudicated one.

**Current status, on the corpus generated by commit `d93e07a`** (source:
`data/evaluation/adjudication_20260719T115815Z.md`, advisor MODE: REVIEW
APPROVED 2026-07-19):

- **inherent (release-blocking): judge-flagged 16/259; adjudicated true
  0/259 — GATE MET.**
- precautionary (non-blocking): judge-flagged 8/46.
- safe_control over-blocking (non-blocking): 0/60.

The gate being met does **not** license an unqualified "0 violations" claim
anywhere (UI, README, blog post, launch draft) — any published claim must
state both numbers together, and the deployed app carries the disclaimer
required by CLAUDE.md until/unless the human decides otherwise. The judge
is never modified to close the judge-flagged/adjudicated-true gap; judge
false positives stay in the raw (16/259) number forever.

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
  see "Cost" below. This is a CLAUDE.md money gate.
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
| `DATABASE_URL` | set (confirmed 2026-07-17) | Neon Postgres connection string -> ACA secret `database-url` |
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
first real deploy (2026-07-18): torch + MiniLM + Chroma + the dual
Streamlit/FastAPI process need more than 1 GiB.
**Estimated cost: roughly $30-60/month** for the 1.0 vCPU / 2.0 GiB
always-on container, plus negligible Log Analytics ingestion, well
above the ACA free monthly grant. This is a CLAUDE.md "Money" human gate —
get explicit approval before the first real (non-`workflow_dispatch`-test)
deploy. (The ACR Basic SKU adds a small, separate ~$5/month regardless of
replica count — not the focus of this gate, but worth knowing.)

**Why not `min_replicas=0` or `max_replicas>1`:** the app's vector index
(embedded ChromaDB, `data/chroma`) is a **single-writer store** persisted on
local container disk. Scaling to zero would mean a cold rebuild delay (and
the local disk is ephemeral across revisions/replicas in ACA — writes don't
persist reliably across restarts anyway). Scaling above one replica risks
two processes fighting over the same on-disk Chroma segments. Both are
tracked as a real fix in `docs/BACKLOG.md` ("Multi-replica / external vector
store").

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
