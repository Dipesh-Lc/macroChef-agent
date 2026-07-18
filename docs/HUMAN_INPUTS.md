# HUMAN_INPUTS.md — everything the agents need from you

The agents run autonomously except at these gates. Items are grouped by the
batch they block. Provide keys via `.env` (never in chat); decisions can be
answered inline when the orchestrator's NEEDS HUMAN summary asks.

## Before / during Batch 1.5 (Phase 1 closeout)

- [x] `FDC_API_KEY` present and working in `.env` (re-grounding the
      corpus will make many API calls; the key is free but rate-limited —
      confirm you're OK with a long-running job or provide the cached data
      directory from the Phase 1 run). Batch 1.5 complete.

## Before / during Batch 2 (benchmark + deploy)

Decisions:
- [x] Cloud: Azure Container Apps (chosen; `AZURE_CREDENTIALS` set as a
      repo secret, confirmed 2026-07-17).
- [x] Postgres: Neon (`DATABASE_URL` set as a repo secret, confirmed
      2026-07-17).
- [x] Hugging Face account + write token: `HUGGING_FACE_TOKEN` set as a
      repo secret, confirmed 2026-07-17. You click "publish"; the
      packaged dataset + upload instructions live in `hf_dataset/`.
- [x] Auth email delivery: NOT NEEDED for launch — decision 3A
      (2026-07-17): anonymous signed per-browser sessions ship instead;
      magic-link deferred until retention measurement starts (Phase 4).
- [x] Analytics: PostHog (`POSTHOG_API_KEY` set as a repo secret,
      confirmed 2026-07-17).
- [ ] Benchmark spend approval — NOW UNBLOCKED (deferred by decision 4A
      until the adjudicated-zero gate was met; the gate was met
      2026-07-18): the external-model comparison arms (3 models ×
      {naive, steelman}, k=3) at an estimated ~$12.21 need your budget
      approval + `OPENAI_API_KEY`/`GEMINI_API_KEY`/`ANTHROPIC_API_KEY`
      in `.env` before any paid calls.
- [ ] Corpus license posture: the Food.com Kaggle corpus (CC0-self-applied)
      is fine for hobby scope, but a public deployment is arguably
      "public/commercial-adjacent" — decide: keep as-is, or swap/trim the
      imported corpus before going live. (The seed/imported split makes a
      swap cheap. Note: after the 2026-07-18 integrity quarantines the
      imported corpus is 2,884 rows; the quality case for an eventual
      swap got stronger — ~25% of the original import was corrupt — but
      the licensing question is unchanged and still yours.)

Keys / accounts (fill placeholders the agents add to `.env.example`):
- [ ] `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` — for the
      benchmark comparison runs only.
- [ ] Hosting account + deploy token for the chosen host.
- [ ] Postgres connection string.
- [ ] Email provider API key for magic links.
- [ ] Analytics project key.

Manual actions:
- [ ] Capture 3 README screenshots + 60–90s demo GIF (the agents leave exact
      capture instructions at the TODO markers).
- [ ] Click the actual production deploy when the pre-deploy review is
      APPROVED.
- [ ] Post the soft-launch drafts (Show HN, subreddits) yourself.

## Before / during Batch 3 (differentiation)

- [ ] Ingredient price data: approve a source (agents will surface options
      + licenses) or say "use a small hand-curated table for v1".
- [ ] Optional: sample MyFitnessPal / Cronometer / MacroFactor export files
      if you want real-format import tested now rather than later.

## Before / during Batch 3.5 (ML depth layer)

- [ ] MLflow backend: local file store (default, zero setup) or a hosted
      tracking server if you want a shareable UI.
- [ ] GPU for the embedding fine-tune: optional. Default is a small model
      on CPU; if you have Colab/a GPU box, say so and the agents will
      produce a runnable training script for it instead.
- [ ] HF Hub publication trigger for the fine-tuned model (account/token
      from the Batch 2 item).

## Before / during Batch 4 (planning systems)

- [ ] Confirm share-link policy: public unguessable-URL links OK, or
      login-gated only?
- [ ] Budget defaults for the weekly solver (e.g. default weekly food budget
      used in examples/tests).

## Before / during Batch 5 (final product)

- [ ] Frontend framework decision (default proposal: Next.js + Tailwind on
      the existing FastAPI backend).
- [ ] Vision go/no-go based on the analytics the agents show you; if go,
      pick the vision provider and supply its key.
- [ ] Public API/MCP: decide key-issuance policy (open with rate limits vs.
      manual keys).
- [ ] Kubernetes stretch item: opt in or skip (manifests + kind-based CI
      check; adds complexity, only worth it for the CV line).
- [ ] Publish the v2 launch posts yourself.

## Standing rules (apply to every batch)

- Any NEW dataset import: the agents show you the license; nothing is
  imported until you say yes.
- Any nonzero allergy-violation rate stops work on that line until you've
  seen it.
- Real secrets only ever go into `.env` / provider dashboards, filled by you.
