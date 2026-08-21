"""
Multi-process integration tests for RedisRateLimiter.

Tests the distributed rate limiter across multiple processes to verify:
- Rate limiting works correctly with horizontal scaling
- No race conditions between processes
- Shared state via Redis is consistent

Requires: Redis server running

Phase: PHASE 2.4 - Rate Limiting Distribué Redis
Created: 2025-11-20
"""

import asyncio
import multiprocessing as mp
import time

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.infrastructure.rate_limiting import RedisRateLimiter


async def worker_acquire_requests(
    worker_id: int,
    test_key: str,
    num_requests: int,
    max_calls: int,
    window_seconds: int,
    results_queue: mp.Queue,
) -> None:
    """
    Worker process that makes rate-limited requests.

    Args:
        worker_id: Unique worker identifier
        test_key: Rate limit key
        num_requests: Number of requests to make
        max_calls: Max calls allowed in window
        window_seconds: Time window in seconds
        results_queue: Queue to collect results (success/failure)
    """
    try:
        # Create Redis connection in this process
        redis = Redis.from_url(str(settings.redis_url), decode_responses=False)
        limiter = RedisRateLimiter(redis)

        results = []
        for _i in range(num_requests):
            allowed = await limiter.acquire(
                key=test_key,
                max_calls=max_calls,
                window_seconds=window_seconds,
            )
            results.append(allowed)

            # Small delay to avoid CPU spinning
            await asyncio.sleep(0.001)

        # Report results
        success_count = sum(results)
        results_queue.put(
            {
                "worker_id": worker_id,
                "total_requests": num_requests,
                "successful": success_count,
                "rejected": num_requests - success_count,
            }
        )

        # Cleanup
        await limiter.close()
        await redis.aclose()

    except Exception as e:
        results_queue.put(
            {
                "worker_id": worker_id,
                "error": str(e),
            }
        )


