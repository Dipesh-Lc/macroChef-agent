"""Schema-drift CI gate (ROADMAP.md Phase 5, Step 5.1).

Confirms the committed migrations under `alembic/versions/` (currently
just the baseline, `0001_baseline_schema.py`) and `app.data.models`'
*current* `Base.metadata` never silently drift apart. Every model change
must ship with a matching migration -- if it doesn't, this test fails.

Runs `alembic` as a real subprocess (matching how it's actually invoked --
locally as `alembic upgrade head`, and in `.github/workflows/ci.yml`'s
`deploy` job the same way against the prod DB) rather than calling
Alembic's Python API in-process. `app.data.db` computes its `engine`/
`database_url` at MODULE IMPORT time from whatever `DATABASE_URL` happened
to be set when it was first imported (see that module's own comment on
why) -- since other test modules in this same pytest session may already
have imported it against the default sqlite DB before this test runs, an
in-process call would silently target the wrong database. A subprocess
gets a fresh interpreter and therefore a fresh, correctly-scoped import of
`app.data.db` for the `DATABASE_URL` this test actually sets.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env.setdefault("EMBEDDING_PROVIDER", "hash")
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_baseline_migration_applies_cleanly_to_fresh_sqlite(tmp_path):
    db_path = tmp_path / "alembic_baseline_check.db"

    result = _run_alembic("upgrade", "head", db_path=db_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert db_path.exists()


def test_schema_drift_gate_autogenerate_diff_is_empty(tmp_path):
    """The schema-drift CI gate itself.

    `alembic check` runs Alembic's own autogenerate comparison between the
    live DB (after applying every committed migration) and the current
    `Base.metadata`, and exits nonzero if it would generate any further
    `op.*` calls -- i.e. if a model was added/changed without a matching
    migration. This is the exact scenario the gate exists to catch before
    it reaches a real Postgres deploy running `alembic upgrade head`.
    """
    db_path = tmp_path / "alembic_drift_check.db"

    upgrade_result = _run_alembic("upgrade", "head", db_path=db_path)
    assert upgrade_result.returncode == 0, (
        upgrade_result.stdout + upgrade_result.stderr
    )

    check_result = _run_alembic("check", db_path=db_path)
    assert check_result.returncode == 0, (
        "Schema drift detected between app/data/models.py and the "
        "committed Alembic migrations under alembic/versions/ -- run "
        "`alembic revision --autogenerate -m '<description>'` and commit "
        "the resulting migration.\n"
        f"{check_result.stdout}{check_result.stderr}"
    )
