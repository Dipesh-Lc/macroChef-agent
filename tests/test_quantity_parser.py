from app.utils.quantity_parser import parse_quantity_string


def test_parses_mass_prefix() -> None:
    assert parse_quantity_string("150 g chicken breast") == {
        "name": "chicken breast",
        "amount": 150.0,
        "unit": "g",
    }


def test_parses_volume_prefix() -> None:
    parsed = parse_quantity_string("2 cups rice")
    assert parsed == {"name": "rice", "amount": 2.0, "unit": "cup"}


def test_parses_count_no_unit() -> None:
    # "medium" is a descriptor, not a unit — amount is the count, unit stays None.
    assert parse_quantity_string("1 medium egg") == {
        "name": "medium egg",
        "amount": 1.0,
        "unit": None,
    }


def test_parses_fraction() -> None:
    assert parse_quantity_string("1 1/2 tbsp olive oil") == {
        "name": "olive oil",
        "amount": 1.5,
        "unit": "tbsp",
    }
    assert parse_quantity_string("1/2 cup milk")["amount"] == 0.5


def test_bare_name_no_quantity() -> None:
    assert parse_quantity_string("chicken breast") == {
        "name": "chicken breast",
        "amount": None,
        "unit": None,
    }


def test_empty_and_garbage_fallback_to_name() -> None:
    assert parse_quantity_string("") == {"name": "", "amount": None, "unit": None}
    # No leading number -> whole string is the name.
    assert parse_quantity_string("a pinch of salt")["name"] == "a pinch of salt"
    # A bare quantity with no food still yields a non-empty name.
    assert parse_quantity_string("500 g")["name"]
