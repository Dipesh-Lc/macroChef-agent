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

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# ROADMAP.md Phase 5, Step 5.2: set in CI's pgvector service job and locally
# via `docker compose up pgvector` (see docker-compose.yml) to also verify
# the 0002 migration (recipe_embeddings, gated to postgresql-only) against a
# REAL Postgres, not just sqlite's no-op path. Skipped entirely otherwise --
# these tests must never require Postgres to be running.
TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")


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


@pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="TEST_POSTGRES_URL not set (needs `docker compose up pgvector`, see docker-compose.yml)",
)
def test_migrations_apply_cleanly_and_drift_free_on_fresh_postgres():
    """Real-Postgres analog of the two sqlite tests above, closing the gap
    the 2026-07-28 handoff flagged: Step 5.1's Alembic path was verified
    against sqlite only. Also proves the 0002 migration (pgvector's
    `recipe_embeddings` table + HNSW index, a no-op on sqlite) actually runs
    on Postgres, and that `alembic/env.py`'s `include_object` exclusion
    keeps `alembic check` from proposing to drop that externally-managed
    table (see that module's comment for why the exclusion is needed at
    all -- confirmed by hand while building this: without it, `check`
    reflects the live table, finds it absent from `Base.metadata`, and
    flags it as drift to remove).
    """
    import uuid

    import psycopg2

    db_name = f"macrochef_alembic_test_{uuid.uuid4().hex[:8]}"
    base_url = TEST_POSTGRES_URL.rsplit("/", 1)[0]
    test_db_url = f"{base_url}/{db_name}"

    admin_conn = psycopg2.connect(TEST_POSTGRES_URL)
    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        admin_conn.close()

    try:
        env = os.environ.copy()
        env["DATABASE_URL"] = test_db_url
        env.setdefault("EMBEDDING_PROVIDER", "hash")

        upgrade_result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
        )
        assert upgrade_result.returncode == 0, upgrade_result.stdout + upgrade_result.stderr

        check_result = subprocess.run(
            [sys.executable, "-m", "alembic", "check"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
        )
        assert check_result.returncode == 0, (
            "Schema drift detected against real Postgres.\n"
            f"{check_result.stdout}{check_result.stderr}"
        )

        verify_conn = psycopg2.connect(test_db_url)
        try:
            with verify_conn.cursor() as cur:
                cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                assert cur.fetchone() is not None, "vector extension was not created"
                cur.execute(
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'recipe_embeddings' "
                    "AND indexname = 'ix_recipe_embeddings_embedding_hnsw'"
                )
                assert cur.fetchone() is not None, "HNSW index was not created"
        finally:
            verify_conn.close()
    finally:
        admin_conn = psycopg2.connect(TEST_POSTGRES_URL)
        admin_conn.autocommit = True
        try:
            with admin_conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                    (db_name,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            admin_conn.close()


@pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="TEST_POSTGRES_URL not set (needs `docker compose up pgvector`, see docker-compose.yml)",
)
def test_langgraph_checkpointer_tables_do_not_trip_the_drift_gate():
    """ROADMAP.md Phase 3, Step 3.2 regression test. Confirmed by hand while
    building this step: `PostgresSaver.setup()` creates `checkpoints`/
    `checkpoint_blobs`/`checkpoint_writes`/`checkpoint_migrations` directly
    (no Alembic migration involved -- see
    app.graph.builder._select_checkpointer's docstring for why they're
    deliberately NOT Alembic-managed). Without alembic/env.py's
    `include_object` exclusion for these table names, `alembic check`
    reflects them from the live DB, finds them absent from `Base.metadata`,
    and proposes dropping them as drift -- this test proves that doesn't
    happen, the same way the sibling test above proves it for 0002's
    `recipe_embeddings`.
    """
    import uuid

    import psycopg2
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg import Connection
    from psycopg.rows import dict_row

    db_name = f"macrochef_checkpointer_test_{uuid.uuid4().hex[:8]}"
    base_url = TEST_POSTGRES_URL.rsplit("/", 1)[0]
    test_db_url = f"{base_url}/{db_name}"

    admin_conn = psycopg2.connect(TEST_POSTGRES_URL)
    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        admin_conn.close()

    try:
        env = os.environ.copy()
        env["DATABASE_URL"] = test_db_url
        env.setdefault("EMBEDDING_PROVIDER", "hash")

        upgrade_result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
        )
        assert upgrade_result.returncode == 0, upgrade_result.stdout + upgrade_result.stderr

        # Mirrors app.graph.builder._select_checkpointer's Postgres branch
        # exactly -- creates the checkpoint tables via the upstream
        # package's own .setup(), entirely outside Alembic.
        pg_conn = Connection.connect(
            test_db_url, autocommit=True, prepare_threshold=0, row_factory=dict_row
        )
        try:
            PostgresSaver(pg_conn).setup()
        finally:
            pg_conn.close()

        check_result = subprocess.run(
            [sys.executable, "-m", "alembic", "check"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
        )
        assert check_result.returncode == 0, (
            "Schema drift gate flagged the LangGraph checkpointer's own tables -- "
            "alembic/env.py's include_object exclusion regressed.\n"
            f"{check_result.stdout}{check_result.stderr}"
        )
    finally:
        admin_conn = psycopg2.connect(TEST_POSTGRES_URL)
        admin_conn.autocommit = True
        try:
            with admin_conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                    (db_name,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            admin_conn.close()
