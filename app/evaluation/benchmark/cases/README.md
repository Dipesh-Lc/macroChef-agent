# Benchmark case files

One JSONL file per `category` (see `app/evaluation/benchmark/case_schema.py`
for the full schema and field-level rationale). This directory currently
holds **scaffold examples only** -- two illustrative, obviously-placeholder
cases per category, each marked `"notes": "SCAFFOLD EXAMPLE - replace during
authoring"`. Authoring tasks delete and replace these with real adversarial
cases; do not treat the content of these examples as coverage.

## Blind-authoring rule

Authoring this case set is deliberately split from building the schema/
validator (this scaffold) and from the constraint-engine implementation.
**Whoever authors cases for these files must not read `app/services/` or
`app/utils/`.** Ground truth (`forbidden_terms`) must come from an external
authority the case can cite, never be reverse-engineered from
`app.services.constraint_engine` or `app.utils.ingredient_normalizer`. A case
whose "correct answer" was derived by reading the matching code under test
is not evidence the code is correct -- it's a tautology.

## Citation requirement

Every case except `safe_control` MUST carry a `source_citation` pointing at
something outside this repository: an allergen-derivative reference (e.g.
FARE's hidden-name lists), a diet-definition standard (e.g. The Vegan
Society's definition of veganism), an allergen-labeling regulation (e.g. FDA
FALCPA), or an equivalent external authority for the claim the case makes.

`scripts/validate_benchmark_cases.py` enforces a contamination heuristic:
any case whose `source_citation.url` is empty, or whose citation points back
at this repository instead of an external source, fails validation. If you
can't cite an external authority for a case, the case isn't ready to ship --
don't invent one.

## Two renderings, always

Every case must express its adversarial content in **both**:

- `conversation` -- for the raw-LLM comparison arm(s).
- `structured_rendering` -- for MacroChef's real input surfaces
  (`UserProfile.allergies` / `diet_type` / `macro_targets` for structured
  intake; `typed_ingredients` / `inventory_text` for the free-text surfaces
  the LLM inventory-extraction step actually parses). Never smuggle
  adversarial content into `allergies` itself -- MacroChef has no
  conversational allergy intake to attack there.

## Quota gate (`scripts/validate_benchmark_cases.py`)

- Total cases across all files: 300-500.
- `safe_control` must be 15%-20% of the total (this is what makes
  "0 violations by refusing everything" impossible to hide as a pass).
- Every category must be non-empty.
- No duplicate `case_id` values across any file.
