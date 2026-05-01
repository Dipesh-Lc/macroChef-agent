from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rag.build_index import build_recipe_index  # noqa: E402


def main() -> None:
    count = build_recipe_index()
    print(f"Ingested {count} recipes into Chroma.")


if __name__ == "__main__":
    main()
