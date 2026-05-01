from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.db import init_db  # noqa: E402
from app.rag.loaders import load_recipes  # noqa: E402


def main() -> None:
    init_db()
    recipes = load_recipes()
    print(f"SQLite tables ready. Sample recipe file contains {len(recipes)} recipes.")


if __name__ == "__main__":
    main()
