# Launch drafts

Drafts only. Posting is a human gate (see CLAUDE.md "Human gates — Public
actions") — nothing here gets published without the human pulling the
trigger. Every draft below states both benchmark numbers together
("judge-flagged N/259; adjudicated true M/259") per CLAUDE.md "Honest
scope" — never a bare "0 violations" claim — and keeps the hobby-project /
not-medical-advice disclaimer. No feature is claimed live that isn't; the
"remaining macros" weekly planner is explicitly marked as roadmap Phase 3,
not shipped.

Fill in placeholders (`[LIVE_URL]`, `[REPO_URL]`) before posting.

---

## 1. Show HN draft

**Title:**

Show HN: MacroChef – a meal planner where the LLM never decides your allergy safety

**Body:**

I built MacroChef, a meal-planning agent with one non-negotiable design rule:
**the LLM never enforces allergies and never computes nutrition — deterministic
code does.** The model is only allowed to touch the fuzzy, non-safety-critical
parts: parsing messy pantry text ("chikcen brest, spinch"), ranking candidates,
and phrasing explanations. Anything that could hurt you if it were wrong runs
as plain, tested Python — a deterministic constraint engine for allergies/diet
type/dislikes/cook time, and a deterministic nutrition scorer grounded in USDA
FoodData Central. The LLM cannot override a safety decision by construction,
not by prompt.

The reason this matters: generic recipe chatbots are confident and wrong about
hard constraints. Ask one for a peanut-free satay and it will cheerfully
suggest a peanut-containing "satay sauce" because it never separated the
safety decision from the language-generation decision. MacroChef treats meal
planning as a structured workflow where a LangGraph pipeline routes intake,
inventory confirmation, constraint building, retrieval (ChromaDB RAG),
deterministic safety filtering, deterministic nutrition scoring, ranking, and
LLM-phrased explanation through separate, typed (Pydantic v2) nodes — so the
safety-critical nodes are auditable in isolation from the LLM-touched ones.

To back that claim up rather than just assert it, I built a 371-case
adversarial benchmark: allergy-contradiction traps, hidden allergens (a
"satay sauce" that's secretly peanut-based), diet-type traps, and safe
controls to check for over-blocking, all authored blind before any run. On
the 259 release-blocking (inherent-severity) cases, the deterministic judge
flagged **17/259**; a written, per-case, second-reviewer-adjudicated pass
found **0/259 true violations** — the 17 flags are documented judge false
positives (mostly substring artifacts, like the word "dairy" inside the
title "Dairy-Free Chicken Fajita Plate" tripping a naive dairy-allergy
check on a recipe that contains no dairy). I publish both numbers together,
always — the raw judge-flagged count never gets quietly dropped, and the
judge itself is never modified to close the gap between the two numbers.
There's also a non-blocking "may-contain" precautionary partition
(judge-flagged 10/46, adjudicated true 6/46, tracked openly) and a
safe-control partition to catch over-blocking (0/60 — no safe recipe
incorrectly rejected).

This is a hobby project, not a certified nutrition or allergy-safety
product — not medical advice, and if you have a real food allergy you
should independently verify every ingredient yourself. The benchmark
measures this system's behavior on its own recipe corpus, not a
real-world guarantee.

Stack: FastAPI + Pydantic v2 backend, LangGraph workflow, ChromaDB RAG,
Streamlit frontend, SQLite memory, runs with zero API keys in mock mode.

Live demo: [LIVE_URL]
Repo (MIT-licensed code): [REPO_URL]

Would love feedback, especially from anyone who's built allergy/safety-critical
LLM features and hit the same "the model wants to be helpful even when helpful
is wrong" problem.

---

## 2. r/MealPrepSunday draft

**Title:**

I built a pantry-aware meal planner that won't suggest recipes with your
allergens (and shows its work)

**Body:**

Hey r/MealPrepSunday — sharing a side project I've been building: MacroChef,
a free meal-planning tool aimed at the "what can I actually cook with what's
in my fridge, that also hits my macros" problem.

How it works: you type (or eventually snap a photo of) what's in your
pantry, set your allergies/diet type/macro targets/max cook time, and it
retrieves and ranks recipes that actually fit — showing you a match score,
a shopping list for anything missing, and a plain-language explanation of
why each recipe was picked.

The part I'm most careful about: allergy filtering and nutrition math are
NOT decided by an AI model. They're handled by plain deterministic code —
the same recipe gets the same safety verdict every time, no "the AI
hallucinated an ingredient" risk. The AI is only used for the fuzzy stuff:
understanding messy typed-in pantry lists and writing the explanation text.

I stress-tested the safety side with an adversarial benchmark (371 cases
designed to trick it — hidden allergens, contradictory requests, etc.). On
the release-blocking cases, the automated checker flagged 17/259, and after
manually reviewing every single flag, 0/259 turned out to be real safety
misses (the rest were false alarms from the checker itself, like the word
"dairy" showing up in a "Dairy-Free" recipe title). I'm not claiming
perfection — it's a hobby project and not medical advice, so if you have a
real allergy, always double check ingredients yourself — but I wanted to be
upfront about the actual numbers instead of just saying "it's safe."

Recipe corpus is currently a mix of hand-curated seeds plus a public
Food.com dataset (a few thousand recipes), with a personal "recipe library"
feature so you can save and index your own recipes too.

Would love feedback from actual meal-preppers on what's missing or annoying.
Live demo: [LIVE_URL] — repo: [REPO_URL]

---

## 3. Macro-tracking community draft (r/fitness or MacroFactor community)

**Title:**

Built a tool that plans meals around your *remaining* macros for the day (allergy-safe by design) — feedback welcome

**Body:**

Long-time macro tracker, and one thing that's always bugged me about
meal-suggestion tools is that they either ignore your macros entirely or
they let an LLM "estimate" nutrition, which is exactly the kind of thing I
don't want guessed at. So I built MacroChef with a hard rule: nutrition
numbers come from a grounded database (USDA FoodData Central), computed by
plain deterministic code — never from an LLM's estimate and never from a
recipe's self-reported tags. Same for allergy/diet filtering: it's
deterministic, not "the AI decided this looked safe."

Today it does pantry-aware recipe recommendation: tell it what's in your
kitchen and your macro targets, diet type, and allergies, and it returns
ranked recipes with a computed macro-fit score and a shopping list for
what's missing.

Heads up on scope honesty: the workflow I actually want — "here's what I've
eaten today, plan dinner around my *remaining* macros for the day" — is on
the roadmap (Phase 3) but not live yet. What's live today is single-meal
recommendation against a full macro target, not a running daily-remaining
calculation. Didn't want to oversell that.

On the engineering-seriousness side, since this is exactly the kind of tool
where a wrong answer can genuinely hurt someone (allergies, not just bad
macros), I built and ran a 371-case adversarial safety benchmark
specifically to try to trick the system into serving an allergen. On the
259 release-blocking cases: the automated judge flagged 17, and a full
manual per-case review found 0 of those 17 were real violations (documented
false positives, published alongside the raw count — not swept under the
rug). There's also a non-blocking "may-contain" category (10 flagged, 6
confirmed real, disclosed and tracked openly rather than hidden) and a
safe-control check to make sure it's not just over-blocking everything
(0/60 false rejections).

Hobby project, not medical advice — if you have a real allergy, verify
ingredients yourself regardless of what any app tells you.

Live: [LIVE_URL] / Repo: [REPO_URL] — genuinely want feedback on whether the
remaining-macros planner (Phase 3) is worth prioritizing next.
