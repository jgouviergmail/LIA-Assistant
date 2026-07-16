"""Context store cleanup: correctness (all items) + machine-independent speedup.

`ToolContextManager.cleanup_session_contexts` deletes every tool-context entry
for a user+session on conversation reset. This suite pins two properties:

1. **Correctness (audit F028 / F019)** — cleanup deletes *all* items even when
   there are more than `BaseStore.asearch`'s default page (`limit=10`). The
   previous single unpaginated `asearch()` call silently orphaned a heavy
   user's excess context after a reset; the class was skipped with a false
   "works correctly in production" note. It now pages through every item.
2. **Speedup (F028)** — the parallel (`asyncio.gather`) deletion is faster than
   sequential deletion. The old test asserted absolute wall-clock budgets
   (`duration_ms < 150`), which are flaky under CI load. We instead measure
   BOTH strategies on the SAME machine and assert a *relative* speedup ratio —
   scheduler/CPU noise cancels out, so the assertion is stable everywhere.
"""

import asyncio
import time

import pytest
from langgraph.store.memory import InMemoryStore

from src.domains.agents.context.manager import ToolContextManager

# Per-delete simulated network latency; large enough that parallelism dominates
# scheduler noise, small enough to keep the test sub-second.
_DELETE_LATENCY_MS = 8.0


class MockStore(InMemoryStore):
    """InMemoryStore with a simulated per-delete network latency."""

    def __init__(self, delete_latency_ms: float = _DELETE_LATENCY_MS) -> None:
        super().__init__()
        self.delete_latency_ms = delete_latency_ms
        self.delete_count = 0

    async def adelete(self, namespace: tuple[str, ...], key: str) -> None:
        await asyncio.sleep(self.delete_latency_ms / 1000.0)
        self.delete_count += 1
        await super().adelete(namespace, key)


async def _populate(
    store: InMemoryStore, user_id: str, session_id: str, domains: int, keys: int
) -> int:
    total = 0
    for d in range(domains):
        namespace = (user_id, session_id, "context", f"domain_{d}")
        for k in range(keys):
            await store.aput(namespace, f"key_{k}", {"test": "data"})
            total += 1
    return total


class TestContextCleanupCorrectness:
    """Cleanup must delete EVERY item, regardless of the search page limit."""

    @pytest.mark.parametrize("domains, keys", [(15, 2), (20, 10)])
    async def test_deletes_all_items_beyond_search_limit(self, domains: int, keys: int) -> None:
        """More than `asearch(limit=10)` items are all found and deleted."""
        store = InMemoryStore()
        user_id, session_id = "user", "session"
        expected = await _populate(store, user_id, session_id, domains, keys)
        assert expected > 10  # guards against a limit-sized false pass

        manager = ToolContextManager()
        result = await manager.cleanup_session_contexts(
            user_id=user_id, session_id=session_id, store=store
        )

        assert result["success"] is True
        assert result["total_items_deleted"] == expected
        assert result["domains_cleaned"] == domains
        remaining = await store.asearch((user_id, session_id, "context"), limit=10_000)
        assert remaining == []

    async def test_isolation_between_sessions(self) -> None:
        """Cleanup of one session leaves sibling sessions untouched."""
        store = InMemoryStore()
        user_id = "user"
        for session in ("keep", "delete"):
            await store.aput((user_id, session, "context", "contacts"), "list", {"x": 1})

        manager = ToolContextManager()
        result = await manager.cleanup_session_contexts(
            user_id=user_id, session_id="delete", store=store
        )

        assert result["total_items_deleted"] == 1
        assert await store.asearch((user_id, "delete", "context"), limit=100) == []
        assert len(await store.asearch((user_id, "keep", "context"), limit=100)) == 1

    async def test_empty_session_is_noop(self) -> None:
        """Cleanup of a session with no context reports zero without error."""
        store = InMemoryStore()
        manager = ToolContextManager()
        result = await manager.cleanup_session_contexts(
            user_id="user", session_id="empty", store=store
        )
        assert result["success"] is True
        assert result["total_items_deleted"] == 0
        assert result["domains_cleaned"] == 0


class TestContextCleanupSpeedup:
    """Parallel deletion beats sequential — measured relatively, not in absolute ms."""

    async def test_parallel_is_faster_than_sequential(self) -> None:
        """Same workload, same machine: gather() must beat a sequential loop."""
        user_id, session_id = "user", "session"
        domains, keys = 20, 5  # 100 deletes

        # Sequential reference: delete one at a time on an identical dataset.
        seq_store = MockStore()
        await _populate(seq_store, user_id, session_id, domains, keys)
        items = await seq_store.asearch((user_id, session_id, "context"), limit=10_000)
        seq_start = time.perf_counter()
        for item in items:
            await seq_store.adelete(item.namespace, item.key)
        sequential_s = time.perf_counter() - seq_start

        # Parallel: the production cleanup path (asyncio.gather).
        par_store = MockStore()
        await _populate(par_store, user_id, session_id, domains, keys)
        manager = ToolContextManager()
        par_start = time.perf_counter()
        result = await manager.cleanup_session_contexts(
            user_id=user_id, session_id=session_id, store=par_store
        )
        parallel_s = time.perf_counter() - par_start

        assert result["total_items_deleted"] == domains * keys
        # Relative assertion: parallel is at least 2× faster. With 100 deletes
        # of ~8 ms each, sequential ≈ 800 ms and parallel ≈ one latency + gather
        # overhead — the ratio is large and machine-noise-independent. A
        # conservative 2× floor never flakes yet still catches a regression to
        # sequential awaits.
        assert parallel_s * 2 < sequential_s, (
            f"parallel ({parallel_s * 1000:.0f} ms) not >=2x faster than "
            f"sequential ({sequential_s * 1000:.0f} ms) — gather() regressed?"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
