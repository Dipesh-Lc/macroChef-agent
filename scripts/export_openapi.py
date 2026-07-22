"""SPA rebuild W1b: export the FastAPI app's OpenAPI schema to
`web/openapi.json`, so `openapi-typescript` can generate TS types for the
React SPA (`web/src/api/types.gen.ts`) without the SPA's build needing a
live backend process.

Pure export: imports `app.main:app` and writes `app.openapi()` verbatim
(UTF-8) -- no schema mutation, no safety/nutrition logic here at all.

Usage:
    python scripts/export_openapi.py
"""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

OUTPUT_PATH = ROOT / "web" / "openapi.json"


def main() -> None:
    schema = app.openapi()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"Wrote OpenAPI schema to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
