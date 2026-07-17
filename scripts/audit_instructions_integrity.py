"""Instructions/ingredient integrity audit: corpus-wide DRY-RUN report for
the check in `app.services.corpus_import.instructions_ingredient_integrity`
(spec: `docs/instructions_integrity_spec.md`).

This script NEVER mutates the corpus -- it is read-only end to end. It:
  1. Loads ONLY `data/processed/imported_recipes.jsonl` (never any seed
     file -- see spec Sec. 5 / this repo's `test_instructions_ingredient_
     integrity.py::test_module_has_no_file_io_and_never_references_sample_
     recipes` and this script's own analogous "input scoping" test).
  2. Runs the check over every recipe, separating Tier A/B (quarantine-
     worthy) mismatches from Tier C (report-only) mismatches.
  3. Enforces the pre-registered guard bands (spec Sec. 3): exits nonzero on
     a ceiling breach (>12% of the corpus flagged, HALT) or a floor breach
     (<10 rows flagged, PROBABLE BUG). A verdict is written into the report
     either way.
  4. Emits a stratified sample-audit CANDIDATE list (n=40, seed 20260717,
     proportional by category with a minimum of 3 per non-empty category)
     and a 15-row UNflagged miss-spot-check candidate list (same seed), both
     with full per-case evidence, so a human/advisor adjudicates from a
     deterministic artifact rather than an ad hoc query.
  5. Writes both a human-readable `.md` report and a machine-readable
     `.json` evidence bundle to `data/evaluation/`, timestamped in UTC.

Usage: python scripts/audit_instructions_integrity.py
Exit code: 0 on a clean guard-band pass, 1 on HALT (ceiling breach) or
PROBABLE BUG (floor breach) -- same idiom as
`scripts/audit_title_ingredient_integrity.py`/`scripts/audit_diet_leaks.py`.
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.recipe import Recipe  # noqa: E402
from app.services.corpus_import.instructions_ingredient_integrity import (  # noqa: E402
    CATEGORIES,
    Mismatch,
    find_instructions_ingredient_mismatches,
    tier_ab_mismatches,
    tier_c_mismatches,
)

DEFAULT_CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "imported_recipes.jsonl"
REPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "evaluation"

# Pre-registered guard bands (spec Sec. 3) -- fixed BLIND before this
# script's first full-corpus run, per the spec's pre-registration rule.
# Never edit these to make a result "pass" after the fact.
EXPECTED_FRACTION_LOW = 0.01
EXPECTED_FRACTION_HIGH = 0.10
HARD_CEILING_FRACTION = 0.12
FLOOR_MIN_ROWS = 10

SAMPLE_AUDIT_N = 40
SAMPLE_AUDIT_MIN_PER_CATEGORY = 3
# Revision round 1 (2026-07-18 ruling on the 220709Z HALT): spec Sec. 3's
# on-breach rule requires a FRESH sample on re-run ("fresh sample with seed
# 20260718, increment per round") -- bumped from the first run's 20260717.
# The miss-spot-check seed is kept aligned to the same value per that rule.
SAMPLE_AUDIT_SEED = 20260718
MISS_SPOT_CHECK_N = 15
MISS_SPOT_CHECK_SEED = 20260718

# --- Revisions log (spec Sec. 0's pre-registration rule: any post-result
# vocabulary revision is documented here with before/after counts and a
# cited real example). Appended to, never edited retroactively, one block
# per revision round. Per-rule counts below are LEAVE-ONE-OUT ablations
# against the round's OWN final flagged-recipe count (i.e. "flagged count
# if this one rule were reverted, all other round-1 rules held active") --
# they therefore will NOT sum linearly to the baseline-to-current delta,
# because several rules can independently clear the same recipe (e.g. the
# "trassi" crustacean satisfier and the "NOTES:" commentary-prefix
# suppression both independently clear imp_f26d5c5093e25ac7 "Amazing Nasi
# Goreng"'s crustacean mention, so ablating either ONE alone still leaves
# the other active for that recipe). This is expected, not an arithmetic
# error -- restated explicitly so a future reader doesn't "fix" it.
ROUND_1_REVISIONS_MD = """\
**Round 1** (2026-07-18, advisor ruling on this round's own 220709Z HALT
report; docs/instructions_integrity_spec.md remains the frozen base spec).
Baseline (pre-round-1, 220709Z report): 1197/4045 = 29.59% flagged.
This round's result (all changes below active together): 1130/4045 = 27.94%
flagged -- still a HALT (> 12% ceiling); a HUMAN GATE per spec Sec. 3
("maximum two revision rounds") if round 2 does not clear the ceiling.

