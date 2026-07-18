---
license: cc-by-4.0
task_categories:
- text-classification
language:
- en
size_categories:
- n<1K
pretty_name: MacroChef Adversarial Allergy & Diet Safety Benchmark
tags:
- food-safety
- allergy
- adversarial-benchmark
- llm-evaluation
- diet
- safety
configs:
- config_name: default
  data_files:
  - split: test
    path: data/benchmark_cases.jsonl
- config_name: hidden_allergen
  data_files:
  - split: test
    path: data/hidden_allergen.jsonl
- config_name: derivative_name
  data_files:
  - split: test
    path: data/derivative_name.jsonl
- config_name: stated_then_contradicted
  data_files:
  - split: test
    path: data/stated_then_contradicted.jsonl
- config_name: prompt_injection
  data_files:
  - split: test
    path: data/prompt_injection.jsonl
- config_name: diet_trap
  data_files:
  - split: test
    path: data/diet_trap.jsonl
- config_name: safe_control
  data_files:
  - split: test
    path: data/safe_control.jsonl
- config_name: morphology
  data_files:
  - split: test
    path: data/morphology.jsonl
- config_name: multi_constraint
  data_files:
  - split: test
    path: data/multi_constraint.jsonl
- config_name: macro_trap
  data_files:
  - split: test
    path: data/macro_trap.jsonl
---

# MacroChef Adversarial Allergy & Diet Safety Benchmark

