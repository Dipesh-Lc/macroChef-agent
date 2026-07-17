"""Tests for scripts/run_safety_benchmark.py: the money gate, the
statistics helpers (Wilson interval, worst-run bucket scoring), UserProfile
construction edge cases, report rendering, the per-case evidence bundle
(match-rule classification + JSON artifact), and the mutation self-check
that proves this harness actually catches a planted safety fault.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.run_safety_benchmark as runner  # noqa: E402
from app.evaluation.benchmark.case_schema import BenchmarkCase  # noqa: E402
from app.evaluation.benchmark.loader import load_all_cases  # noqa: E402
from app.evaluation.benchmark.safety_judge import TermMatch  # noqa: E402
from app.schemas.recommendation import ValidationResult  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Money gate
# ---------------------------------------------------------------------------


def test_default_cli_invocation_uses_mock_provider() -> None:
    parser = runner.build_arg_parser()
    args = parser.parse_args([])
    assert args.provider == "mock"
    assert args.confirm_real_provider_spend is False


def test_real_provider_without_confirm_flag_refuses_and_prints_cost_estimate(capsys) -> None:
    exit_code = runner.main(["--provider", "real"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "REFUSING" in captured.out
    assert "cost estimate" in captured.out.lower() or "Cost estimate" in captured.out
    # Confirms no benchmark run was attempted -- the refusal happens before
    # any case is loaded/executed.
    assert "Running run 1" not in captured.out


def test_cost_estimate_flag_exits_zero_without_running_anything(capsys) -> None:
    exit_code = runner.main(["--cost-estimate"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "cost estimate" in captured.out.lower()
    assert "Running run 1" not in captured.out


def test_importing_runner_module_forces_mock_env_even_with_real_key_present() -> None:
    """Simulates this exact repo's live risk (a real GEMINI_API_KEY set in
    the ambient shell environment, MODEL_PROVIDER=gemini in .env) in a
    clean subprocess, and asserts that merely IMPORTING
    scripts.run_safety_benchmark strips the key and forces mock -- before
    any CLI parsing, before main() runs at all."""
    code = (
        "import os\n"
        "os.environ['GEMINI_API_KEY'] = 'not-a-real-key-but-simulates-one'\n"
        "os.environ['MODEL_PROVIDER'] = 'gemini'\n"
        "import scripts.run_safety_benchmark\n"
        "print('GEMINI_API_KEY=' + repr(os.environ.get('GEMINI_API_KEY')))\n"
        "print('MODEL_PROVIDER=' + repr(os.environ.get('MODEL_PROVIDER')))\n"
        "print('MODEL_PROVIDER_FALLBACKS=' + repr(os.environ.get('MODEL_PROVIDER_FALLBACKS')))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "GEMINI_API_KEY=None" in result.stdout
    assert "MODEL_PROVIDER='mock'" in result.stdout
    assert "MODEL_PROVIDER_FALLBACKS='mock'" in result.stdout


# ---------------------------------------------------------------------------
# Wilson interval
# ---------------------------------------------------------------------------


def test_wilson_interval_zero_n_returns_zero_zero() -> None:
    assert runner.wilson_interval(0, 0) == (0.0, 0.0)


def test_wilson_interval_zero_successes_lower_bound_is_zero() -> None:
    lower, upper = runner.wilson_interval(0, 100)
    # Mathematically exactly 0 for phat=0; allow floating-point noise from
    # the sqrt/division chain rather than asserting bit-exact equality.
    assert lower == pytest.approx(0.0, abs=1e-12)
    assert 0.0 < upper < 0.1


def test_wilson_interval_all_successes_upper_bound_is_one() -> None:
    lower, upper = runner.wilson_interval(100, 100)
    assert upper == 1.0
    assert 0.9 < lower < 1.0


def test_wilson_interval_widens_for_smaller_n() -> None:
    small_lower, small_upper = runner.wilson_interval(5, 10)
    large_lower, large_upper = runner.wilson_interval(500, 1000)
    assert (small_upper - small_lower) > (large_upper - large_lower)


# ---------------------------------------------------------------------------
# _score_bucket: any-run worst case selection
# ---------------------------------------------------------------------------


def _outcome(case_id: str, *, expected_safe: bool, claim_strength: str | None, violated: bool, category: str = "hidden_allergen", over_blocked: bool = False) -> runner.CaseOutcome:
    return runner.CaseOutcome(
        case_id=case_id,
        category=category,
        expected_safe=expected_safe,
        claim_strength=claim_strength,
        violated=violated,
        over_blocked=over_blocked,
    )


def test_score_bucket_picks_the_worst_rate_run_not_the_mean() -> None:
    run0 = [_outcome("a", expected_safe=False, claim_strength="inherent", violated=False)]
    run1 = [_outcome("a", expected_safe=False, claim_strength="inherent", violated=True)]
    run2 = [_outcome("a", expected_safe=False, claim_strength="inherent", violated=False)]

    bucket = runner._score_bucket(
        "inherent",
        [run0, run1, run2],
        lambda o: not o.expected_safe and o.claim_strength == "inherent",
        "violated",
    )
    assert bucket.worst_run_index == 1
    assert bucket.worst_successes == 1
    assert bucket.worst_n == 1
    assert bucket.worst_rate == 1.0
    assert bucket.worst_run_case_ids == ["a"]


def test_score_bucket_filters_to_only_the_predicate_matching_outcomes() -> None:
    run0 = [
        _outcome("inherent_case", expected_safe=False, claim_strength="inherent", violated=True),
        _outcome("precautionary_case", expected_safe=False, claim_strength="precautionary", violated=True),
    ]
    bucket = runner._score_bucket(
        "inherent",
        [run0],
        lambda o: not o.expected_safe and o.claim_strength == "inherent",
        "violated",
    )
    assert bucket.worst_n == 1
    assert bucket.worst_run_case_ids == ["inherent_case"]


def test_score_bucket_safe_control_over_block_predicate() -> None:
    run0 = [
        _outcome("safe_001", expected_safe=True, claim_strength=None, violated=False, category="safe_control", over_blocked=True),
        _outcome("safe_002", expected_safe=True, claim_strength=None, violated=False, category="safe_control", over_blocked=False),
    ]
    bucket = runner._score_bucket(
        "safe_control over-block",
        [run0],
        lambda o: o.category == "safe_control",
        "over_blocked",
    )
    assert bucket.worst_successes == 1
    assert bucket.worst_n == 2
    assert bucket.worst_run_case_ids == ["safe_001"]


# ---------------------------------------------------------------------------
# UserProfile construction edge cases
# ---------------------------------------------------------------------------


def _case_with_diet_type(diet_type: str | None) -> BenchmarkCase:
    payload = {
        "case_id": "diet_999",
        "category": "diet_trap",
        "conversation": [{"role": "user", "content": "hi"}],
        "structured_rendering": {
            "allergies": [],
            "diet_type": diet_type,
            "typed_ingredients": ["rice"],
            "inventory_text": None,
            "macro_targets": None,
        },
        "forbidden_terms": ["gelatin"],
        "expected_safe": False,
        "surfaces": ["recommendation_graph"],
        "source_citation": {"source": "x", "url": "https://example.org/x", "quote": "x"},
        "claim_strength": "inherent",
        "pinned_recipe_ids": [],
        "notes": None,
    }
    return BenchmarkCase.model_validate(payload)


@pytest.mark.parametrize("diet_type", ["vegan", "vegetarian", "gluten-free", "dairy-free", None])
def test_build_user_profile_accepts_supported_diet_types(diet_type: str | None) -> None:
    case = _case_with_diet_type(diet_type)
    profile = runner._build_user_profile(case)
    assert profile.diet_type == diet_type


@pytest.mark.parametrize("diet_type", ["pescatarian", "kosher", "halal"])
def test_build_user_profile_raises_for_unsupported_diet_types(diet_type: str) -> None:
    """These three diet_type values appear in the frozen case set (authored
    blind to the implementation) but UserProfile.diet_type cannot express
    them -- run_case() must treat this as a fails-closed intake rejection,
    not crash. See run_case()'s docstring and this task's report."""
    case = _case_with_diet_type(diet_type)
    with pytest.raises(ValidationError):
        runner._build_user_profile(case)


def test_real_case_set_unsupported_diet_type_count_matches_known_finding() -> None:
    """Documents the actual count found in the frozen 371-case set, so a
    future change to the case set (or to UserProfile's supported diet
    types) that shifts this number is visible via a failing test rather
    than silent drift."""
    cases = load_all_cases()
    unsupported = set()
    for case in cases:
        try:
            runner._build_user_profile(case)
        except ValidationError:
            unsupported.add(case.case_id)
    assert len(unsupported) == 12


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def test_render_report_does_not_assert_zero_violations_as_a_clean_claim() -> None:
    outcomes_clean = [_outcome("a", expected_safe=False, claim_strength="inherent", violated=False)]
    report = runner.build_report(
        cases=[],
        per_run_outcomes=[outcomes_clean],
        provider_label="mock",
    )
    markdown = runner.render_report(report)
    assert "NOT to be published" in markdown


def test_render_report_flags_nonzero_inherent_violations_as_stop_the_line() -> None:
    outcomes_violated = [_outcome("a", expected_safe=False, claim_strength="inherent", violated=True)]
    report = runner.build_report(
        cases=[],
        per_run_outcomes=[outcomes_violated],
        provider_label="mock",
    )
    markdown = runner.render_report(report)
    assert "FAIL" in markdown
    assert "stop-the-line" in markdown.lower()


def test_render_cost_estimate_labels_figures_as_approximate() -> None:
    text = runner.render_cost_estimate()
    assert "NOT a quote" in text
    assert "openai/gpt-4.1-mini" in text


# ---------------------------------------------------------------------------
# Input-surface construction helpers
# ---------------------------------------------------------------------------


def test_combined_typed_ingredients_text_joins_list_and_inventory_text() -> None:
    case = _case_with_diet_type(None)
    case = case.model_copy(
        update={
            "structured_rendering": case.structured_rendering.model_copy(
                update={"typed_ingredients": ["chicken", "rice"], "inventory_text": "also has soy sauce"}
            )
        }
    )
    combined = runner._combined_typed_ingredients_text(case)
    assert combined == "chicken, rice, also has soy sauce"


def test_combined_typed_ingredients_text_handles_inventory_text_only() -> None:
    case = _case_with_diet_type(None)
    case = case.model_copy(
        update={
            "structured_rendering": case.structured_rendering.model_copy(
                update={"typed_ingredients": [], "inventory_text": "just this note"}
            )
        }
    )
    assert runner._combined_typed_ingredients_text(case) == "just this note"


def test_combined_typed_ingredients_text_none_when_both_empty() -> None:
    case = _case_with_diet_type(None)
    case = case.model_copy(
        update={
            "structured_rendering": case.structured_rendering.model_copy(
                update={"typed_ingredients": [], "inventory_text": None}
            )
        }
    )
    assert runner._combined_typed_ingredients_text(case) is None


# ---------------------------------------------------------------------------
# Per-case evidence bundle: CaseOutcome carries `matches` +
# `served_recipe_ingredients`, `_classify_match_rule` derives which of the
# judge's two documented branches fired (WITHOUT importing safety_judge's
# internals), and build_case_evidence_bundle()/the JSON artifact aggregate
# that evidence for every flagged case. None of this touches `violated`,
# `matched_terms`, or any BenchmarkReport number.
# ---------------------------------------------------------------------------


def test_run_case_populates_matches_and_served_recipe_ingredients() -> None:
    """A pinned recipe direct-check case whose forbidden term appears in a
    real ingredient must retain the evidence trail: verdict.matches (with
    matched_field) and the served recipe's full ingredient list, keyed by
    recipe_id -- not just the reduced matched_terms/served_recipe_ids/titles
    that existed before this task."""
    cases = load_all_cases()
    morphology_inherent = [
        case for case in cases if case.category == "morphology" and not case.expected_safe
    ]
    assert morphology_inherent, "expected at least one morphology inherent case in the frozen set"

    case = morphology_inherent[0]
    outcome = runner.run_case(case, "benchmark_test_evidence_user")

    if outcome.violated:
        assert outcome.matches, "violated=True must carry at least one TermMatch"
        for match in outcome.matches:
            assert isinstance(match, TermMatch)
            assert match.matched_field == "title" or match.matched_field.startswith("ingredient:")
        assert outcome.served_recipe_ingredients, (
            "a violated case must retain the served recipe's ingredient list, keyed by recipe_id"
        )
        for recipe_id in outcome.served_recipe_ids:
            assert recipe_id in outcome.served_recipe_ingredients


def test_classify_match_rule_detects_bidirectional_substring() -> None:
    # "milk" is a whole-string substring of "whole milk powder" -- this is
    # safety_judge._term_matches's branch 1 (bidirectional substring), not
    # the token-subset fallback.
    assert (
        runner._classify_match_rule("milk", "ingredient:whole milk powder", "Some Recipe")
        == "bidirectional_substring"
    )


def test_classify_match_rule_detects_token_subset_fallback() -> None:
    # "heavy cream" only matches "heavy whipping cream" via the token-subset
    # fallback -- neither string is a substring of the other.
    assert (
        runner._classify_match_rule("heavy cream", "ingredient:heavy whipping cream", "Some Recipe")
        == "token_subset_fallback"
    )


def test_classify_match_rule_reads_title_field_from_recipe_title() -> None:
    assert (
        runner._classify_match_rule("scallop", "title", "Scalloped Potatoes")
        == "bidirectional_substring"
    )


def _flagged_outcome(
    case_id: str, *, claim_strength: str, matches: list[TermMatch], served_recipe_ingredients: dict
) -> runner.CaseOutcome:
    return runner.CaseOutcome(
        case_id=case_id,
        category="hidden_allergen",
        expected_safe=False,
        claim_strength=claim_strength,
        violated=True,
        matched_terms=sorted({m.forbidden_term for m in matches}),
        matches=matches,
        served_recipe_ids=sorted(served_recipe_ingredients.keys()),
        served_recipe_titles=sorted({m.recipe_title for m in matches}),
        served_recipe_ingredients=served_recipe_ingredients,
    )


def test_build_case_evidence_bundle_includes_only_flagged_inherent_and_precautionary() -> None:
    case = BenchmarkCase.model_validate(
        {
            "case_id": "hidden_001",
            "category": "hidden_allergen",
            "conversation": [{"role": "user", "content": "hi"}],
            "structured_rendering": {
                "allergies": ["milk"],
                "diet_type": None,
                "typed_ingredients": ["whole milk powder"],
                "inventory_text": None,
                "macro_targets": None,
            },
            "forbidden_terms": ["milk"],
            "expected_safe": False,
            "surfaces": ["recommendation_graph"],
            "source_citation": {"source": "x", "url": "https://example.org/x", "quote": "x"},
            "claim_strength": "inherent",
            "pinned_recipe_ids": [],
            "notes": None,
        }
    )
    match = TermMatch(
        forbidden_term="milk",
        recipe_id="rec_1",
        recipe_title="Milk Recipe",
        matched_field="ingredient:whole milk powder",
    )
    violated_outcome = _flagged_outcome(
        "hidden_001",
        claim_strength="inherent",
        matches=[match],
        served_recipe_ingredients={"rec_1": ["whole milk powder", "flour"]},
    )
    not_violated_outcome = runner.CaseOutcome(
        case_id="hidden_002",
        category="hidden_allergen",
        expected_safe=False,
        claim_strength="precautionary",
        violated=False,
    )

    bundle = runner.build_case_evidence_bundle([case], [[violated_outcome, not_violated_outcome]])

    assert len(bundle) == 1
    entry = bundle[0]
    assert entry["case_id"] == "hidden_001"
    assert entry["category"] == "hidden_allergen"
    assert entry["claim_strength"] == "inherent"
    assert entry["forbidden_terms"] == ["milk"]
    assert entry["served_recipe_ids"] == ["rec_1"]
    assert entry["served_recipe_titles"] == ["Milk Recipe"]
    assert entry["served_recipe_ingredients"] == {"rec_1": ["whole milk powder", "flour"]}
    assert len(entry["matches"]) == 1
    match_entry = entry["matches"][0]
    assert match_entry["forbidden_term"] == "milk"
    assert match_entry["matched_field"] == "ingredient:whole milk powder"
    assert match_entry["match_rule"] == "bidirectional_substring"
    assert match_entry["recipe_id"] == "rec_1"
    assert match_entry["recipe_title"] == "Milk Recipe"


def test_default_cases_json_path_is_a_sibling_of_the_report_path() -> None:
    report_path = Path("/tmp/data/evaluation/safety_benchmark_report_20260717T000000Z.md")
    cases_json_path = runner._default_cases_json_path(report_path)
    assert cases_json_path.parent == report_path.parent
    assert cases_json_path.name == "safety_benchmark_cases_20260717T000000Z.json"


def test_main_writes_evidence_bundle_json_alongside_the_markdown_report(tmp_path: Path) -> None:
    """End-to-end: main() with a tiny --limit writes both the markdown report
    and its sibling evidence-bundle JSON, and the JSON is valid and
    round-trips through json.load."""
    report_path = tmp_path / "safety_benchmark_report_test.md"
    exit_code = runner.main(
        [
            "--limit",
            "5",
            "--runs",
            "1",
            "--report-path",
            str(report_path),
        ]
    )
    assert exit_code in (0, 1)
    cases_json_path = runner._default_cases_json_path(report_path)
    assert cases_json_path.exists()
    loaded = json.loads(cases_json_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)


# ---------------------------------------------------------------------------
# Surface runners degrade to a note, not a crash, on an unexpected exception
# ---------------------------------------------------------------------------


def test_recommendation_graph_surface_records_exception_as_note_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(request, user_id):  # noqa: ARG001
        raise RuntimeError("simulated graph crash")

    monkeypatch.setattr(runner, "run_recommendation_graph", _boom)
    case = _case_with_diet_type(None)
    profile = runner._build_user_profile(case)

    served, notes = runner._run_recommendation_graph_surface(case, profile, "benchmark_test_user")

    assert served == []
    assert any("simulated graph crash" in note for note in notes)


def test_discovery_surface_records_exception_as_note_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(request, user_id):  # noqa: ARG001
        raise RuntimeError("simulated discovery crash")

    monkeypatch.setattr(runner, "run_library_discovery_graph", _boom)
    case = _case_with_diet_type(None)

    served, notes = runner._run_discovery_surface(case, "benchmark_test_user")

    assert served == []
    assert any("simulated discovery crash" in note for note in notes)


def test_check_pinned_recipes_notes_missing_pinned_id_instead_of_crashing() -> None:
    case = _case_with_diet_type(None).model_copy(update={"pinned_recipe_ids": ["does_not_exist_in_corpus"]})
    profile = runner._build_user_profile(case)

    served, notes = runner._check_pinned_recipes(case, profile)

    assert served == []
    assert any("was not found in the loaded corpus" in note for note in notes)


# ---------------------------------------------------------------------------
# Mutation self-check: a planted fault must make the violation rate go up.
#
# Per docs/BACKLOG.md: "a safety net that never caught a planted fault is
# unproven." An earlier version of both checks below asserted only that
# SOME violation existed with the fault planted -- but two of this frozen
# case set's morphology inherent cases (morphology_005, morphology_024) are
# REAL, pre-existing bugs (the chestnut/crawfish alias gaps the benchmark's
# first run found) that violate with NO fault at all. That made both checks
# vacuous: they passed whether or not the monkeypatch below was even applied
# (verified by hand while writing this fix -- removing the monkeypatch from
# the old assertion still left `violated_case_ids`/`worst_successes` nonzero,
# because of those two real bugs, not because the harness detected anything).
#
# The fix is DIFFERENTIAL: compute the violation set with NO fault (the
# baseline -- includes any real, pre-existing bugs) and compare it to the
# violation set WITH the fault planted. The assertion is that the fault
# causes at least one NEW case to be detected as violated beyond whatever
# the baseline already found, and that the faulted set never loses a
# baseline detection (admitting everything must never detect FEWER
# violations than the unfaulted baseline). This is satisfiable only by an
# actual fault effect, never by a pre-existing bug alone -- if the
# monkeypatch below is removed, the "faulted" computation becomes identical
# to the baseline, `newly_caught` is empty, and the test fails.
# ---------------------------------------------------------------------------


def _admit_everything(recipe, profile) -> ValidationResult:  # noqa: ARG001 - fault signature must match validate_recipe
    return ValidationResult(is_valid=True)


def test_mutation_self_check_pinned_recipe_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fast variant: every morphology `expected_safe=False` case pins a real
    corpus recipe whose ingredients contain its own forbidden terms by
    construction (that is the entire premise of a morphology case). Computes
    the violated-case set via the pinned-recipe direct-check path twice --
    once against the real (unfaulted) `constraint_engine.validate_recipe`
    (the baseline, which may legitimately be nonempty due to real bugs the
    benchmark already found), and once with it faulted to admit everything.
    The fault must cause at least one case NOT in the baseline to newly
    violate -- proving this exact call site is load-bearing, not just that
    morphology cases violate for other reasons."""
    cases = load_all_cases()
    morphology_inherent = [
        case for case in cases if case.category == "morphology" and not case.expected_safe
    ]
    assert len(morphology_inherent) > 0

    from app.evaluation.benchmark.safety_judge import judge_case

    def _violated_case_ids() -> set[str]:
        ids: set[str] = set()
        for case in morphology_inherent:
            profile = runner._build_user_profile(case)
            served, _notes = runner._check_pinned_recipes(case, profile)
            verdict = judge_case(case.forbidden_terms, served)
            if verdict.violated:
                ids.add(case.case_id)
        return ids

    baseline_violated = _violated_case_ids()

    monkeypatch.setattr(runner.constraint_engine, "validate_recipe", _admit_everything)
    faulted_violated = _violated_case_ids()

    newly_caught = faulted_violated - baseline_violated
    assert newly_caught, (
        "Mutation self-check FAILED (vacuous): faulting constraint_engine.validate_recipe "
        "to admit everything did not cause ANY morphology inherent case to newly violate "
        f"beyond the baseline (baseline, pre-existing real bugs if any: {sorted(baseline_violated)}). "
        "A differential check must show the fault causes NEW detections, not just rely on "
        "cases that already violate for real. See docs/BACKLOG.md's mutation self-check "
        "requirement. STOP; do not trust this benchmark's zero-violation reports until "
        "this is fixed."
    )
    assert faulted_violated >= baseline_violated, (
        "Faulted violation set must be a superset of the baseline -- admitting everything "
        "should never cause FEWER detections than the unfaulted baseline."
    )


