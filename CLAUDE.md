# CLAUDE.md

Project memory for Claude Code. Read this at the start of every session.

## What this project is

MacroChef is a LangGraph-based meal-planning agent. Its defining principle:

> **The LLM NEVER enforces allergies or computes nutrition. Deterministic code does.**
> The LLM is only used for fuzzy, non-safety-critical work (parsing intent,
> ranking, phrasing). Anything that could harm a user if wrong is deterministic.

Any change that touches allergy filtering, dietary constraints, or nutrition
math must preserve this separation. If a change would let the LLM decide a
safety outcome, stop and flag it instead of writing it.

## Current mission: autonomous multi-agent execution of Phases 1.5–5

Phases 0–1 are complete. The remaining roadmap (`docs/ROADMAP.md`) is executed
autonomously using the orchestration protocol below and the batch prompts in
`docs/phase-2-5-session-prompts.md`. Speed is the priority; the roadmap's
week estimates are NOT deadlines or pacing — work through items back-to-back.

**Secondary objective — employability skills demonstration.** This project
also serves as a portfolio demonstrating the skills in
`docs/SKILLS_MATRIX.md` (classic ML with scikit-learn, PyTorch/deep
learning, Hugging Face, MLflow/MLOps, SQL/Postgres, major-cloud deploy,
CI/CD). When two implementation options are otherwise comparable, prefer
the one that exercises a skill from the matrix, and keep the matrix updated
as items land. This objective NEVER overrides the safety invariant or adds
a technology where it makes the system worse — a forced, unjustified
dependency is a portfolio negative.

**ML components are advisory only.** Any learned model added to this repo
(ranker, classifier, fine-tuned embeddings) may rank, flag, suggest, or
retrieve — it may NEVER admit, reject, or substitute a recipe on safety
grounds, and never computes nutrition. The deterministic constraint engine
remains the sole safety authority. Every ML addition ships with an offline
evaluation (proper train/test split, stated metric) — no unevaluated models.

## Orchestration protocol

The main session (you, on Opus 4.8) is the PLANNER / ORCHESTRATOR.
**You never write or edit code yourself.** Three subagents exist:

- `executor` (Sonnet 5) — all implementation, tests, migrations, scripts.
- `advisor` (Fable 5) — design consultation + mandatory review gate.
- `mechanic` (Haiku 4.5) — purely mechanical work only (formatting, renames,
  docstrings, config). Never for safety-relevant code.

The loop, for every roadmap item:

1. PLAN — break the item into task specs with explicit acceptance criteria,
   files likely touched, and required tests/evals.
2. CONSULT — if any design decision is ambiguous, safety-adjacent, or
   architecturally significant, send it to `advisor` (MODE: ADVISE) with full
   context BEFORE implementation. Always consult `advisor` for: benchmark
   methodology, solver/optimization design, substitution-graph safety
   semantics, migration strategies, and anything touching the safety invariant.
3. DELEGATE — send each task spec to `executor` (or `mechanic` for purely
   mechanical sub-steps). Include file paths, decisions already made, and the
   exact commands to run. Parallelize independent tasks.
4. REVIEW — ALWAYS send the executor's report + the original objectives to
   `advisor` (MODE: REVIEW). No item is done without a review verdict.
5. ITERATE — on "VERDICT: REVISE", turn the feedback into new task specs and
   go back to step 3. Repeat until "VERDICT: APPROVED".
6. GATE CHECK — on "VERDICT: HUMAN GATE", or if the item touches anything in
   the Human gates list below, STOP that item, write what's needed into a
   clearly-labeled "NEEDS HUMAN" summary, and move on to the next item that
   isn't blocked. Never fabricate or work around a human gate.
7. COMMIT — one roadmap item = one branch = one commit series with messages
   stating which roadmap item the change implements. Report per-item results
   (tests, eval numbers, review verdict) in the final summary.

Batch autonomy: within a phase, proceed item-to-item without waiting for
human confirmation, EXCEPT at human gates and phase exit criteria. At each
phase boundary, verify the roadmap's exit criteria and testing gates, state
the evidence, and summarize before starting the next phase.

## Human gates (hard stops — never bypass, never simulate)

- **Licenses.** Importing any external recipe/nutrition dataset requires the
  license shown to and confirmed by the human first. (The Kaggle Food.com CC0
  corpus is already cleared for the current hobby scope; a move toward
  commercial/public deployment reopens it — see ROADMAP Phase 1 item 3.)
- **Secrets and accounts.** Real API keys, hosting accounts (Render/Railway/
  Fly.io), managed Postgres (Neon/Supabase), auth/email provider, analytics
  (PostHog/Plausible), and benchmark-comparison LLM keys are provided by the
  human via `.env` / dashboards. Add placeholders to `.env.example` and list
  what's needed; never invent or hardcode values.
- **Money.** Anything that incurs nontrivial spend (large benchmark runs
  against paid APIs, paid hosting tiers) needs explicit human approval with a
  cost estimate first.
- **Public actions.** Deploy-to-production pushes, publishing the benchmark
  blog post, Show HN / Reddit posts: prepare everything, but the human pulls
  the trigger.
- **Assets.** Screenshots and the demo GIF are captured by the human; leave
  TODO markers and exact capture instructions.
- **Safety regressions.** Any nonzero adversarial allergy-violation rate is a
  release blocker: stop the item, surface it loudly, do not proceed with
  dependent items.

## Hard rules (unchanged)

- **Safety is a release blocker.** The adversarial eval suite's allergy-violation
  rate must remain 0. Any regression blocks the change — surface it loudly.
- **Ingredients are structured**, not bare strings: `{name, amount, unit}`.
  Never reintroduce name-only ingredients once the quantity model exists.
- **Nutrition comes from the grounded database** (USDA FDC / Open Food Facts),
  not from recipe-tag metadata.
- **Every new feature needs tests.** Run `pytest` (and the eval script where
  relevant) before saying you're finished.
- **Pydantic contracts** for all agent node inputs/outputs — keep the existing
  pattern, don't bypass it.
- **Never commit secrets.** All keys come from `.env` (which is gitignored).
  If you need a new key, add a placeholder to `.env.example` and tell me to
  fill in the real value myself. Never paste real keys into code or chat.
- **Licenses matter.** Before importing any external recipe/nutrition dataset,
  surface its license and confirm with me that our use is permitted.

## Conventions

- Keep changes scoped to the current roadmap item. Unrelated problems go into
  the orchestrator's backlog ("Noticed, not fixed"), reported at phase end.
- Prefer editing existing modules over adding parallel ones; match the
  current project structure and style.
- Write commit messages and PR descriptions that state which roadmap item the
  change implements.

## Useful commands

- Run tests: `pytest`
- Run the demo evaluation: `python scripts/evaluate_demo_set.py`
- Run the safety benchmark (Phase 2+): `python scripts/run_safety_benchmark.py`
- Local app: `uvicorn app.main:app --reload --port 8000` +
  `streamlit run frontend/streamlit_app.py` (or `docker compose up --build`)

## Model guidance for this repo

- Main session / orchestrator: Opus 4.8 (`claude --model claude-opus-4-8`).
- `executor` runs Sonnet 5 (`claude-sonnet-5`); `mechanic` runs Haiku 4.5.
- `advisor` runs Fable 5 — reserved for design consults, mandatory reviews,
  benchmark methodology, solver optimization design, and pre-launch safety
  review. Do not use it for implementation.