A frozen, blind-authored set of **371 adversarial test cases** for evaluating
whether a meal-planning / recipe-recommendation system correctly enforces
stated food allergies and dietary constraints. Built for and used by
[MacroChef](https://github.com/Dipesh-Lc/macroChef-agent), a LangGraph-based
meal-planning agent whose defining safety principle is:

> The LLM never enforces allergies or computes nutrition. Deterministic
> code does. The benchmark exists to check that principle actually holds.

Every case pairs a raw conversational transcript (for testing a bare LLM)
with a structured rendering (for testing a system with real, non-chat
allergy/diet intake fields) asserting the same adversarial content in both
surfaces. A deterministic, independently-implemented judge — never the
constraint-engine code under test — scores whether a served recommendation's
title or ingredient list contains a forbidden term.

## Why this exists

Naming a food is not the same as knowing what it contains. "Nougat" doesn't
say "milk." "Malted milk" in an ingredient line doesn't automatically mean a
recipe is unsafe for a gluten allergy (the malt in question may be barley
malt syrup, or may just be flavoring — case-dependent). A system that only
pattern-matches allergen *names* against recipe *titles* will both miss real
hidden allergens and over-block safe foods whose titles happen to contain a
scary-looking substring. This benchmark is built to catch both failure
modes, adversarially, using only external authorities (never the
implementation under test) as ground truth.

## The two-number honest-reporting methodology

Every case is judged by two independent things: (1) a deterministic,
narrowly-scoped **judge** (substring + token-subset matching against served
titles/ingredients — biased toward flagging, never toward missing, so its
false positives are a known, accepted cost) and (2) a **human/advisor
adjudication** of every judge flag, with a written per-case verdict
(`TRUE_VIOLATION` or `JUDGE_FP`), citable evidence, and ambiguity defaulting
to `TRUE_VIOLATION`. Both numbers are always published together — the raw
judge-flagged count is never dropped once a human adjudication brings it
down, and the judge itself is never modified to close the gap.

**Current numbers** (measured against MacroChef on commit `457c3d7`; see
`data/evaluation/adjudication_20260718T123735Z.md` in the source repository
for the full per-case adjudication):

| Bucket | n | judge-flagged | adjudicated true |
| --- | ---: | ---: | ---: |
| `inherent` (release-blocking) | 259 | 17 | **0** |
| `precautionary` (non-blocking) | 46 | 10 | 6 |
| `safe_control` over-blocking | 60 | 0 | 0 |

Read this as: **"judge-flagged 17/259 inherent; adjudicated true 0/259"**
(plus precautionary 10/46 flagged / 6/46 true, and 0/60 safe-control
over-blocks). This pairing is mandatory wherever a claim about this
benchmark's results is made — see the "Two-number methodology" rule below.

**Two-number methodology rule, for anyone scoring their own system against
this benchmark:**
- The judge is a high-recall, low-precision automated matcher. It is
  designed to over-flag rather than miss a real violation.
- A judge flag is a starting point for a human/expert adjudication, not a
  final verdict. Report both the raw judge-flagged count and the
  adjudicated-true count, always paired, forever — a judge false positive
  that gets adjudicated away does not disappear from the raw number.
- Never modify the judge (or its equivalent in your own harness) to make a
  score look better after seeing the result. If the judge's matching logic
  needs to change, that is a separate, disclosed methodology change, not a
  quiet fix to close a gap.
- `inherent` violations are the release-blocking safety number — the named
  food carries the allergen **by definition** (e.g. mayonnaise contains
  egg). `precautionary` violations are non-blocking — an external authority
  (typically FARE) lists the allergen as a *possible*, not definitional,
  source (e.g. "gravy may contain peanut"). Collapsing the two into one
  score makes the release-blocking rate uninterpretable in both directions:
  it either forces useless over-blocking (refusing gravy for every peanut
  allergy) or lets a real definitional miss hide inside a noisier bucket.

## What the benchmark is (structure)

371 cases, blind-authored (the case authors did not read MacroChef's
`app/services/` or `app/utils/` matching code — ground truth comes only from
external authorities such as FARE, FDA FALCPA, and standards-of-identity
regulations, never from reverse-engineering the system under test), pinned
(frozen at a fixed count/content — no case is edited after freeze without a
recorded, reviewed change), across **9 categories**: 8 adversarial-intent
categories plus one non-adversarial `safe_control` baseline (so that a
system which refuses everything cannot masquerade as "0% violations" — see
the over-blocking column above).

| category | count | what it tests |
| --- | ---: | --- |
| `hidden_allergen` | 58 | named foods that hide a common allergen under a different name (e.g. nougat contains milk-derived ingredients) |
| `derivative_name` | 59 | allergen derivatives/synonyms (e.g. casein, whey, isinglass) that a naive name-match would miss |
| `stated_then_contradicted` | 50 | a user states a constraint, then a later turn/field appears to contradict or soften it — correct behavior is to keep enforcing the original constraint |
| `prompt_injection` | 14 | text designed to get an LLM-touching surface to ignore or override a stated allergy/diet constraint (deduplicated to 14 distinct payloads; see `data/README.md`) |
| `diet_trap` | 40 | diet-definition edge cases (vegan/vegetarian/gluten-free/dairy-free) where a food's dietary status is easy to get wrong |
| `safe_control` | 60 | genuinely safe requests — correct behavior is to serve a recommendation, not refuse |
| `morphology` | 40 | lookalike names that are NOT the allergen (e.g. a name that superficially resembles an allergen term but isn't derived from it) — tests over-blocking |
| `multi_constraint` | 25 | two or more simultaneous constraints (allergy + diet) that must all hold at once |
| `macro_trap` | 25 | macro/nutrition-target framing combined with a hidden allergy or diet constraint |
| **total** | **371** | |

**Partition breakdown** (by `claim_strength`, computed over
`expected_safe: false` cases, plus the `expected_safe: true` cases which
carry no claim):

| partition | n | meaning |
| --- | ---: | --- |
| `inherent` | 259 | the named food carries the forbidden term **by definition** — release-blocking |
| `precautionary` | 46 | an external authority lists the forbidden term as a **possible**, non-definitional source — non-blocking |
| non-violation (`expected_safe: true`) | 66 | 60 `safe_control` cases + 6 cases in other categories (e.g. `morphology`) that themselves assert zero forbidden terms |

## Fields schema

Each row is one JSON object (see `app/evaluation/benchmark/case_schema.py`
in the source repository for the full Pydantic definition and rationale
comments):

| field | type | description |
| --- | --- | --- |
| `case_id` | `str` | stable id, prefixed by category (e.g. `hidden_001`, `diet_014`) |
| `category` | `str` | one of the 9 categories in the table above |
| `conversation` | `list[{role, content}]` | raw transcript rendering, for a bare-LLM comparison arm |
| `structured_rendering` | `object` | MacroChef-native rendering: `allergies` (`list[str]`), `diet_type` (`str \| null`), `typed_ingredients` (`list[str]`), `inventory_text` (`str \| null`), `macro_targets` (`object \| null`) |
| `forbidden_terms` | `list[str]` | externally-sourced terms that must never appear in a served recommendation's title/ingredients; empty iff `expected_safe` is `true` |
| `expected_safe` | `bool` | `true` iff there is no forbidden-term claim to enforce (all `safe_control` cases, plus any case that itself asserts zero forbidden terms) |
| `surfaces` | `list[str]` | which system surface(s) this case exercises: `recommendation_graph` and/or `discovery` |
| `source_citation` | `{source, url, quote} \| null` | the external authority backing `forbidden_terms`; required for every non-`safe_control` case |
| `claim_strength` | `"inherent" \| "precautionary" \| null` | required iff `expected_safe` is `false`; classifies whether the forbidden-term claim is definitional (`inherent`) or possible/precautionary; `null` iff `expected_safe` is `true` |
| `pinned_recipe_ids` | `list[str]` | optional — pins specific corpus recipe ids for cases that need a fixed ingredient list rather than whatever retrieval happens to surface |
| `notes` | `str \| null` | optional free-text authoring note |

`scripts/validate_benchmark_cases.py` in the source repository enforces
this schema plus quota rules (safe_control 15-20% of total, no duplicate
`case_id`, no duplicate `(conversation, structured_rendering)` payload, and
a closed allergy-label vocabulary) — run it against this dataset's
`data/*.jsonl` files to re-verify well-formedness independently.

## Loading

This dataset is plain JSONL with no nested-structure issues that require a
custom loading script, so it uses the Hugging Face `datasets` **no-script**
format. Every case row already carries its own `category` field, so a
single combined file (`data/benchmark_cases.jsonl`, 371 rows) sits alongside
the original 9 per-category files (byte-identical to the source
repository's `app/evaluation/benchmark/cases/*.jsonl`) for convenience.

```python
from datasets import load_dataset

# All 371 cases combined
ds = load_dataset("<your-namespace>/macrochef-adversarial-safety-benchmark")

# One category only, via the config name (matches the original filenames)
hidden_allergen = load_dataset(
    "<your-namespace>/macrochef-adversarial-safety-benchmark",
    "hidden_allergen",
)
```

Or, working from a local clone of this dataset repo / the `hf_dataset/`
directory directly:

```python
from datasets import load_dataset

ds = load_dataset("json", data_files="data/benchmark_cases.jsonl", split="train")
```

## Running the harness against your own system

The evaluation harness (`scripts/run_safety_benchmark.py`,
`app/evaluation/benchmark/safety_judge.py`, `app/evaluation/benchmark/
loader.py`, `app/evaluation/benchmark/case_schema.py`) lives in the
[MacroChef source repository](https://github.com/Dipesh-Lc/macroChef-agent)
under MIT license — it is **not duplicated in this dataset repo**, since the
case set (data) and the harness (code) are licensed separately (see
`LICENSE` below). To run it:

```bash
git clone https://github.com/Dipesh-Lc/macroChef-agent.git
cd macroChef-agent
pip install -r requirements.txt
python scripts/run_safety_benchmark.py
```

By default this runs the **mock provider** — free, no external API calls,
works from a fresh clone with no keys configured (`MODEL_PROVIDER=mock` is
force-set at the top of the script regardless of any ambient `.env`). It
runs the frozen 371-case set through MacroChef's real
`recommendation_graph` / `discovery` surfaces, judges every served
recommendation against each case's `forbidden_terms`, and writes a dated
markdown report plus a machine-readable per-flagged-case evidence bundle to
`data/evaluation/`. A real-provider run (which spends money on LLM calls for
explanation text — retrieval/embeddings stay local either way) requires
`--provider real` **and** `--confirm-real-provider-spend`; see
`python scripts/run_safety_benchmark.py --cost-estimate` for an
order-of-magnitude cost sheet before ever passing that flag.

To score a **different** system against this case set: load
`data/benchmark_cases.jsonl` (or the per-category files), feed each case's
`structured_rendering` (or `conversation`, for a bare-LLM comparison arm)
into your system, collect whatever gets served, and check the served
titles/ingredients for any of that case's `forbidden_terms` — using a judge
at least as recall-biased as the one described above, and reporting both
the raw judge-flagged count and an adjudicated-true count, always paired.

## Citation

If you use this benchmark, please cite the MacroChef project:

```bibtex
@misc{macrochef_adversarial_safety_benchmark,
  title = {MacroChef Adversarial Allergy \& Diet Safety Benchmark},
  author = {MacroChef project},
  year = {2026},
  howpublished = {\url{https://github.com/Dipesh-Lc/macroChef-agent}},
  note = {371 blind-authored adversarial cases for evaluating allergy/diet
          constraint enforcement in meal-planning systems. Dataset license:
          CC BY 4.0. Harness code license: MIT (in the source repository).}
}
```

## Disclaimer

This is a hobby project's evaluation artifact, not medical advice and not a
certification of any system's safety. A judge-flagged or adjudicated-true
result on this benchmark reflects behavior observed against a specific,
pinned corpus and commit at a point in time — it does not guarantee behavior
against other corpora, other commits, or real-world usage. Anyone with a
food allergy using any system evaluated against this benchmark (including
MacroChef itself) should independently verify ingredients before eating
anything; do not rely on any automated system, or any score on this
benchmark, as a substitute for that.
