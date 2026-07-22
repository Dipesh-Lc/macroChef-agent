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

## Current mission: ship first

> Target: a live public URL on Azure Container Apps with rate limits and
> analytics, as fast as possible. Everything else is subordinate.

Phases 0–1 are complete. The remaining roadmap (`docs/ROADMAP.md`) and the
batch prompts in `docs/phase-2-5-session-prompts.md` are still the reference
material, but they no longer set the pace — shipping does. Where a roadmap
item, a methodology refinement, or a corpus-quality pass would delay the
public URL without changing safety or correctness, it goes to
`docs/BACKLOG.md` (see "Default to backlog" below) instead of being done now.

**Secondary objective — employability skills demonstration.** This project
also serves as a portfolio demonstrating the skills in
`docs/SKILLS_MATRIX.md` (classic ML with scikit-learn, PyTorch/deep
learning, Hugging Face, MLflow/MLOps, SQL/Postgres, major-cloud deploy,
CI/CD). When two implementation options are otherwise comparable, prefer
the one that exercises a skill from the matrix, and keep the matrix updated
as items land. This objective is subordinate to shipping: it never delays
the live URL, it NEVER overrides the safety invariant, and it never adds
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
- `advisor` (Fable 5) — design consultation + review gate, for FULL TREATMENT
  items only (see below).
- `mechanic` (Haiku 4.5) — purely mechanical work only (formatting, renames,
  docstrings, config). Never for safety-relevant code.

### Two-tier review protocol

Advisor consult + review is no longer mandatory for every item — that was too
slow for a ship-first mission. Classify every item into one of two tiers:

- **FULL TREATMENT** — advisor consult (MODE: ADVISE) where the design is
  ambiguous, plus mandatory review (MODE: REVIEW). No shortcuts. Applies to:
  - `app/services/constraint_engine.py`
  - anything deciding an **allergy or diet outcome**
  - anything that would let the **LLM decide a safety outcome**
  - **secrets, auth, rate limiting, data isolation between users**
- **EVERYTHING ELSE** — one executor pass, **no advisor review**. The bar is
  **`pytest` green + `python scripts/evaluate_demo_set.py` at
  allergy_violation_rate 0.000**. Not perfection. **Cap at ONE revise
  round** — if the second pass isn't clean, backlog the remainder
  (`docs/BACKLOG.md`) and move on.

**Default to backlog.** Skip eval-methodology polish, report wording,
citation verbatim-ness, docstring-accuracy passes, and corpus quality work
unless shipping actually depends on them. When something is noticed but not
fixed, it goes in `docs/BACKLOG.md` **with enough detail to act on later**
— file paths, what was already decided, any pre-registered criteria. Not a
vibe, not a bare TODO comment. "Refine later" means never unless it is
written down there.

The loop, for every roadmap item:

1. PLAN — break the item into task specs with explicit acceptance criteria,
   files likely touched, and required tests/evals. Classify the item as
   FULL TREATMENT or EVERYTHING ELSE using the tiers above.
2. CONSULT (FULL TREATMENT only) — if any design decision is ambiguous,
   safety-adjacent, or architecturally significant, send it to `advisor`
   (MODE: ADVISE) with full context BEFORE implementation. EVERYTHING ELSE
   items skip this step.
3. DELEGATE — send each task spec to `executor` (or `mechanic` for purely
   mechanical sub-steps). Include file paths, decisions already made, and the
   exact commands to run. Parallelize independent tasks.
4. REVIEW — FULL TREATMENT items: ALWAYS send the executor's report + the
   original objectives to `advisor` (MODE: REVIEW); no such item is done
   without a review verdict. EVERYTHING ELSE items: skip advisor; the item
   is done once `pytest` is green and `evaluate_demo_set.py` reports
   allergy_violation_rate 0.000.
5. ITERATE — on "VERDICT: REVISE", turn the feedback into new task specs and
   go back to step 3. FULL TREATMENT items repeat until "VERDICT: APPROVED".
   EVERYTHING ELSE items get at most one revise round; if the second pass
   still isn't clean, backlog the remainder and move on.
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
- **Safety regressions.** A nonzero **adjudicated-true `inherent`**
  violation rate on the adversarial benchmark is a release blocker: stop
  the item, surface it loudly, do not proceed with dependent items. (Gate
  semantics fixed by the human on 2026-07-17 — see "Honest scope" below
  for the full definition. Agents may not amend it.)

## Honest scope (hard rule, not a preference)

**Release-gate semantics — decided by the human on 2026-07-17 (option
"adjudicated zero"). The pre-registration was agent-authored, so agents
could not amend it; this amendment is the human's and agents may not
revise it further:**

- The release gate is **zero adjudicated-true `inherent` violations** on
  the adversarial benchmark.
- Every judge flag receives a **written, per-case, advisor-reviewed
  adjudication** (verdict TRUE_VIOLATION or JUDGE_FP, matched term +
  field, served recipe's actual ingredients, citable rule; ambiguity
  defaults to TRUE_VIOLATION — see
  `data/evaluation/adjudication_20260717T145539Z.md` for the convention).
- The raw judge-flagged count is **always published alongside** the
  adjudicated number ("judge-flagged N/259; adjudicated true M/259").
  Judge false positives stay in the raw number forever.
- **The judge is never modified** to close the gap between the two
  numbers.

Until the adjudicated-true inherent number is zero: the deployed app
carries a prominent disclaimer (hobby project, not medical advice,
allergy users must verify ingredients themselves), and **no "0
violations" claim is published anywhere** — not the UI, not the README,
not a blog post or launch draft. When the gate is met, any published
claim states both numbers. Under-claim until the number is real.

## Hard rules (unchanged)

- **Safety is a release blocker.** The adversarial benchmark's
  **adjudicated-true `inherent`** violation rate must remain 0, per the
  gate semantics in "Honest scope" (judge-flagged count always reported
  alongside; judge never weakened). Any regression blocks the change —
  surface it loudly.
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
  `docs/BACKLOG.md` ("Noticed, not fixed") with enough detail to act on later
  — see "Default to backlog" above.
- Prefer editing existing modules over adding parallel ones; match the
  current project structure and style.
- Write commit messages and PR descriptions that state which roadmap item the
  change implements.

## Useful commands

- Run tests: `pytest`
- Run the demo evaluation: `python scripts/evaluate_demo_set.py`
- Run the safety benchmark (Phase 2+): `python scripts/run_safety_benchmark.py`
- Local app (SPA rebuild W6, single-process cutover — no more Streamlit):
  `uvicorn app.main:app --reload --port 8000` in one terminal +
  `cd web && npm run dev` in another (Vite dev server, proxies the backend
  API prefixes to :8000 — see `web/vite.config.ts`). For a build-parity
  smoke test of the production single-process image instead, use
  `docker compose up --build` (API-only; see `docker-compose.yml`'s
  comment for why the SPA dev loop runs outside Docker).

## Model guidance for this repo

- Main session / orchestrator: Opus 4.8 (`claude --model claude-opus-4-8`).
- `executor` runs Sonnet 5 (`claude-sonnet-5`); `mechanic` runs Haiku 4.5.
- `advisor` runs Fable 5 — reserved for design consults, mandatory reviews,
  benchmark methodology, solver optimization design, and pre-launch safety
  review. Do not use it for implementation (Fallback - Opus 4.8 if Fable 5 not available).
