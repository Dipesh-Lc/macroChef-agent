# Status handoff — ROADMAP execution, 2026-07-28 overnight session

## If you only read this

Landed and verified green on `main`, in order: **Step 1.1** (structured
run events), **Step 4.1+4.4** (landing page, killed the placehold.co
placeholder art), **Step 1.2** (LLM cost ledger + `/admin/llm-usage`).
Plus three docs: `ROADMAP.md`/`docs/BACKLOG.md` now tracked,
`docs/HUMAN_INPUTS.md` (new — your action items), and
`docs/PHASE3_HITL_CHEF_SPEC.md` (pre-implementation spec for the two
steps I deliberately did NOT build: 3.2 HITL checkpointer, 3.3 Chef
agent — both safety-adjacent, held for a real design consult with you).

**Session stopped, not by choice**: two more agents (Step 1.3 OTel,
Step 4.5 macro viz) failed immediately on launch — account API usage
limit hit, resets 4:20am Europe/Berlin. Neither wrote any code (verified:
their branches are empty, identical to `main`'s HEAD). Nothing lost,
nothing to clean up, just less done than planned. I did not retry in a
loop per instructions — if you're reading this well after 4:20am Berlin
and want the rest of Phase 1/2/3.1 finished, just say so.

---

## Strategy this session (advisor-approved, you weren't available)

You said to implement ROADMAP.md, parallelize for speed, and consult the
advisor for any decision that would normally need you since you'd be
asleep ~8 hours. I ran one advisor strategy consult before starting
(transcript context below) and followed its four recommendations:

1. **Scope**: Phase 1 → Phase 2 → Step 3.1 on a sequential backend track,
   hard stop before Step 3.2/3.3 (write a spec instead of code) because
   they're a new LLM-driven attack surface next to the safety-gate
   invariant, and CLAUDE.md already classifies "the Chef agent's tool
   gating and response gate" as FULL TREATMENT — mandatory advisor
   consult *before* an executor starts, which can't happen with you
   asleep and no real product decisions made yet (see the five open
   questions in the spec doc).
2. **OTel backend**: recommended **Honeycomb** as the documented default
   (simplest OTLP story, generous free tier) — logged in
   `docs/HUMAN_INPUTS.md` H1. Never got built (see below).
3. **Parallelization**: three tracks in separate git worktrees — backend
   core (sequential, one file-touching track at a time), frontend work
   with zero backend dependency, and docs. This is why 4.1/4.4 (and the
   started-but-failed 4.5) ran out of roadmap order — deliberately pulled
   forward because they don't touch any file the backend track touches.
4. **Stopping condition**: land on a green, committed, acceptance-criteria
   -met step boundary, never mid-step; write this doc regardless of how
   far I got. That's what happened — the two failures happened *before*
   any file was touched, so there's no half-finished step anywhere.

---

## Done — with evidence

### ROADMAP 1.1 — Structured run events + request IDs
- Commit `eed6d82` (merged `e570b10`).
- `app/observability/events.py`: `RunEvent` model, `EventSink` protocol
  (`InMemorySink`, `LogSink`), `@traced_node` decorator on all 19 graph
  node functions, `run_id` contextvar wired through `RequestIdMiddleware`
  in `app/main.py`, request_id now on every log line.
- Evidence: `tests/test_observability_events.py` (10 tests) green; full
  `EMBEDDING_PROVIDER=hash pytest` run 3x independently by the executor,
  then once more by me after merge — all exit 0, no failures.
- One noticed-not-fixed: `ruff check .` has ~617 pre-existing errors
  repo-wide (mostly `tests/` import ordering), confirmed pre-existing on
  `main` before this session, not introduced by any of tonight's work.
  Worth a dedicated cleanup pass — not currently blocking anything since
  CLAUDE.md's "Done means" for individual steps was checked file-by-file
  against files each step touched, not the whole repo.

### ROADMAP 4.1 + 4.4 — Landing page + placeholder art fix
- Commit `5d67764` (merged `9c71943`).
- New `/` → `LandingPage` (hero, 3 proof chips with **real current
  numbers pulled from the README**, not the roadmap's stale "269/269" —
  worth you double-checking the exact wording reads right), pipeline
  diagram of the actual graph nodes, footer. Planner moved to `/plan`.
  New `/chat` → existing `ComingSoonPage` (Chef agent isn't built yet).
- Killed `placehold.co` everywhere — found and fixed it server-side too
  (`app/services/recipe_image_service.py`,
  `recipe_discovery_service.py`, `recipe_validation_service.py` were all
  injecting placehold.co URLs into `image_url`, not just the frontend).
  New `RecipeArt.tsx`: zero-network, deterministic gradient + food-icon,
  title never clipped.
- Evidence: full web matrix (`lint && typecheck && test -- --run &&
  build`) green, 146/146 tests. Full backend pytest green (1539 tests,
  4 pre-existing skips) — this one touched backend files so I ran the
  whole suite, not just the touched ones.
- Deviations worth your eyes: "Chat with Chef" CTA goes to a coming-soon
  page rather than being omitted; the safety proof chip text was
  rewritten to match CLAUDE.md's own release-gate semantics (adjudicated
  number + raw judge-flagged count, both shown) rather than the stale
  roadmap number — check it reads the way you want.

### ROADMAP 1.2 — LLM call ledger
- Commit `fad1805` (merged `bf3e654`).
- New `llm_calls` table, `app/observability/llm_ledger.py`
  (`PRICE_PER_MTOK` table, real token-usage extraction per provider —
  caught that the OpenAI path here uses the Responses API, not Chat
  Completions, so usage fields are `input_tokens`/`output_tokens` not
  the more common `prompt_tokens`/`completion_tokens`), new
  session-gated `GET /admin/llm-usage?days=7`.
- A `user_id` contextvar (mirroring 1.1's `run_id` one) bound at graph-
  invocation entry points, since `user_id` isn't otherwise threaded down
  to the LLM-call choke point.
- Evidence: 12/12 new ledger tests, full pytest green (confirmed
  independently by me post-merge), manual end-to-end smoke test against
  an isolated sqlite DB confirming rows appear correctly and the
  endpoint 401s without a session.
- **Flagged for you** (also in `docs/BACKLOG.md` I3): the admin endpoint
  is session-gated but not user-scoped — any anonymous session can see
  total app-wide LLM spend. Fine for a single-maintainer demo, not once
  there are real distinguishable accounts.

### Docs
- `ROADMAP.md` and `docs/BACKLOG.md` were sitting untracked from the
  planning session that produced them — now committed (`2685532`), plus
  one new BACKLOG entry (I3, above).
- `docs/HUMAN_INPUTS.md` (new) — durable home for the "code ships, but
  an account/secret/purchase needs you" half of any step. Currently one
  entry: H1, the OTel hosted-backend account (see below).
- `docs/PHASE3_HITL_CHEF_SPEC.md` (`e8cf2e2`) — 688-line pre-implementation
  spec for Step 3.2 (HITL checkpointer) and Step 3.3 (Chef agent), with
  verified file:line references, concrete function signatures, DB table
  definitions, and — most importantly — **five open design questions
  that are genuinely yours to decide**, not things an agent should
  guess: multi-recipe response-gate semantics, the `remember()` tool's
  cap/lifecycle, SqliteSaver vs PostgresSaver default, whether
  `ground_nutrition` needs its own rate-limit bucket (it'd be the app's
  first live request-path USDA call), and 403-vs-404 for cross-user
  thread isolation (checked: no existing ownership-check precedent in
  the codebase to copy). Read this before greenlighting an executor on
  3.2/3.3 — that's a FULL TREATMENT step per CLAUDE.md, needs you in the
  loop.

---

## NOT done — and why

### ROADMAP 1.3 — OpenTelemetry tracing
Never started. The agent failed on launch (API usage limit), before
touching any file. Spec is unchanged from ROADMAP.md; grounding context
for whoever picks it up next: build on the already-merged
`app/observability/events.py`/`llm_ledger.py`, make span emission a true
no-op when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset, Honeycomb is the
recommended backend (`docs/HUMAN_INPUTS.md` H1).

### ROADMAP 4.5 — Macro visualization + polish
Also never started, same reason, same lack of any partial file changes.

### ROADMAP 2.1, 2.2, 2.3, 3.1
Not attempted — sequentially blocked behind 1.3 in the backend track's
ordering (2.2 in particular can't safely run parallel to 2.1, both
rewrite `model_provider.py`; ordering matters here, not just speed).

### ROADMAP 3.2, 3.3
Deliberately deferred per the advisor consult, see "Strategy" above.
Spec is ready (`docs/PHASE3_HITL_CHEF_SPEC.md`); implementation needs a
FULL TREATMENT advisor design consult with you present first.

### Phase 5, Phase 6.1/6.2/6.3 (README/CLAUDE.md rewrite, demo assets)
Not attempted at all tonight — lower priority per the roadmap's own
impact-per-hour ordering, and the session ended before backend Phase 1/2
work cleared enough runway to reach them.

---

## Recommended next steps

1. If you want the rest of Phase 1/2/3.1 finished, just ask — nothing
   about tonight's stoppage was a design problem, it was an account
   limit. Steps 1.3 and 4.5 can restart cleanly from their ROADMAP.md
   specs (or from this doc) with zero cleanup needed.
2. Before any executor touches Step 3.2 or 3.3: read
   `docs/PHASE3_HITL_CHEF_SPEC.md` §3 (the five open questions) and
   either answer them inline in that doc or run a real advisor consult
   with you present to argue through them.
3. Sanity-check the landing page copy (`web/src/pages/LandingPage.tsx`)
   — several proof-chip links point at GitHub anchors that assume
   specific README section headers exist; worth a 30-second look.
4. `docs/HUMAN_INPUTS.md` H1 is waiting on you: create a Honeycomb
   account, two env vars, and — once Step 1.3 eventually lands — a real
   trace screenshot for the README.
