from app.services.vision_service import extract_inventory_from_image


def test_mock_vision_uses_default_for_generic_filename() -> None:
    observations = extract_inventory_from_image("generic_fridge_photo.jpg")

    assert [item.normalized_name for item in observations] == [
        "chicken breast",
        "spinach",
        "egg",
        "bell pepper",
        "Greek yogurt",
        "rice",
    ]
    assert any(item.needs_confirmation for item in observations)


def test_mock_vision_uses_filename_specific_scenario() -> None:
    observations = extract_inventory_from_image("vegetarian_pantry_upload.png")

    names = [item.normalized_name for item in observations]
    assert "tofu" in names
    assert "broccoli" in names
    assert "soy sauce" in names
