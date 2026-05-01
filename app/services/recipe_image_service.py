from urllib.parse import quote_plus

CUISINE_COLORS = {
    "italian": "8f3d2f",
    "indian": "8a5a1f",
    "japanese": "243f5c",
    "chinese": "7a332e",
    "mexican": "2f6b4f",
    "mediterranean": "246052",
    "american": "4d4f45",
}


def placeholder_image_url(
    title: str,
    cuisine: str | None = None,
    meal_type: str | None = None,
) -> str:
    label = quote_plus(f"{cuisine or meal_type or 'MacroChef'} recipe\n{title}")
    color = CUISINE_COLORS.get((cuisine or "").lower(), "243f36")
    return f"https://placehold.co/640x420/{color}/f2f0eb/png?text={label}"
