# DEMO_SCRIPT.md — a 90-second scripted walkthrough

For interviews, portfolio reviews, or anyone who wants to see MacroChef work
in under two minutes. Written to be run against the **live URL**:
<https://ca-macrochef.orangeplant-d8bf2180.italynorth.azurecontainerapps.io/>.

> **Status note:** as of this writing, the local repo is ahead of what's
> deployed — ROADMAP.md Phases 3.2/3.3/4.3 (the checkpointer, the Chef chat
> agent, and this chat UI) exist in the codebase and pass their full test
> suite, but require a human-triggered `workflow_dispatch` promote (see
> `docs/DEPLOY.md`) before they're live at the URL above. This script
> describes the intended experience once that promote has happened — if
> you're reading this before that, the "Chef chat" step below won't yet be
> reachable on the live site (it will 404 or show the old "coming soon"
> placeholder). This is an honest gap, not an oversight: see
> `docs/BACKLOG.md`'s F3 entry for the one remaining piece (an image-upload
> control for the HITL flow) that even a full promote won't close yet.

## Before you start

- Have the URL open in a normal browser tab, not incognito (the anonymous
  session cookie needs to persist across the two steps below).
- No login, no signup — MacroChef has no accounts. Every session is an
  anonymous, signed token minted on first request.

## Minute 1 — live agent reasoning, not a spinner

1. Click **"Find recipes"** (or navigate to `/plan`) from the landing page.
2. Type a few ingredients you have on hand — e.g. `chicken, rice, broccoli`
   — and set an allergy in the profile form, e.g. add "peanuts."
3. Click **"Find recipes."** *Say while it runs:* "Most apps show a spinner
   here for 20-30 seconds. This one streams the graph's own reasoning live —
   intake, retrieval, safety filtering, nutrition scoring — as Server-Sent
   Events, one row per node, as it actually happens."
4. Point out the timeline filling in row by row (`RunProgressTimeline`) —
   each row is a real `RunEvent` from the backend's own observability layer
   (`app/observability/events.py`), not a fake progress bar.
5. When results land, open one recipe's detail and point at the **verified
   vs. estimated** macro badges. *Say:* "Every number here traces back to a
   USDA FoodData Central lookup or is honestly labeled as estimated — never
   silently guessed."

## Minute 2 (0:60-1:30) — the flagship feature: Chef, the tool-calling agent

1. Click **"Chat with Chef"** (or navigate to `/chat`).
2. First visit: a profile form appears — *say:* "Chat is multi-turn, so your
   allergy profile gets bound once, at the start of the conversation — Chef
   can never be talked into forgetting it later, because it's never given
   the chance to see a different one." Fill in the same peanut allergy, click
   **"Start chat."**
3. Type: `Find me a high-protein dinner and check it's safe for my allergy.`
4. *While it streams, say:* "Watch the tool-call chips appear before the
   final answer — Chef is calling `search_recipes`, then
   `check_recipe_safety`, live, and you're seeing each call as it happens."
   Click a chip (e.g. `🛡 check_recipe_safety`) to expand it and show the
   real per-recipe verdict.
5. When the final answer lands, *say:* "That safety verdict didn't come from
   the language model's judgment — it came from a deterministic Python
   function, `constraint_engine.validate_recipe`, the exact same one the
   planner flow above uses. There's a second, silent gate behind this too: if
   Chef ever names a recipe as safe without having called that check first
   in the same turn, the response never ships — it's rejected and retried
   automatically, or a generic fallback message is sent instead. That gate
   found two real bugs in its own first review pass, described in
   `docs/CASE_STUDY.md`."

## Minute 2:30-2:? (bonus, if there's time) — the receipts

1. Click **"Evals"** (or navigate to `/evals`).
2. *Say:* "Every claim on the README is backed by a number on this page, not
   just prose — retrieval quality, the safety benchmark's pass rate, both
   the raw judge-flagged count and the adjudicated-true count side by side,
   per this project's own release-gate policy: the judge is never modified
   to make the second number smaller."

## What this script deliberately skips

- **The HITL image-confirmation pause** (upload a pantry photo, the run
  pauses mid-graph on a low-confidence ingredient guess, you correct it,
  the run resumes) — fully built and tested at the API level
  (`tests/test_hitl_resume.py`) but has no click-through UI yet
  (`docs/BACKLOG.md` F3). Worth narrating verbally ("this exists, tested,
  just not wired to a button yet") rather than pretending it isn't there.
- **The staging environment** (ROADMAP 5.3) — an engineering-audience detail
  (auto-deploy on every merge, before a human promotes to prod), not
  something a demo audience needs to see clicked through.

## Acceptance check

Someone who has never seen this project before should be able to run this
script themselves, end to end, using only this document and the live URL —
no access to the codebase, no verbal narration required beyond what's
written above.
