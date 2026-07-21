"""Roadmap item "Shareable plan URLs" (Phase 4 item 4): locks in the "no
LLM anywhere on this path" rule from this feature's design spec by
statically scanning the share modules' imports rather than trusting a
comment. See app.services.share_service's module docstring for the safety
reasoning (allergy/nutrition decisions are never made by an LLM in this
codebase; the share path makes no decision at all, so it must not import
anything that could tempt one in later)."""

import ast
from pathlib import Path

import pytest

_SHARE_MODULE_PATHS = [
    "app/services/share_service.py",
    "app/api/routes_share.py",
    "app/schemas/share.py",
    "app/data/share_repository.py",
]

# Any import whose dotted path contains one of these (case-insensitive)
# substrings is treated as an LLM/model-provider dependency. Deliberately
# broad -- app.services.model_provider is the concrete in-repo module, and
# the raw provider SDK names are blocked too so a future direct SDK import
# (bypassing model_provider.py) would also fail this test.
_FORBIDDEN_IMPORT_SUBSTRINGS = (
    "model_provider",
    "anthropic",
    "openai",
    "google.generativeai",
    "genai",
    "gemini",
    "ollama",
    "langchain",
    "langgraph",
)


def _imported_module_names(source_path: Path) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


@pytest.mark.parametrize("relative_path", _SHARE_MODULE_PATHS)
def test_share_module_imports_no_llm_or_model_provider_dependency(relative_path: str) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    source_path = repo_root / relative_path
    assert source_path.exists(), f"expected {relative_path} to exist"

    imported = _imported_module_names(source_path)
    lowered = [name.lower() for name in imported]

    offenders = [
        name
        for name in lowered
        if any(forbidden in name for forbidden in _FORBIDDEN_IMPORT_SUBSTRINGS)
    ]
    assert offenders == [], (
        f"{relative_path} imports an LLM/model-provider dependency: {offenders} "
        f"(full import list: {imported}) -- the share path must never involve an LLM."
    )
