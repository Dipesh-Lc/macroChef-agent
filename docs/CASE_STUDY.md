# CASE_STUDY.md — two war stories from this repo's own history

Not a marketing pitch — every number here is traceable to a specific commit
in this repo. Written for talking points and blog-post material (ROADMAP.md
Step 6.3), pulled from the two hardest, most instructive problems this
project actually hit: measuring and closing a real data-completeness gap,
and building an adversarial safety benchmark rigorous enough to trust its
own "clean" result.

---

## War story 1 — "53% coverage" turned out to be measuring the wrong thing

**The setup.** MacroChef's nutrition math depends on converting every recipe
ingredient into grams — `"2 tbsp of olive oil"` isn't useful to a scorer
until it's `"27g"`. Early on, the metric tracked for this was "recipes with
a populated `unit` field," and it looked reasonable: most ingredient rows
had *some* unit string attached.

**The problem, once actually measured.** A dedicated measurement script
(`scripts/measure_gram_computability.py`, commit `705e4c5`) revealed that
"unit field populated" was the wrong proxy entirely. Having a unit string
like `"tbsp"` doesn't mean the system can *convert* it — that conversion
depends on two small, hand-curated lookup tables: `_DENSITY_G_PER_ML`
(volume → grams, e.g. how many grams a milliliter of olive oil weighs) and
`_PIECE_WEIGHT_G` (count → grams, e.g. how many grams one "large egg"
weighs). The real bottleneck wasn't unit *presence* — it was table
*coverage*. The honest baseline, once measured correctly, was **36.71%**
grams-computable.

**The fix, and the discipline around it.** Rather than mass-guess plausible
density figures, the fix (`d2c31fc`) expanded both tables under a strict
**"cite or omit" rule**: every new entry — roughly 40 brand-new base
ingredients plus ~150 aliases reusing an existing entry's citation for
genuinely density-equivalent compound names (`"all purpose flour"` → the
existing `"flour"` entry) — needed a real source (USDA FDC household-measure
weights, King Arthur Baking's ingredient-weight chart). Ambiguous terms —
bare `"oil"` with no varietal specified, `"nuts"` with no species, blended
products like curry powder, anything requiring an ABV-adjusted alcohol
figure — were deliberately **skipped, not guessed**, and logged in
`docs/BACKLOG.md` for a future pass instead. `_normalize_for_density_lookup`
kept its strict, non-fuzzy matching the whole time — no loosening the match
logic to manufacture more hits.

**The result:** 36.71% → **53.24%** grams-computable (mass ingredients were
already at 100%; the real movement was volume, 34.5% → 56.7%, and count,
26.4% → 27.9%). A related pass the same session
(`7546d65`) hit an analogous measurement problem for *cuisine* tagging:
Food.com's own users only tag distinctive/exotic cuisines — nobody tags a
recipe "American" on a US recipe site — so eight canonical cuisines had
**zero** tag-mined examples no matter how much the tag vocabulary grew. The
fix was a dish-name gazetteer (`"coq au vin"` → French, `"carbonara"` →
Italian) matching *specific, unambiguous multi-word dish titles only* —
deliberately never bare adjectives, because a naive version of this exact
idea would tag "French Toast" as French cuisine. A mandatory adversarial
test suite pins known collision titles (French Toast, French Fries, Swiss
Cheese, Russian Dressing, American Cheese, Italian Dressing) to prove the
gazetteer never fires on them. Cuisine coverage moved 12.90% → 17.41% from
that one pass alone (current corpus-wide: 51.8%, see README's evals table).

**The takeaway.** A coverage metric is only as honest as what it's actually
measuring — "field populated" quietly became the proxy everyone trusted
until someone asked what the field was *for*. The discipline that made the
fix trustworthy wasn't the density table itself; it was refusing to fill
gaps with plausible-sounding guesses, logging what got skipped instead of
hiding it, and building an adversarial test for the exact failure mode
("this new capability looks smart but produces a wrong-but-confident
answer") a naive fix would have introduced.

---

## War story 2 — getting to "0/269" required not trusting the first "0/269"

**The setup.** MacroChef's release gate is an adversarial safety benchmark:
hundreds of hand-authored cases (hidden allergens, prompt injection,
morphology traps like "eggplant" vs. "egg") run against the deterministic
constraint engine, judged by a deliberately paranoid, recall-biased
substring matcher that's structurally barred from importing the code it
grades (an AST-walking test, `tests/test_safety_judge_import_ban.py`, fails
the build if that boundary is ever crossed). The release policy
(`CLAUDE.md`, human-decided) is strict: **the raw judge-flagged count and
the adjudicated-true count are always published together, and the judge is
never modified to close the gap between them.**

**The first real run wasn't clean, and pretending it was would have been
easy.** The first full run against a fully-committed `main` came back
**73/269 judge-flagged** — not zero. Getting from "73 flagged" to a
defensible "0 real violations" needed something more rigorous than eyeballing
each case.

**The near-miss.** The first pass at explaining those 73 flags was a
hand-written, per-case adjudication — read each flagged case, decide if it's
a real violation or a judge artifact, write up why. An independent review of
that first draft caught two real problems: its own case-by-case accounting
didn't actually sum to 73 (a bookkeeping error, not a safety one, but still
a sign the method wasn't rigorous enough to trust), and its central claim —
that most failures shared one specific judge-artifact mechanism — turned out
to be **wrong** for a majority of a sampled subset when checked against the
raw data. Most actually matched on a *different*, still-safe mechanism (a
stale recipe title lingering after a correct ingredient substitution) than
the one the draft had used to justify not re-deriving the rest by hand.

**The fix wasn't a better hand-audit — it was removing hands from the
loop.** Rather than patch the sampling methodology, it was replaced
entirely: `scripts/verify_benchmark_evidence.py` loads every served recipe's
*actual resolved ingredients* from the benchmark's own evidence bundle, and
every case's *real* tested constraint (the allergy/diet_type actually on the
profile — independent of the judge's own forbidden-term list, so it can't
inherit the judge's blind spots), then calls the **real, production**
`contains_allergen`/`violates_diet_type` functions directly against every
one of them. Exhaustive, not sampled — 98 judge-flagged cases (inherent +
precautionary combined), every one individually re-verified by the actual
safety code, not a human's read of a diff.

**Result: zero real violations across all 98**, on firmer footing than the
method it replaced — and confirmed the judge itself was unmodified since its
pre-registration commit, so the zero wasn't bought by quietly loosening what
counts as a match.

**The takeaway.** The dangerous version of this story is the one where the
first "0/269" ships because it was easier to trust a plausible-sounding
explanation than to build the tool that checks it exhaustively. The
adjudication discipline this project holds itself to — publish the raw
number next to the adjudicated one, never touch the judge to shrink the gap,
re-verify with the production code path itself rather than a written
argument about it — exists because the first draft of "we're clean" was
wrong in a way that looked right until someone checked.

---

*Current numbers (as of this writing, see README.md for the live figures):
391 total adversarial cases, 278 release-blocking (`inherent`); the last
fully certified judge run covers the prior 269-case set at 73/269 flagged,
0/269 adjudicated-true — a fresh run covering the current 278 needs a
human-approved paid judge pass, per the project's money gate.*
