import pytest

from app.schemas.inventory import InventoryObservation
from app.services.text_inventory_parser import merge_inventory_observations, parse_typed_inventory
from app.utils import ingredient_normalizer


def test_parses_comma_separated_text() -> None:
    observations = parse_typed_inventory("chicken breast, spinach, eggs")

    assert [item.normalized_name for item in observations] == ["chicken breast", "spinach", "egg"]
    assert all(item.confidence == 1.0 for item in observations)
    assert all(item.source == "text" for item in observations)


def test_normalizes_synonyms() -> None:
    observations = parse_typed_inventory("capsicum, greek yoghurt, courgette, scallion")

    assert [item.normalized_name for item in observations] == [
        "bell pepper",
        "Greek yogurt",
        "zucchini",
        "green onion",
    ]


def test_fuzzy_normalizes_common_typos_when_rapidfuzz_is_available() -> None:
    if ingredient_normalizer.process is None:
        pytest.skip("rapidfuzz is optional and is not installed")

    observations = parse_typed_inventory("chikcen brest, greeek yogurt, bell peper")

    assert [item.normalized_name for item in observations] == [
        "chicken breast",
        "Greek yogurt",
        "bell pepper",
    ]


def test_merge_inventory_keeps_user_text_over_uncertain_vision_duplicate() -> None:
    text_items = parse_typed_inventory("bell pepper, rice")
    vision_items = [
        InventoryObservation(
            raw_name="capsicum",
            normalized_name="bell pepper",
            confidence=0.62,
            source="vision",
            needs_confirmation=True,
        ),
        InventoryObservation(
            raw_name="spinach",
            normalized_name="spinach",
            confidence=0.86,
            source="vision",
            needs_confirmation=False,
        ),
    ]

    merged = merge_inventory_observations(text_items, vision_items)
    by_name = {item.normalized_name: item for item in merged}

    assert list(by_name) == ["bell pepper", "rice", "spinach"]
    assert by_name["bell pepper"].source == "text"
    assert by_name["bell pepper"].confidence == 1.0