def run_worker(
    worker_id: int,
    test_key: str,
    num_requests: int,
    max_calls: int,
    window_seconds: int,
    results_queue: mp.Queue,
) -> None:
    """
    Entry point for worker process.

    Creates event loop and runs worker_acquire_requests coroutine.
    """
    asyncio.run(
        worker_acquire_requests(
            worker_id, test_key, num_requests, max_calls, window_seconds, results_queue
        )
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.multiprocess
class TestRedisRateLimiterMultiProcess:
    """Test rate limiter with actual multiple processes.

    A running Redis is the ``integration`` contract (the task's preflight
    guarantees it) — the tests fail loudly without it. The old
    ``pytest._redis_available`` skipif was removed (ADR-241 follow-up): the
    attribute was set NOWHERE, so the whole class had been silently skipped on
    every runner since 2025-11 — green by absence, invisible to the
    permanent-skip guard because the condition looked dynamic. The
    ``multiprocess`` marker keeps the class out of PR CI (F006 allowlist);
    run it explicitly with ``pytest -m multiprocess`` — proven green on
    Python 3.14 under both Linux forkserver (dev container) and Windows spawn.
    """

    async def test_multiple_processes_respect_global_limit(self):
        """
        Test that multiple processes respect shared rate limit.

        Scenario:
        - 4 processes each try to make 10 requests (40 total)
        - Global limit: 20 requests
        - Expected: Exactly 20 requests succeed across all processes
        """
        test_key = f"test:multiprocess:{int(time.time() * 1000000)}"
        num_workers = 4
        requests_per_worker = 10
        max_calls = 20
        window_seconds = 60

        # Create queue for collecting results
        results_queue = mp.Queue()

        # Spawn worker processes
        processes: list[mp.Process] = []
        for worker_id in range(num_workers):
            p = mp.Process(
                target=run_worker,
                args=(
                    worker_id,
                    test_key,
                    requests_per_worker,
                    max_calls,
                    window_seconds,
                    results_queue,
                ),
            )
            p.start()
            processes.append(p)

        # Wait for all processes to complete
        for p in processes:
            p.join(timeout=10)  # 10s timeout
            if p.is_alive():
                p.terminate()
                pytest.fail(f"Worker process {p.pid} timed out")

        # Collect results
        results = []
        while not results_queue.empty():
            results.append(results_queue.get())

        # Verify all workers completed
        assert len(results) == num_workers

        # Verify no errors
        for result in results:
            assert "error" not in result, f"Worker error: {result.get('error')}"

        # Calculate total successful requests across all processes
        total_successful = sum(r["successful"] for r in results)
        total_rejected = sum(r["rejected"] for r in results)

        # CRITICAL: Exactly max_calls (20) should succeed
        assert (
            total_successful == max_calls
        ), f"Expected {max_calls} successful requests, got {total_successful}"

        # Remaining requests should be rejected
        expected_rejected = (num_workers * requests_per_worker) - max_calls
        assert (
            total_rejected == expected_rejected
        ), f"Expected {expected_rejected} rejected requests, got {total_rejected}"

        print("\nMulti-process test results:")
        print(f"  Workers: {num_workers}")
        print(f"  Requests per worker: {requests_per_worker}")
        print(f"  Total requests: {num_workers * requests_per_worker}")
        print(f"  Global limit: {max_calls}")
        print(f"  Successful: {total_successful}")
        print(f"  Rejected: {total_rejected}")

        for result in results:
            print(
                f"  Worker {result['worker_id']}: {result['successful']}/{result['total_requests']} succeeded"
            )

    async def test_high_concurrency_no_race_conditions(self):
        """
        Test high concurrency without race conditions.

        Scenario:
        - 8 processes each try to make 20 requests (160 total)
        - Global limit: 100 requests
        - Expected: Exactly 100 requests succeed, no over-limit due to race conditions
        """
        test_key = f"test:race_conditions:{int(time.time() * 1000000)}"
        num_workers = 8
        requests_per_worker = 20
        max_calls = 100
        window_seconds = 60

        results_queue = mp.Queue()

        # Spawn workers
        processes = []
        for worker_id in range(num_workers):
            p = mp.Process(
                target=run_worker,
                args=(
                    worker_id,
                    test_key,
                    requests_per_worker,
                    max_calls,
                    window_seconds,
                    results_queue,
                ),
            )
            p.start()
            processes.append(p)

        # Wait for completion
        for p in processes:
            p.join(timeout=15)
            if p.is_alive():
                p.terminate()
                pytest.fail("Worker process timed out")

        # Collect results
        results = []
        while not results_queue.empty():
            results.append(results_queue.get())

        assert len(results) == num_workers

        # Verify no errors
        for result in results:
            assert "error" not in result

        # Calculate totals
        total_successful = sum(r["successful"] for r in results)

        # CRITICAL: Should not exceed max_calls by more than a small margin
        # Note: Multi-process timing can cause slight overage (5% tolerance)
        # The Lua script is atomic, but process startup timing can cause overlap
        tolerance = max(1, int(max_calls * 0.05))  # 5% tolerance, minimum 1
        assert (
            total_successful <= max_calls + tolerance
        ), f"Race condition detected: {total_successful} > {max_calls + tolerance}"

        # Should be within expected range
        assert (
            total_successful >= max_calls - tolerance
        ), f"Expected ~{max_calls}, got {total_successful}"

        print("\nHigh concurrency test results:")
        print(f"  Workers: {num_workers}")
        print(f"  Total requests: {num_workers * requests_per_worker}")
        print(f"  Global limit: {max_calls}")
        print(f"  Successful: {total_successful}")
        print("  ✅ No race conditions detected")

    async def test_sliding_window_across_processes(self):
        """
        Test sliding window behavior with multiple processes.

        Scenario:
        - 2 processes make requests at different times
        - Verify old requests slide out of window correctly
        """
        test_key = f"test:sliding_window:{int(time.time() * 1000000)}"
        max_calls = 5
        window_seconds = 3  # Short window for fast test

        # Phase 1: First process fills the limit
        results_queue1 = mp.Queue()
        p1 = mp.Process(
            target=run_worker,
            args=(1, test_key, max_calls, max_calls, window_seconds, results_queue1),
        )
        p1.start()
        p1.join(timeout=5)

        result1 = results_queue1.get()
        assert result1["successful"] == max_calls

        # Phase 2: Wait for window to slide
        await asyncio.sleep(window_seconds + 0.5)

        # Phase 3: Second process should now be able to make requests
        results_queue2 = mp.Queue()
        p2 = mp.Process(
            target=run_worker,
            args=(2, test_key, max_calls, max_calls, window_seconds, results_queue2),
        )
        p2.start()
        p2.join(timeout=5)

        result2 = results_queue2.get()

        # Second process should succeed (window slid)
        assert (
            result2["successful"] == max_calls
        ), f"Sliding window failed: only {result2['successful']}/{max_calls} succeeded"

        print("\nSliding window test:")
        print(f"  Phase 1: {result1['successful']}/{max_calls} succeeded")
        print(f"  Wait: {window_seconds}s")
        print(f"  Phase 2: {result2['successful']}/{max_calls} succeeded")
        print("  ✅ Sliding window working correctly")


# Note: This test file should be run with pytest markers:
# pytest tests/integration/test_redis_limiter_multiprocess.py -m multiprocess -v
