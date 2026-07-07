import json
from pathlib import Path

from app.schemas.nutrition import FoodMatch
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Sentinel stored in place of a FoodMatch dict to mean "we got a real FDC
# response for this query and confirmed no acceptable candidate" -- distinct
# from "never looked up" (key absent). Only ever written after a genuine 200
# response; a transient failure (network error, non-2xx) must never reach
# this state, or a momentary flake would get cached as a permanent no-match.
_NO_MATCH = "__no_match__"


class FdcCache:
    """Disk-backed cache from normalized ingredient query to `FoodMatch`.

    Avoids refetching the same ingredient from USDA FDC across process
    restarts. Keeps an in-memory dict in front of a JSON file on disk; reads
    are served from memory once loaded, writes go to both.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._data: dict[str, dict] | None = None

    def _load(self) -> dict[str, dict]:
        if self._data is not None:
            return self._data
        if not self._path.exists():
            self._data = {}
            return self._data
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Failed to read FDC cache at %s: %s", self._path, exc)
            self._data = {}
        return self._data

    def get(self, query: str) -> FoodMatch | None:
        raw = self._load().get(query)
        if raw is None or raw == _NO_MATCH:
            return None
        return FoodMatch.model_validate(raw)

    def is_confirmed_no_match(self, query: str) -> bool:
        """True only for a query that received a real FDC response with no
        acceptable candidate -- never true for a query that simply hasn't
        been looked up, and never set after a transient request failure."""
        return self._load().get(query) == _NO_MATCH

    def set(self, query: str, match: FoodMatch) -> None:
        data = self._load()
        data[query] = match.model_dump(mode="json")
        self._write(data)

    def set_no_match(self, query: str) -> None:
        data = self._load()
        data[query] = _NO_MATCH
        self._write(data)

    def _write(self, data: dict[str, dict]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp_path.replace(self._path)
        except OSError as exc:
            logger.warning("Failed to write FDC cache at %s: %s", self._path, exc)
