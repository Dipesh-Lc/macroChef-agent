# Status handoff — ROADMAP execution, 2026-07-28 overnight session

## If you only read this

**14 ROADMAP steps shipped, merged to `main`, and independently verified
green tonight**, each on its own commit series: all of Phase 1 (1.1,
1.2, 1.3), all of Phase 2 (2.1, 2.2, 2.3), Step 3.1 (SSE streaming),
Step 3.4 (evals in CI), Steps 4.1, 4.2, 4.4, 4.5, 4.6 (landing page,
live streaming UI, real card art, macro charts, public eval page),
Steps 5.1 and 5.4 (Alembic migrations, security headers), and Steps 6.1
(README rewrite — 6.2/CLAUDE.md is a special case, see below). Current
`main` tip: `b8aa798`. Final verification, run once more after
everything landed: full backend `pytest` (100%, zero failures), full
web matrix (`lint && typecheck && test && build`, all green),
`scripts/audit_diet_leaks.py` (0.0% leak rate, all 4 diets).

**Deliberately not built**: Steps 3.2 (HITL checkpointer) and 3.3 (Chef
conversational agent) — both safety-adjacent, spec'd in
`docs/PHASE3_HITL_CHEF_SPEC.md` with five open design questions that are
genuinely yours to decide. Step 4.3 (chat UI) is blocked on 3.3. Steps
5.2 (pgvector) and 5.3 (staging CD) weren't attempted — lower priority
per the roadmap's own ordering, and both carry real infra
cost/complexity that deserves dedicated attention rather than being
rushed at the end of a long session. Step 6.3 (demo GIFs/case study)
wasn't attempted — no way to record video/screenshots in this
environment.