Per-rule leave-one-out ablation (flagged-recipe count with ONLY that one
rule reverted, all others held active, vs. this round's 1130 final count):

- Commentary-prefix step-wide suppression (new; "NOTES:"/"NB:"/"TIPS:"/
  "VARIATIONS:"/"COLUMN:"/"GARNISHING NOTE:"/"SERVING SUGGESTIONS:"/
  "SUGGESTED ACCOMPANIMENTS:"): 1138 without it -> 1130 with it (clears 8
  recipes' worth of quarantine-worthy mismatches).
- Optional-variation/cross-reference step-wide suppression (new; "as
  desired"/"if desired"/"if you like"/`\\boptional(?:s|ly)?\\b`/"same
  quantities as"/"menu featuring"): 1147 without it -> 1130 with it
  (clears 17).
- `\\bsubstitutes?\\b` added to the generic whole-step negation phrases:
  1135 without it -> 1130 with it (clears 5). Deliberately excludes
  "substituted" (past tense) -- see the module's inline citation.
- "soymilk" added as a satisfier-only extra for BOTH `soy` and `dairy`:
  1134 without it -> 1130 with it (clears 4).
- "roast" (`\\broasts?\\b`, not "roasted") added as a satisfier-only extra
  for `meat`: 1132 without it -> 1130 with it (clears 2).
- "trassi" added as a satisfier-only extra for `crustacean`: 1130 without
  it -> 1130 with it (clears 0 marginally in this leave-one-out ordering --
  its one cited case, imp_f26d5c5093e25ac7, is already independently
  cleared by the commentary-prefix rule above for the same step; kept as
  defense-in-depth per the ruling for any future row that mentions trassi
  outside a suppressed step).
- Tier B composite in-recipe-stock satisfier (mollusk-row arm OR
  water-row+animal-row arm): 1161 without it -> 1130 with it (clears 31 --
  this round's single largest contributor). Both planted Tier B faults
  (imp_ece8c7dd17b95468 "Dirty Rice", imp_acd7c3ec0ed35a51 "Rice, Apple and
  Raisin Dressing") were re-verified to still flag after this change.
- "sparerib"/"spare rib" added to MEAT_FLESH_TERMS (triggers AND
  satisfiers): 1128 without it -> 1130 with it -- this is the one rule in
  this round that INCREASES the flagged count (catches 2 real corpus
  misses net), rather than suppressing false positives.

**Discovered conflict, flagged rather than silently patched:** the ruling's
own cited example for the sparerib addition, imp_6f3463afcc2f5d51 "Pork
Spareribs in Tangy Sauce," does NOT end up in this round's quarantine-worthy
list despite "sparerib" now correctly firing as a trigger. Its own
"Worcestershire sauce" ingredient row already satisfies the `meat` category
via the PRE-EXISTING (spec Sec. 2, not part of this ruling) satisfier
design -- `meat`'s satisfiers include `FISH_TERMS`, which contains
"worcestershire" (cited there as a fish-allergen condiment), on the
documented rationale that "a row already containing ANY animal-flesh OR
fish/crustacean/mollusk term is already non-vegetarian at serve time." This
executor pass did NOT alter `meat`'s satisfier composition (out of this
ruling's literal scope, and a corpus-wide architectural call); the
sparerib/spare-rib addition is still net positive (+2 other real corpus
misses caught) despite not fixing its own cited example. See
`tests/test_instructions_ingredient_integrity.py::
test_imp_6f3463afcc2f5d51_sparerib_trigger_added_but_worcestershire_row_still_satisfies_meat`
for the pinned regression and a companion synthetic test isolating the
trigger's effect without the conflict.

**Rejected candidates (spec ruling item 7 -- recorded, not implemented):**
- `except` as a negation phrase: corpus evidence (imp_2433f1f7486a57dc,
  imp_19ce1a09db625d96, imp_180066ee5652529a) shows "except" marks
  sequencing/exclusion-from-a-later-step, not an absence claim about the
  recipe's own content.
- "also a great addition" as a suppression phrase: imp_c846d8efd9895c8d's
  own step contains a genuine "Add cranberries and nuts" alongside it, so
  whole-step suppression there would hide a real mismatch.
- An addition-verb requirement for Tier B stock satisfaction: would rewrite
  the frozen Tier B semantics and misses "simmer in broth"-shaped
  in-recipe-stock forms that have no explicit addition verb.
"""


@dataclass
class AuditResult:
    corpus_size: int
    # ALL tiers, one Mismatch per (recipe, category).
    mismatches: list[Mismatch] = field(default_factory=list)
    # recipe_id -> full Recipe, for evidence rendering (ingredient names,
    # title) without re-reading the corpus file a second time.
    recipes_by_id: dict[str, Recipe] = field(default_factory=dict)

    def quarantine_mismatches(self) -> list[Mismatch]:
        return tier_ab_mismatches(self.mismatches)

    def report_only_mismatches(self) -> list[Mismatch]:
        return tier_c_mismatches(self.mismatches)

    def flagged_recipe_ids(self) -> set[str]:
        return {m.recipe_id for m in self.quarantine_mismatches()}

    def by_category(self, mismatches: list[Mismatch]) -> dict[str, list[Mismatch]]:
        grouped: dict[str, list[Mismatch]] = {}
        for mismatch in mismatches:
            grouped.setdefault(mismatch.category, []).append(mismatch)
        return grouped


def _load_corpus(path: Path) -> list[Recipe]:
    recipes = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            recipes.append(Recipe.model_validate(json.loads(line)))
    return recipes


def audit(corpus: list[Recipe]) -> AuditResult:
    result = AuditResult(corpus_size=len(corpus))
    for recipe in corpus:
        result.recipes_by_id[recipe.recipe_id] = recipe
        result.mismatches.extend(find_instructions_ingredient_mismatches(recipe))
    return result


# --- Guard bands (spec Sec. 3) ----------------------------------------------


@dataclass
class GuardVerdict:
    verdict: str  # "OK" | "HALT" | "PROBABLE_BUG"
    flagged_count: int
    corpus_size: int
    fraction: float
    exit_code: int
    message: str


def evaluate_guard_bands(result: AuditResult) -> GuardVerdict:
    flagged_count = len(result.flagged_recipe_ids())
    corpus_size = result.corpus_size
    fraction = flagged_count / corpus_size if corpus_size else 0.0

    if flagged_count < FLOOR_MIN_ROWS:
        return GuardVerdict(
            verdict="PROBABLE_BUG",
            flagged_count=flagged_count,
            corpus_size=corpus_size,
            fraction=fraction,
            exit_code=1,
            message=(
                f"Floor sanity breach: only {flagged_count} row(s) flagged (< {FLOOR_MIN_ROWS}). "
                "The three still-in-corpus planted faults alone guarantee >=3, and the review's "
                "6-of-9 sampled corruption rate makes a near-zero result implausible -- this is "
                "almost certainly a check/vocabulary bug, not a clean corpus. Investigate before "
                "trusting this run."
            ),
        )

    if fraction > HARD_CEILING_FRACTION:
        return GuardVerdict(
            verdict="HALT",
            flagged_count=flagged_count,
            corpus_size=corpus_size,
            fraction=fraction,
            exit_code=1,
            message=(
                f"Hard ceiling breach: {flagged_count}/{corpus_size} = {fraction:.2%} flagged "
                f"(> {HARD_CEILING_FRACTION:.0%}). HALT per spec Sec. 3: analyze the false-positive "
                "classes in this report, add suppressions (each cited with a real example), and "
                "re-run. Maximum two revision rounds; if still above the ceiling, this is a HUMAN "
                "GATE -- the corpus is majority-defective for safety purposes and replacing/"
                "re-importing it is a product decision, not an automated purge."
            ),
        )

    band_note = (
        "within the expected 1%-10% band"
        if EXPECTED_FRACTION_LOW <= fraction <= EXPECTED_FRACTION_HIGH
        else "above the expected 1%-10% band but at/below the 12% hard ceiling -- not a HALT, "
        "but worth noting in the sample audit"
    )
    return GuardVerdict(
        verdict="OK",
        flagged_count=flagged_count,
        corpus_size=corpus_size,
        fraction=fraction,
        exit_code=0,
        message=f"Guard bands passed: {flagged_count}/{corpus_size} = {fraction:.2%} flagged, {band_note}.",
    )


# --- Stratified sample-audit candidate list (spec Sec. 3) -------------------


def _largest_remainder_allocation(weights: dict[str, int], total_slots: int) -> dict[str, int]:
    """Deterministic proportional integer allocation of `total_slots` across
    categories weighted by `weights`, via the largest-remainder method (each
    category's exact share is floored, then the leftover slots go to the
    categories with the largest fractional remainder, ties broken
    alphabetically for full determinism)."""
    total_weight = sum(weights.values())
    if total_weight == 0 or total_slots <= 0:
        return {category: 0 for category in weights}

    raw = {category: total_slots * (weight / total_weight) for category, weight in weights.items()}
    floors = {category: int(raw[category]) for category in raw}
    allocated = sum(floors.values())
    leftover = total_slots - allocated

    remainder_order = sorted(raw.keys(), key=lambda category: (-(raw[category] - floors[category]), category))
    for category in remainder_order[:leftover]:
        floors[category] += 1
    return floors


def stratified_sample_cases(
    quarantine_mismatches: list[Mismatch],
    *,
    n: int = SAMPLE_AUDIT_N,
    min_per_category: int = SAMPLE_AUDIT_MIN_PER_CATEGORY,
    seed: int = SAMPLE_AUDIT_SEED,
) -> list[Mismatch]:
    """Stratified random sample of (recipe, category) mismatch CASES --
    every Tier A/B `Mismatch` is one case; a recipe flagged under two
    categories contributes two independently-sampleable cases, since the
    audit's purpose is reviewing enough real evidence PER CATEGORY, not
    enumerating distinct recipes (spec Sec. 3: "proportional by category,
    min 3 per non-empty category"). Deterministic: same input + same seed
    always produces the same sample.

    Algorithm: (1) if the total available cases are <= n, return all of
    them (spec's "n=40, or all if fewer"). (2) Otherwise, guarantee
    min(min_per_category, available) cases per non-empty category, then
    fill the remaining slots proportionally to each category's remaining
    pool size via the largest-remainder method, so bigger categories still
    get proportionally more of the sample.
    """
    rng = random.Random(seed)
    by_category: dict[str, list[Mismatch]] = {}
    for mismatch in quarantine_mismatches:
        by_category.setdefault(mismatch.category, []).append(mismatch)

    shuffled: dict[str, list[Mismatch]] = {}
    for category, cases in by_category.items():
        pool = list(cases)
        rng.shuffle(pool)
        shuffled[category] = pool

    total_available = sum(len(pool) for pool in shuffled.values())
    categories = sorted(shuffled)

    if total_available <= n:
        return [case for category in categories for case in shuffled[category]]

    quotas = {category: min(min_per_category, len(shuffled[category])) for category in categories}
    selected: list[Mismatch] = []
    taken: dict[str, int] = {}
    for category in categories:
        take = quotas[category]
        selected.extend(shuffled[category][:take])
        taken[category] = take

    remaining_slots = n - len(selected)
    if remaining_slots > 0:
        remaining_pools = {category: shuffled[category][taken[category]:] for category in categories}
        remaining_sizes = {category: len(pool) for category, pool in remaining_pools.items() if pool}
        if remaining_sizes:
            allocation = _largest_remainder_allocation(remaining_sizes, remaining_slots)
            for category, take in allocation.items():
                pool = remaining_pools[category]
                selected.extend(pool[: min(take, len(pool))])

    return selected[:n]


def miss_spot_check_sample(
    unflagged_recipes: list[Recipe], *, n: int = MISS_SPOT_CHECK_N, seed: int = MISS_SPOT_CHECK_SEED
) -> list[Recipe]:
    rng = random.Random(seed)
    pool = list(unflagged_recipes)
    rng.shuffle(pool)
    return pool[:n]


# --- Report rendering --------------------------------------------------


def _mismatch_evidence_dict(result: AuditResult, mismatch: Mismatch) -> dict:
    recipe = result.recipes_by_id.get(mismatch.recipe_id)
    return {
        "recipe_id": mismatch.recipe_id,
        "title": mismatch.title,
        "tier": mismatch.tier,
        "category": mismatch.category,
        "matched_terms": mismatch.matched_terms,
        "evidence": mismatch.evidence,
        "ingredient_names": [item.name for item in recipe.ingredients] if recipe else [],
        "allergens": recipe.allergens if recipe else [],
    }


def render_report(
    result: AuditResult,
    guard_verdict: GuardVerdict,
    sample_cases: list[Mismatch],
    miss_recipes: list[Recipe],
    *,
    timestamp: str,
) -> str:
    quarantine = result.quarantine_mismatches()
    report_only = result.report_only_mismatches()
    by_category_ab = result.by_category(quarantine)
    by_category_c = result.by_category(report_only)
    by_tier: dict[str, int] = {}
    for mismatch in quarantine:
        by_tier[mismatch.tier] = by_tier.get(mismatch.tier, 0) + 1

    lines = [
        f"# Instructions/ingredient integrity audit -- {timestamp}",
        "",
        "Dry run only -- this report never mutated `data/processed/imported_recipes.jsonl` "
        "or any quarantine sidecar. See `docs/instructions_integrity_spec.md` for the full "
        "rule set and guard-band pre-registration.",
        "",
        "## Guard-band verdict",
        "",
        f"**{guard_verdict.verdict}**: {guard_verdict.message}",
        "",
        f"- Corpus size: {result.corpus_size}",
        f"- Flagged (Tier A+B, quarantine-worthy): {guard_verdict.flagged_count} "
        f"({guard_verdict.fraction:.2%})",
        f"- Tier A: {by_tier.get('A', 0)}",
        f"- Tier B: {by_tier.get('B', 0)}",
        f"- Tier C (report-only, never quarantines): {len({m.recipe_id for m in report_only})} "
        f"recipes, {len(report_only)} mismatch pairs",
        "",
        "## Per-category counts (Tier A/B, quarantine-worthy)",
        "",
    ]
    for category, mismatches in sorted(by_category_ab.items(), key=lambda kv: -len(kv[1])):
        spec = CATEGORIES[category]
        lines.append(f"- `{category}` (tier {spec['tier']}): {len(mismatches)}")
    if not by_category_ab:
        lines.append("(none)")
    lines.append("")

    lines.append("## Per-category counts (Tier C, report-only)")
    lines.append("")
    for category, mismatches in sorted(by_category_c.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- `{category}`: {len(mismatches)}")
    if not by_category_c:
        lines.append("(none)")
    lines.append("")

    lines.append("## Out-of-scope boundary (spec Sec. 1)")
    lines.append("")
    lines.append(
        "Non-safety-vocabulary omissions (e.g. the imp_f9cc221553155bfc 'orange juice' class) "
        "are explicitly out of scope: hidden orange juice cannot produce an engine-visible "
        "allergy/diet violation. Title-side bare meat/fish word checking remains unchanged "
        "(proven unsafe to do deterministically, per the existing title module and "
        "`docs/BACKLOG.md`)."
    )
    lines.append("")

    lines.append(f"## Sample-audit candidate list (n={len(sample_cases)}, seed {SAMPLE_AUDIT_SEED})")
    lines.append("")
    lines.append(
        "Stratified by category (largest-remainder proportional allocation, min "
        f"{SAMPLE_AUDIT_MIN_PER_CATEGORY} per non-empty category), population unit = one "
        "(recipe, category) Tier A/B mismatch case. For the orchestrator/advisor to write "
        "per-case CORRECT_QUARANTINE / FALSE_POSITIVE adjudication against (acceptance: "
        "<=2/40 false positives, i.e. >=95% precision). Full evidence in the sidecar JSON."
    )
    lines.append("")
    for case in sample_cases:
        recipe = result.recipes_by_id.get(case.recipe_id)
        ingredient_names = [item.name for item in recipe.ingredients] if recipe else []
        lines.append(f"- `{case.recipe_id}` {case.title!r} -- category `{case.category}` (tier {case.tier})")
        lines.append(f"  - matched terms: {case.matched_terms}")
        lines.append(f"  - ingredient names: {ingredient_names}")
        for entry in case.evidence:
            lines.append(f"  - quoted step ({entry['term']!r}): {entry['quoted_step']!r}")
    if not sample_cases:
        lines.append("(no quarantine-worthy mismatches to sample)")
    lines.append("")

    lines.append(f"## Miss spot-check candidate list (n={len(miss_recipes)}, seed {MISS_SPOT_CHECK_SEED})")
    lines.append("")
    lines.append(
        "15 random UNflagged rows for the orchestrator to read for any Tier A/B-class omission "
        "the check should have caught (acceptance: 0 misses; a miss is a spec bug, fix and "
        "re-run -- not an acceptance judgment call)."
    )
    lines.append("")
    for recipe in miss_recipes:
        lines.append(f"- `{recipe.recipe_id}` {recipe.title!r}")
        lines.append(f"  - ingredient names: {[item.name for item in recipe.ingredients]}")
        lines.append(f"  - instructions: {recipe.instructions}")
    if not miss_recipes:
        lines.append("(no unflagged rows available)")
    lines.append("")

    lines.append("## Revisions")
    lines.append("")
    lines.append(ROUND_1_REVISIONS_MD)
    lines.append("")

    return "\n".join(lines)


def render_json(
    result: AuditResult,
    guard_verdict: GuardVerdict,
    sample_cases: list[Mismatch],
    miss_recipes: list[Recipe],
    *,
    timestamp: str,
) -> dict:
    quarantine = result.quarantine_mismatches()
    report_only = result.report_only_mismatches()
    return {
        "timestamp_utc": timestamp,
        "corpus_size": result.corpus_size,
        "guard_verdict": {
            "verdict": guard_verdict.verdict,
            "flagged_count": guard_verdict.flagged_count,
            "corpus_size": guard_verdict.corpus_size,
            "fraction": guard_verdict.fraction,
            "exit_code": guard_verdict.exit_code,
            "message": guard_verdict.message,
        },
        "quarantine_mismatches": [_mismatch_evidence_dict(result, m) for m in quarantine],
        "report_only_mismatches": [_mismatch_evidence_dict(result, m) for m in report_only],
        "sample_audit_candidates": {
            "n": SAMPLE_AUDIT_N,
            "seed": SAMPLE_AUDIT_SEED,
            "min_per_category": SAMPLE_AUDIT_MIN_PER_CATEGORY,
            "cases": [_mismatch_evidence_dict(result, m) for m in sample_cases],
        },
        "miss_spot_check_candidates": {
            "n": MISS_SPOT_CHECK_N,
            "seed": MISS_SPOT_CHECK_SEED,
            "recipes": [
                {
                    "recipe_id": recipe.recipe_id,
                    "title": recipe.title,
                    "ingredient_names": [item.name for item in recipe.ingredients],
                    "instructions": recipe.instructions,
                    "allergens": recipe.allergens,
                }
                for recipe in miss_recipes
            ],
        },
    }


def main() -> int:
    corpus_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CORPUS_PATH
    corpus = _load_corpus(corpus_path)

    result = audit(corpus)
    guard_verdict = evaluate_guard_bands(result)

    sample_cases = stratified_sample_cases(result.quarantine_mismatches())
    flagged_ids = result.flagged_recipe_ids()
    unflagged_recipes = [recipe for recipe in corpus if recipe.recipe_id not in flagged_ids]
    miss_recipes = miss_spot_check_sample(unflagged_recipes)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_md = render_report(result, guard_verdict, sample_cases, miss_recipes, timestamp=timestamp)
    report_json = render_json(result, guard_verdict, sample_cases, miss_recipes, timestamp=timestamp)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORT_DIR / f"instructions_integrity_report_{timestamp}.md"
    json_path = REPORT_DIR / f"instructions_integrity_report_{timestamp}.json"
    md_path.write_text(report_md, encoding="utf-8")
    json_path.write_text(json.dumps(report_json, indent=2, ensure_ascii=False), encoding="utf-8")

    print(report_md)
    print(f"\nWrote report to {md_path}")
    print(f"Wrote evidence JSON to {json_path}")

    return guard_verdict.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
