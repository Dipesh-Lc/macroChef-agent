import json
from pathlib import Path
from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)

# Schema version for the on-disk cache file. Bumping this invalidates any
# older cache shape on load (see `_load`) rather than attempting to
# interpret it -- the safe behavior for a cache whose meaning changed, not
# just its serialization.
_SCHEMA_VERSION = 2


class FdcCache:
    """Disk-backed cache of raw USDA FDC `/foods/search` request/response
    payloads, keyed by the exact request (`search_query`, `data_types`
    tier, `page_size`) that produced them.

    This cache stores FACTS ("FDC returned this JSON for this exact
    request"), never DECISIONS ("this is the food we picked"). Matching
    logic (`_best_match` and friends in `usda_client.py`) is re-run against
    the cached payload on every call, so a change to the matching,
    plausibility, or preparation rules takes effect on the very next run
    without needing any cache invalidation -- there is nothing decision-like
    on disk to go stale. This is a deliberate refactor away from an earlier
    cache generation that stored the *decided* `FoodMatch` (or a "no match"
    sentinel) per ingredient query: that shape made rule changes invisible
    for any ingredient already cached, which is precisely what this project
    phase set out to fix. See the phase 1.5 design note in the executor
    task spec for the full rationale.

    A payload with an empty (or missing) `foods` list is itself a valid,
    cacheable fact -- "FDC was asked this and had nothing" -- so, unlike the
    old generation, there is no separate "confirmed no match" sentinel or
    method here. A cache miss (`get_payload` returns `None`) means "this
    exact request has never successfully completed," not "FDC has nothing."

    Migration: a cache file written by the pre-refactor decision-cache (or
    any file that isn't valid JSON, or is JSON but lacks this generation's
    `_schema_version` marker) is a different, incompatible shape. It is
    detected on load, discarded, and logged rather than partially
    interpreted -- there is nothing valid to carry forward from it (it never
    stored the raw payloads this generation needs), so a cold cache simply
    re-fetches from FDC as needed.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._data: dict[str, Any] | None = None

    def _empty(self) -> dict[str, Any]:
        return {"_schema_version": _SCHEMA_VERSION, "entries": {}}

    def _load(self) -> dict[str, Any]:
        if self._data is not None:
            return self._data
        if not self._path.exists():
            self._data = self._empty()
            return self._data
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Failed to read FDC cache at %s: %s", self._path, exc)
            self._data = self._empty()
            return self._data

        if not isinstance(raw, dict) or raw.get("_schema_version") != _SCHEMA_VERSION or "entries" not in raw:
            logger.warning(
                "FDC cache at %s is an older/incompatible schema (pre-refactor "
                "decision cache or corrupt) -- discarding and starting cold "
                "rather than misinterpreting its contents.",
                self._path,
            )
            self._data = self._empty()
            return self._data

        self._data = raw
        return self._data

    @staticmethod
    def _key(search_query: str, data_types: tuple[str, ...] | list[str], page_size: int) -> str:
        # "|" and "::" can never appear inside a normalized query or a
        # dataType name, so this plain join is an unambiguous, human-readable
        # key -- easier to eyeball/diff in the on-disk JSON than a hash.
        return "::".join([search_query, "|".join(data_types), str(page_size)])

    def get_payload(
        self, search_query: str, data_types: tuple[str, ...] | list[str], page_size: int
    ) -> dict | None:
        """The cached raw FDC response for this exact request, or `None` if
        it has never been successfully fetched. `None` is a cache MISS, not
        a signal about whether FDC has any matching food -- an empty
        `{"foods": []}` payload is a legitimate, cacheable HIT."""
        key = self._key(search_query, data_types, page_size)
        return self._load()["entries"].get(key)

    def set_payload(
        self,
        search_query: str,
        data_types: tuple[str, ...] | list[str],
        page_size: int,
        payload: dict,
    ) -> None:
        key = self._key(search_query, data_types, page_size)
        data = self._load()
        data["entries"][key] = payload
        self._write(data)

    def _write(self, data: dict) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp_path.replace(self._path)
        except OSError as exc:
            logger.warning("Failed to write FDC cache at %s: %s", self._path, exc)
