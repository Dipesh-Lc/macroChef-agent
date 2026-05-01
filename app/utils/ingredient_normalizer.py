import re

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover - optional dependency fallback
    fuzz = None
    process = None


SYNONYMS = {
    "bell peppers": "bell pepper",
    "capsicum": "bell pepper",
    "chix": "chicken",
    "chicken": "chicken breast",
    "chicken breasts": "chicken breast",
    "chickpeas": "chickpea",
    "garbanzo": "chickpea",
    "garbanzo beans": "chickpea",
    "greek yoghurt": "Greek yogurt",
    "greek yogurt": "Greek yogurt",
    "yoghurt": "yogurt",
    "courgette": "zucchini",
    "aubergine": "eggplant",
    "cilantro": "coriander",
    "scallion": "green onion",
    "scallions": "green onion",
    "spring onion": "green onion",
    "spring onions": "green onion",
    "brown rice": "brown rice",
    "white rice": "rice",
    "eggs": "egg",
    "egg whites": "egg white",
    "shrimp": "shrimp",
    "prawns": "shrimp",
    "peanuts": "peanut",
    "peanut butter": "peanut butter",
    "coconut milk": "coconut milk",
    "soy sauce": "soy sauce",
    "tamari": "soy sauce",
    "gluten free tamari": "soy sauce",
    "mozzarella cheese": "mozzarella",
    "parmesan cheese": "parmesan",
    "feta cheese": "feta",
    "bell pepper": "bell pepper",
}

CANONICAL_INGREDIENTS = sorted(
    {
        *SYNONYMS.values(),
        "almond",
        "avocado",
        "basil",
        "bean",
        "beef",
        "black bean",
        "bread",
        "broccoli",
        "brown rice",
        "carrot",
        "cauliflower",
        "cheddar",
        "chicken breast",
        "chickpea",
        "coconut milk",
        "coriander",
        "corn",
        "cucumber",
        "egg",
        "eggplant",
        "feta",
        "garlic",
        "ginger",
        "green onion",
        "Greek yogurt",
        "ground turkey",
        "lemon",
        "lentil",
        "lime",
        "mozzarella",
        "mushroom",
        "oats",
        "olive oil",
        "onion",
        "paneer",
        "parmesan",
        "pasta",
        "peanut",
        "quinoa",
        "rice",
        "salmon",
        "shrimp",
        "soy sauce",
        "spinach",
        "sweet potato",
        "tofu",
        "tomato",
        "tortilla",
        "turkey",
        "zucchini",
    }
)

DESCRIPTORS = {
    "fresh",
    "frozen",
    "canned",
    "organic",
    "raw",
    "cooked",
    "large",
    "small",
    "medium",
    "low fat",
    "reduced fat",
    "boneless",
    "skinless",
}


def cleanup_ingredient_name(name: str) -> str:
    cleaned = name.strip().replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    cleaned = re.sub(r"\b\d+(\.\d+)?\b", " ", cleaned)
    unit_pattern = r"\b(cups?|tbsp|tsp|grams?|g|kg|oz|ounces?|lbs?|pounds?|cloves?)\b"
    cleaned = re.sub(unit_pattern, " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def normalize_ingredient(name: str) -> str:
    """Normalize free-form ingredient names for matching and scoring."""

    if not name:
        return ""

    cleaned = cleanup_ingredient_name(name)
    key = cleaned.lower()

    if key in SYNONYMS:
        return SYNONYMS[key]

    for descriptor in sorted(DESCRIPTORS, key=len, reverse=True):
        key = re.sub(rf"\b{re.escape(descriptor)}\b", " ", key)

    key = re.sub(r"\s+", " ", key).strip()
    if key in SYNONYMS:
        return SYNONYMS[key]

    if key.endswith("ies"):
        key = f"{key[:-3]}y"
    elif key.endswith("s") and not key.endswith(("ss", "us")):
        key = key[:-1]

    if key == "greek yogurt":
        return "Greek yogurt"

    return fuzzy_normalize_ingredient(key)


def fuzzy_normalize_ingredient(name: str, threshold: int = 88) -> str:
    """Map close misspellings to known pantry names when rapidfuzz is installed."""

    if not name or process is None or fuzz is None:
        return name

    match = process.extractOne(name, CANONICAL_INGREDIENTS, scorer=fuzz.WRatio)
    if match and match[1] >= threshold:
        return match[0]
    return name


def normalize_many(names: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for name in names:
        value = normalize_ingredient(name)
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized


def ingredient_matches(candidate: str, inventory_item: str) -> bool:
    left = normalize_ingredient(candidate).lower()
    right = normalize_ingredient(inventory_item).lower()
    if not left or not right:
        return False
    return left == right or left in right or right in left
