import re

from app.schemas.inventory import InventoryObservation
from app.utils.ingredient_normalizer import normalize_ingredient


def parse_typed_inventory(text: str | None) -> list[InventoryObservation]:
    if not text:
        return []

    tokens = [token.strip() for token in re.split(r"[,\n;]+", text) if token.strip()]
    observations: list[InventoryObservation] = []
    seen: set[str] = set()

    for token in tokens:
        normalized = normalize_ingredient(token)
        if not normalized or normalized in seen:
            continue
        observations.append(
            InventoryObservation(
                raw_name=token,
                normalized_name=normalized,
                quantity=None,
                confidence=1.0,
                source="text",
                needs_confirmation=False,
            )
        )
        seen.add(normalized)

    return observations


def merge_inventory_observations(
    *observation_groups: list[InventoryObservation],
) -> list[InventoryObservation]:
    """Merge inventory observations by normalized name, keeping the most reliable source."""

    merged: dict[str, InventoryObservation] = {}
    source_priority = {"manual": 3, "text": 2, "vision": 1}

    for observations in observation_groups:
        for observation in observations:
            key = observation.normalized_name.lower()
            current = merged.get(key)
            if current is None:
                merged[key] = observation
                continue

            current_rank = (source_priority[current.source], current.confidence)
            next_rank = (source_priority[observation.source], observation.confidence)
            if next_rank > current_rank:
                merged[key] = observation

    return list(merged.values())
