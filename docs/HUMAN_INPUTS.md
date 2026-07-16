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
- [ ] Cloud: Azure Container Apps (default — Azure leads in your JDs) /
      GCP Cloud Run (cheapest) / AWS App Runner. Requires an account on
      the chosen cloud + deploy credentials as GitHub repo secrets.
- [ ] Postgres: managed on the chosen cloud, or Neon / Supabase free tier
      (default proposal: Neon — cheaper than cloud-managed).
- [ ] Hugging Face account + write token, for publishing the benchmark
      dataset (Batch 2) and optionally the fine-tuned model (Batch 3.5).
      You click "publish"; agents prepare everything.
- [ ] Auth email delivery: e.g. Resend / Postmark / Supabase Auth
      (default proposal: magic links via Resend).
- [ ] Analytics: PostHog / Plausible (default proposal: PostHog).
- [ ] Benchmark spend approval: the harness will report an estimated cost
      for running 300–500 cases against GPT / Claude / Gemini before any
      paid calls. Approve a budget cap.
- [ ] Corpus license posture: the Food.com Kaggle corpus (CC0-self-applied)
      is fine for hobby scope, but a public deployment is arguably
      "public/commercial-adjacent" — decide: keep as-is, or swap/trim the
      imported corpus before going live. (The seed/imported split makes a
      swap cheap.)

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
