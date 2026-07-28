"""Before/after wall-clock benchmark for ROADMAP.md Phase 2, Step 2.2.

`app.services.grounding_job.run_grounding` (sequential) vs `run_grounding_
async` (fanned out, bounded by a semaphore) over the SAME fixed-size subset
of the real recipe corpus.

This does NOT hit the live USDA FDC API -- there is no `FDC_API_KEY`
available in this environment (and Step 2.2's task spec explicitly says not
to spend real API quota running a multi-thousand-recipe corpus twice just
for a benchmark). Instead, both the sync and async fake clients below sleep
for `--latency-ms` per simulated request, standing in for a real FDC round
trip -- everything else (matching logic, aggregation, report assembly) is
the real, unmodified code path. This isolates exactly the thing Step 2.2
changed (how many of those simulated network calls are in flight at once),
without needing a real API key or spending any quota.

Usage:
    python scripts/benchmark_async_grounding.py [--recipes N] [--latency-ms N] [--concurrency N]
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag.loaders import load_corpus  # noqa: E402
from app.schemas.nutrition import FoodMacros, FoodMatch  # noqa: E402
from app.services.grounding_job import run_grounding, run_grounding_async  # noqa: E402

_FAKE_MATCH = FoodMatch(
    fdc_id=1,
    description="Simulated match",
    data_type="SR Legacy",
    macros=FoodMacros(calories=100, protein_g=10, carbs_g=10, fat_g=5, fiber_g=1),
    query="simulated",
)


class _SleepingSyncClient:
    """Stands in for UsdaClient's sync path: every `search_food` call sleeps
    `latency_seconds` (simulating an FDC round trip) before returning a
    canned match. No `_cache`/diagnostics attributes needed -- `run_grounding`
    reads those defensively via `getattr(..., None)`.

    Also implements `search_food_with_reason` with NO sleep -- `run_
    grounding`'s terminal-outcome classification pass
    (`_terminal_outcome_for_ingredient`) prefers this method when present
    (see its docstring) and, on the real `UsdaClient`, it's a cache hit
    against the payload the main grounding pass already fetched (no new
    network I/O). Without this, the fallback path would call `search_food`
    a SECOND time per ingredient and double-count simulated latency that
    the real client never actually pays twice.
    """

    def __init__(self, latency_seconds: float):
        self._latency_seconds = latency_seconds
        self.calls = 0

    def search_food(self, name: str, *, preparation: str | None = None) -> FoodMatch | None:
        self.calls += 1
        time.sleep(self._latency_seconds)
        return _FAKE_MATCH

    def search_food_with_reason(
        self, name: str, *, preparation: str | None = None, record_diagnostics: bool = True
    ) -> tuple[FoodMatch | None, str]:
        return _FAKE_MATCH, "grounded"


class _SleepingAsyncClient:
    """Async sibling of `_SleepingSyncClient` -- every `search_food_async`
    call awaits `asyncio.sleep(latency_seconds)` instead of blocking.

    Also implements a zero-latency sync `search_food` -- `run_grounding_
    async`'s post-fan-out terminal-outcome classification pass
    (`_terminal_outcome_for_ingredient`) is deliberately still a plain
    sequential loop (see its docstring: it's a cache-hit re-classification
    against the same client, never a new network call on the real
    `UsdaClient`), so this fake client needs a fast, no-sleep sync method
    for that pass too, matching what the real cache-backed client actually
    costs there -- effectively free, not a second round of simulated
    network latency.
    """

    def __init__(self, latency_seconds: float):
        self._latency_seconds = latency_seconds
        self.calls = 0

    async def search_food_async(
        self, name: str, *, preparation: str | None = None
    ) -> FoodMatch | None:
        self.calls += 1
        await asyncio.sleep(self._latency_seconds)
        return _FAKE_MATCH

    def search_food(self, name: str, *, preparation: str | None = None) -> FoodMatch | None:
        return _FAKE_MATCH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recipes", type=int, default=150, help="Subset size (fixed, deterministic)."
    )
    parser.add_argument(
        "--latency-ms", type=float, default=150.0,
        help="Simulated per-request USDA FDC round-trip latency, in milliseconds.",
    )
    parser.add_argument(
        "--concurrency", type=int, default=4, help="Async fan-out bound (LLM_MAX_CONCURRENCY)."
    )
    args = parser.parse_args()

    latency_seconds = args.latency_ms / 1000.0

    full_corpus = load_corpus()
    subset = sorted(full_corpus, key=lambda r: r.recipe_id)[: args.recipes]
    total_ingredients = sum(len(r.ingredients) for r in subset)

    print(f"Subset: {len(subset)} recipes, {total_ingredients} ingredient occurrences.")
    print(f"Simulated per-request latency: {args.latency_ms:.0f} ms.")
    print(f"Async fan-out concurrency bound: {args.concurrency}.\n")

    sync_client = _SleepingSyncClient(latency_seconds)
    sync_start = time.perf_counter()
    run_grounding(
        client=sync_client,
        sidecar_path=Path(ROOT) / "data" / "cache" / "_benchmark_sync_sidecar.jsonl",
        corpus=subset,
        seeds=[],
    )
    sync_elapsed = time.perf_counter() - sync_start

    async_client = _SleepingAsyncClient(latency_seconds)

    async def _run_async() -> float:
        start = time.perf_counter()
        await run_grounding_async(
            client=async_client,
            sidecar_path=Path(ROOT) / "data" / "cache" / "_benchmark_async_sidecar.jsonl",
            corpus=subset,
            seeds=[],
            max_concurrency=args.concurrency,
        )
        return time.perf_counter() - start

    async_elapsed = asyncio.run(_run_async())

    speedup = sync_elapsed / async_elapsed if async_elapsed > 0 else float("inf")

    print(
        f"run_grounding        (sequential): {sync_elapsed:8.2f}s  "
        f"({sync_client.calls} simulated USDA calls)"
    )
    print(
        f"run_grounding_async  (fanned out):  {async_elapsed:8.2f}s  "
        f"({async_client.calls} simulated USDA calls)"
    )
    print(f"Speedup: {speedup:.2f}x")


if __name__ == "__main__":
    main()
