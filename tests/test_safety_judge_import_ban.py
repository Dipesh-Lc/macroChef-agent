"""Enforces the safety_judge independence rule via a real import-graph walk.

`app/evaluation/benchmark/safety_judge.py` must never import
`app.services.constraint_engine` or `app.utils.ingredient_normalizer`,
directly OR transitively -- see that module's docstring for why. This test
does NOT grep the source text (a grep can't see a banned module pulled in
two import-hops away through some other module `safety_judge` imports); it
statically parses `safety_judge.py`'s AST, resolves every module it imports
to a file on disk, parses THOSE files' AST too, and recurses -- building the
real transitive import closure without ever executing any of the modules
(so this test is fast and has no side effects, even though several modules
in this codebase have heavy import-time costs, e.g. chromadb/sentence-
transformers).
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

BANNED_MODULES = frozenset(
    {
        "app.services.constraint_engine",
        "app.utils.ingredient_normalizer",
    }
)

JUDGE_MODULE = "app.evaluation.benchmark.safety_judge"


def _resolve_module_file(module_name: str) -> Path | None:
    """Resolve `module_name` to a `.py` file on disk WITHOUT importing/
    executing it, or None if it can't be resolved to a plain Python source
    file (compiled extension, namespace package, third-party module we
    don't need to recurse into, or a name that isn't actually a module)."""
    try:
        spec = importlib.util.find_spec(module_name)
    except Exception:
        # Some third-party packages raise on find_spec for odd dotted
        # names (e.g. a name that's actually a class/attribute, not a
        # submodule) -- treat as an unresolvable leaf, not a test failure.
        return None
    if spec is None or spec.origin is None:
        return None
    if not spec.origin.endswith(".py"):
        return None
    return Path(spec.origin)


def _is_project_module(module_name: str) -> bool:
    """True for modules that are part of THIS project's own source tree
    (the only place the banned modules could possibly live, or be
    re-exposed through). Bounds recursion to `app.*` -- third-party
    packages (pydantic, etc.) have no way to import back into this
    project, so there is no need to parse their internals, which is also
    what keeps this walker from having to handle third-party packages'
    own relative imports (e.g. pydantic's internal `from ._internal import
    ...`)."""
    return module_name == "app" or module_name.startswith("app.")


def _direct_imports(module_name: str, source_path: Path) -> set[str]:
    """Every module name `module_name`'s source directly imports (both
    `import x.y` and `from x.y import z`).

    For `from x.y import z` this records BOTH `x.y` (the module itself) AND
    `x.y.z` (module-plus-attribute) for every imported name. The second form
    is what makes `from app.services import constraint_engine` detectable:
    without it, only `node.module` ("app.services") would be recorded, and
    the banned name "app.services.constraint_engine" would never enter the
    closure -- see this test module's docstring / the bug this fixes. Some
    of the `x.y.z` names recorded this way aren't real modules (e.g.
    `from app.schemas.recipe import Recipe` records "app.schemas.recipe.
    Recipe", which is a class, not a module) -- that's harmless: the ban
    set only ever contains real module names, and `_resolve_module_file`
    already treats unresolvable names as leaves rather than raising (see
    its docstring/try-except), so bogus module-plus-attribute names are
    silently dropped during recursion, not flagged.

    Only called on project (`app.*`) modules -- this codebase's own source
    uses no relative imports (verified by `test_no_relative_imports_in_app_
    package` below), so relative-import resolution is intentionally not
    implemented here. A relative import appearing in a *project* module
    would raise loudly rather than silently under-report; third-party
    packages (which do use relative imports internally) are never passed
    to this function -- see `_is_project_module` and its use in
    `transitive_import_closure`.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                raise AssertionError(
                    f"{source_path}: relative import (level={node.level}) found; "
                    "this import-graph walker only resolves absolute imports. "
                    "Update _direct_imports before adding relative imports here."
                )
            if node.module:
                names.add(node.module)
                for alias in node.names:
                    names.add(f"{node.module}.{alias.name}")
    return names


def transitive_import_closure(start_module: str) -> set[str]:
    """Every module name reachable from `start_module` by following
    imports, including `start_module` itself.

    Every directly-imported name (project, stdlib, or third-party) is
    recorded in the returned set, so a banned module imported directly
    would still be caught. Recursion (parsing a module's own source to
    find ITS imports) only descends into project (`app.*`) modules --
    see `_is_project_module` for why that bound is safe: the banned
    modules are project modules, and nothing outside this project can
    import them back in.
    """
    seen: set[str] = set()
    frontier = [start_module]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        if not _is_project_module(current):
            continue
        path = _resolve_module_file(current)
        if path is None:
            continue
        for imported in _direct_imports(current, path):
            if imported not in seen:
                frontier.append(imported)
    return seen


def test_safety_judge_import_closure_excludes_banned_modules() -> None:
    closure = transitive_import_closure(JUDGE_MODULE)
    hits = closure & BANNED_MODULES
    assert not hits, (
        f"safety_judge's transitive import closure includes banned module(s) {sorted(hits)}. "
        "The judge must be independent of the system under test -- see "
        "app/evaluation/benchmark/safety_judge.py's module docstring."
    )


def test_safety_judge_import_closure_is_non_trivial() -> None:
    """Sanity check on the walker itself: the closure should include more
    than just the judge module (at minimum, `pydantic` and `re`), so an
    empty/near-empty closure (which would make the ban check vacuous)
    can't slip by silently."""
    closure = transitive_import_closure(JUDGE_MODULE)
    assert JUDGE_MODULE in closure
    assert len(closure) > 1


def test_direct_imports_catches_both_from_import_forms(tmp_path: Path) -> None:
    """Regression test for the bug where `from app.services import
    constraint_engine` (module-then-attribute form) escaped the ban check
    while `from app.services.constraint_engine import contains_allergen`
    (fully-qualified form) was already caught.

    Plants BOTH forms in a throwaway fixture module (never the real
    `safety_judge.py` on disk) and runs the same `_direct_imports` walker
    the ban check uses against it, asserting the banned module name shows
    up in the recorded names for each form independently.
    """
    module_attr_form = tmp_path / "fixture_module_attr_form.py"
    module_attr_form.write_text(
        "from app.services import constraint_engine\n",
        encoding="utf-8",
    )
    fully_qualified_form = tmp_path / "fixture_fully_qualified_form.py"
    fully_qualified_form.write_text(
        "from app.services.constraint_engine import contains_allergen\n",
        encoding="utf-8",
    )

    module_attr_names = _direct_imports("fixture_module_attr_form", module_attr_form)
    assert "app.services.constraint_engine" in module_attr_names, (
        "The module-then-attribute form `from app.services import "
        "constraint_engine` was not detected -- this is the exact form "
        "that escaped the ban check before this fix."
    )

    fully_qualified_names = _direct_imports(
        "fixture_fully_qualified_form", fully_qualified_form
    )
    assert "app.services.constraint_engine" in fully_qualified_names, (
        "The fully-qualified form `from app.services.constraint_engine "
        "import contains_allergen` regressed -- it was already caught "
        "before this fix and must remain caught."
    )


def test_no_relative_imports_in_app_package() -> None:
    """Guards `_direct_imports`'s "no relative imports in this codebase"
    assumption: if this ever starts failing, the import-ban walker above
    needs relative-import resolution before it can be trusted again."""
    root = Path(__file__).resolve().parents[1] / "app"
    offenders: list[str] = []
    for py_file in root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
                offenders.append(str(py_file))
    assert not offenders, f"Relative imports found (walker needs updating): {offenders}"