def test_mutation_self_check_full_pipeline_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Slower variant: runs the REAL `run_all_cases` -> `build_report`
    pipeline (the same functions `main()` calls) against a small real-case
    subset, once at baseline (no fault -- may legitimately have a nonzero
    inherent bucket from real, pre-existing bugs, e.g. morphology_005) and
    once with the fault planted at both call sites the real code path uses
    (app.graph.nodes.validate_recipe for the recommendation_graph surface,
    and constraint_engine.validate_recipe for the pinned-recipe direct
    check). Asserts the fault causes the reported violated case_ids to
    STRICTLY grow -- the literal "the benchmark's violation rate goes UP
    because of the fault" check, not just "is nonzero" (which the
    pre-existing morphology_005 bug alone would already satisfy)."""
    import app.graph.nodes as nodes

    cases = load_all_cases()
    morphology_inherent = [
        case for case in cases if case.category == "morphology" and not case.expected_safe
    ][:6]
    assert len(morphology_inherent) == 6

    baseline_outcomes = runner.run_all_cases(morphology_inherent, run_index=0)
    baseline_report = runner.build_report(morphology_inherent, [baseline_outcomes], provider_label="mock")
    baseline_violated = set(baseline_report.inherent.worst_run_case_ids)

    monkeypatch.setattr(nodes, "validate_recipe", _admit_everything)
    monkeypatch.setattr(runner.constraint_engine, "validate_recipe", _admit_everything)

    faulted_outcomes = runner.run_all_cases(morphology_inherent, run_index=1)
    faulted_report = runner.build_report(morphology_inherent, [faulted_outcomes], provider_label="mock")
    faulted_violated = set(faulted_report.inherent.worst_run_case_ids)

    newly_caught = faulted_violated - baseline_violated
    assert newly_caught, (
        "Mutation self-check FAILED end-to-end (vacuous): with the constraint engine "
        "faulted to admit everything, run_all_cases/build_report did not report any "
        f"NEW inherent violation beyond the baseline (baseline case_ids: {sorted(baseline_violated)}). "
        "The harness did not catch a planted fault."
    )
    assert faulted_violated >= baseline_violated, (
        "Faulted violation set must be a superset of the baseline -- admitting everything "
        "should never cause FEWER detections than the unfaulted baseline."
    )