**One decision left entirely to you**: `CLAUDE.md` is gitignored
(commit `5601fe9`, "internal build tooling, not part of the shipped
product"), which conflicts with ROADMAP Step 6.2's instruction to
rewrite it. I did not touch it. A reviewed, updated candidate version
exists at
`.claude/worktrees/agent-adb1a0db0427b9ee8/CLAUDE.md` (171 lines,
preserves every invariant/human-gate/orchestration-protocol section
verbatim in spirit, updates the project map and commands to reflect
tonight's work) if you want to adopt it — it's untracked either way so
there's no git history to fall back on if you overwrite the current one,
worth a manual diff first.

## The one incident worth knowing about

Mid-session, a `git checkout <branch> -- .` I ran to preview a merge
conflict instead overwrote the whole working tree. `git reset --hard
HEAD` recovered everything committed, but permanently lost two
pre-existing **uncommitted** edits that were sitting in your working
tree before this session started: a hand-edit to `docs/DEPLOY.md` (the
committed version didn't yet mention `/evals/latest`; the lost edit
did) and a regenerated `data/processed/grounding_report.md` (low-stakes
— it's a generated file, rerun `scripts/ground_corpus.py --report-path
...` for a fresh one). Neither was ever committed, so there's no git
object to recover from. This is the one thing tonight that isn't fully
recoverable — flagging plainly, not burying it.

## Strategy (advisor-approved, since you were unavailable)

You said to implement ROADMAP.md, parallelize for speed, and consult
the advisor for decisions that would normally need you. One strategy
consult ran before starting; I followed its recommendations throughout:
work the backend track (files overlap between consecutive steps)
strictly sequentially; run frontend/docs work with no backend
dependency in parallel worktrees; hard-stop before 3.2/3.3 and write a
spec instead, since they're a new LLM-driven attack surface next to the
safety-gate invariant and CLAUDE.md already classifies "the Chef
agent's tool gating and response gate" as FULL TREATMENT (mandatory
advisor consult *before* an executor starts — meaningless without you
present to answer real product questions); only ever land on a green,
committed, acceptance-criteria-met step boundary; write a handoff
regardless of how far things got. You said "keep going" twice more as
the night progressed, which is why the session extended well past the
originally-scoped Phase 1+2+3.1 into Phase 4/5/6 work that 3.1/3.4
unblocked.

The session hit account API usage limits three times (roughly 4:20am,
3pm, and 8pm Europe/Berlin) — each time, agents that hadn't started
writing code yet failed cleanly (verified via git: no branches, no
partial commits) and resumed successfully on retry with no lost work.

## Done — with evidence (chronological)

### Phase 1 — Observability
- **1.1** Structured run events + request IDs. `app/observability/events.py`.
- **1.2** LLM call ledger + `GET /admin/llm-usage` (session-gated, not
  user-scoped — `docs/BACKLOG.md` I3, deliberate for a single-user demo).
- **1.3** OpenTelemetry tracing, true no-op unless
  `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Honeycomb is the documented
  default backend (`docs/HUMAN_INPUTS.md` H1) — account/secrets/
  screenshot still on you.

### Phase 2 — LLM layer hardening
- **2.1** Native structured outputs (`generate_structured` in
  `model_provider.py`) — real per-provider mechanisms (Gemini
  `response_schema`, OpenAI Responses-API `text.format` json_schema,
  Anthropic forced tool-use), one-shot repair loop, removed the old
  duplicate regex/brace-scan vision extractor entirely.
- **2.2** Async provider calls + fan-out. **Measured 3.76x speedup**
  (102.8s → 27.4s) fanning out the actual sequential bottleneck — the
  corpus grounding job (confirmed live `/recipes/recommend` doesn't
  call USDA at request time at all, so the roadmap's literal
  before/after criterion didn't apply; measured the real one instead).
- **2.3** Semantic response cache (`llm_cache.py`), TTL per purpose (30d
  for detailed instructions, no cache for recipe generation — "keep
  novelty"), `LLM_CACHE_ENABLED` kill switch.

### Step 3.1 — SSE streaming (the centerpiece)
`POST /recipes/recommend/stream` — live per-node events, terminal
`result`/`error` event, 10s heartbeats for ACA. Runs the unmodified
graph in a worker thread while polling a per-request event sink,
chosen over LangGraph's native `.stream()` because the graph can fall
back to a non-LangGraph sequential runner and both paths needed one
event mechanism. Also fixed a real bug found along the way:
`builder.py`'s bare `except Exception` around the *entire* graph build
would have silently swallowed any real construction error — narrowed to
match the import-only pattern the library-graph builder already used.
Old sync endpoint provably untouched (its isolation test suite re-run
unmodified, still passes).

### Step 3.4 — Evals as a visible, CI-enforced system
`scripts/run_all_evals.py` (mock-provider-only, no `--provider` flag
exists at all — verified this can't trigger real spend), hard CI gate
on the **adjudicated-true** count (not the raw judge-flagged count,
which has expected occasional false positives). **Found and fixed a
real pre-existing bug**: neither this script nor the original
`run_safety_benchmark.py` ever called `init_db()`, so a fresh sqlite
file made every case silently serve 0 recipes — a false-negative safety
gate. Proved the gate works with a real fault-injection experiment
(temporarily made `validate_recipe` admit everything, confirmed the
gate fails, reverted cleanly, added a permanent regression test for it).
`GET /evals/latest` is public/read-only; `data/evaluation/eval_report.json`
doesn't exist yet (deliberately — a partial/rushed run would misrepresent
itself as authoritative; run `python scripts/run_all_evals.py` for real
data whenever you want it).

### Phase 4 — Frontend
- **4.1+4.4** New landing page at `/` (planner moved to `/plan`), killed
  `placehold.co` everywhere — found and removed it server-side too.
- **4.2** Live streaming progress timeline (`RunProgressTimeline.tsx`,
  `lib/sse.ts` — a hand-rolled fetch-based SSE parser since `POST` SSE
  can't use native `EventSource`) replacing the frozen "Finding
  recipes…" button. Falls back to the old sync call automatically only
  if the stream transport itself fails before any event arrives.
- **4.5** Hand-rolled SVG macro radial/trend-bar charts (no new chart
  dependency), mobile bottom-nav + accordion, micro-interactions
  respecting `prefers-reduced-motion`. Honestly documented that neither
  `DayPlan` nor `WeeklyPlan` currently carries a per-macro verified/
  estimated flag — the hatch-pattern mechanism exists and is tested but
  every current caller renders solid (a real backend gap, not
  fabricated data).
- **4.6** Public `/evals` methodology page. Regenerated
  `web/openapi.json`/`types.gen.ts` twice — the branch's own regen was
  stale by two steps' worth of schema drift (missing 2.1/2.3's
  `parse_fallback_count`/`cache_hit_count` fields), I caught it and
  regenerated again against the fully-merged state; `npm run typecheck`
  confirms it's current now.

### Phase 5 — Infra
- **5.1** Alembic migrations + a real schema-drift CI gate
  (`alembic check` against a fresh sqlite DB). Postgres path verified
  by code review and reuse of `db.py`'s existing normalization logic,
  **not** independently tested against a live Postgres instance (none
  available in this environment) — worth a real verification pass
  before the next prod deploy touches schema.
- **5.4** Security headers (CSP — verified PostHog needs zero CSP
  allowance since it's server-side only, no `posthog-js` anywhere in
  `web/`), HSTS behind a new `ENABLE_HSTS` flag (default off), gzip,
  confirmed cache headers for hashed assets already existed correctly.

### Phase 6 — Docs
- **6.1** README rewritten to the roadmap's exact 8-part spec: honest
  safety badge (0/269 adjudicated, 73 raw-flagged called out alongside,
  never collapsed to one number), 5 receipt-linked bullets, two Mermaid
  diagrams, a dedicated safety section with a real adversarial case
  quoted inline, honest evals section (states plainly that
  `/evals/latest` has no committed report yet), verified 5-line
  quickstart, engineering notes. Dropped a rich "Engineering deep
  dives" section to fit the spec's line budget — fully recoverable from
  git history (`4572b05`) if you want to fold pieces of it into a
  future `docs/CASE_STUDY.md` (Step 6.3, not started).
- **6.2** CLAUDE.md — see "one decision left entirely to you" above.

### Docs infrastructure added tonight
- `ROADMAP.md`/`docs/BACKLOG.md` tracked (were sitting untracked).
- `docs/HUMAN_INPUTS.md` — **H1** (Honeycomb OTel account, code ready)
  and **H2** (nightly real-judge benchmark run, deliberately never
  built — no code, no schedule trigger, needs a cost estimate + your
  approval first per CLAUDE.md's money gate).
- `docs/PHASE3_HITL_CHEF_SPEC.md` — 688-line pre-implementation spec for
  3.2/3.3 with five open design questions.

## Recommended next steps for you

1. `docs/HUMAN_INPUTS.md` — Honeycomb account (H1), and a real decision
   on the nightly judge run (H2).
2. Decide on the `CLAUDE.md` question above — diff the candidate
   against your current local copy before deciding.
3. Read `docs/PHASE3_HITL_CHEF_SPEC.md` §3 before anyone starts 3.2/3.3.
4. Run `python scripts/run_all_evals.py` for real once you want
   `/evals/latest` and the new `/evals` page showing live data.
5. Verify the Alembic Postgres path against a real (even throwaway)
   Postgres instance before it matters at deploy time — Step 5.1 was
   only tested against sqlite in this environment.
6. The `docs/DEPLOY.md`/`grounding_report.md` incident above — no action
   needed unless you remember what was in the lost `DEPLOY.md` edit.
