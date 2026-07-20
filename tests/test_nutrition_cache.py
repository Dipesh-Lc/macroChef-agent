"""A3 prep: `FdcCache` batches disk writes instead of rewriting the entire
on-disk JSON cache on every `set_payload` call (see its module comment for
the `_AUTO_FLUSH_ENTRIES` rationale). These tests cover the batching
contract directly; `test_usda_client.py`/`test_grounding_job.py` cover the
two flush-on-exit-path integrations (rate-limit error, `run_grounding`)."""

from app.services.nutrition_cache import _AUTO_FLUSH_ENTRIES, FdcCache


def _payload(n: int) -> dict:
    return {"foods": [{"fdcId": n}]}


def test_no_disk_write_before_batch_threshold(tmp_path) -> None:
    cache_path = tmp_path / "cache.json"
    cache = FdcCache(cache_path)

    cache.set_payload("widget", ["Branded"], 5, _payload(1))
    assert not cache_path.exists()

    # Still under threshold, still nothing on disk.
    for i in range(2, _AUTO_FLUSH_ENTRIES):
        cache.set_payload(f"widget{i}", ["Branded"], 5, _payload(i))
    assert not cache_path.exists()

    # The in-memory read path still works even though nothing is flushed.
    assert cache.get_payload("widget", ["Branded"], 5) == _payload(1)


def test_auto_flush_at_threshold_entries(tmp_path) -> None:
    cache_path = tmp_path / "cache.json"
    cache = FdcCache(cache_path)

    for i in range(_AUTO_FLUSH_ENTRIES - 1):
        cache.set_payload(f"widget{i}", ["Branded"], 5, _payload(i))
    assert not cache_path.exists()

    # The Nth entry (== _AUTO_FLUSH_ENTRIES) triggers the auto-flush.
    cache.set_payload("widget-last", ["Branded"], 5, _payload(999))
    assert cache_path.exists()

    # Everything written so far -- not just the entry that triggered the
    # flush -- must be durably on disk, readable by a fresh instance.
    reloaded = FdcCache(cache_path)
    assert reloaded.get_payload("widget0", ["Branded"], 5) == _payload(0)
    assert reloaded.get_payload("widget-last", ["Branded"], 5) == _payload(999)


def test_explicit_flush_persists_and_is_idempotent(tmp_path) -> None:
    cache_path = tmp_path / "cache.json"
    cache = FdcCache(cache_path)

    cache.set_payload("widget", ["Branded"], 5, _payload(1))
    assert not cache_path.exists()

    cache.flush()
    assert cache_path.exists()

    reloaded = FdcCache(cache_path)
    assert reloaded.get_payload("widget", ["Branded"], 5) == _payload(1)

    # Idempotent: calling flush() again with nothing new pending is a safe
    # no-op, not a crash and not a spurious rewrite that would lose data.
    cache.flush()
    assert cache_path.exists()
    reloaded_again = FdcCache(cache_path)
    assert reloaded_again.get_payload("widget", ["Branded"], 5) == _payload(1)


def test_flush_on_a_cache_with_no_writes_is_a_safe_no_op(tmp_path) -> None:
    cache_path = tmp_path / "cache.json"
    cache = FdcCache(cache_path)

    cache.flush()

    assert not cache_path.exists()
