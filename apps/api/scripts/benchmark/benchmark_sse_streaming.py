#!/usr/bin/env python3
"""
SSE Streaming Performance Benchmark

Measures performance metrics for LangGraph agent SSE streaming:
- Time to First Token (TTFT)
- Time to Last Token (TTLT)
- Tokens per second
- Total response time
- Router decision latency

Usage:
    python scripts/benchmark_sse_streaming.py
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger()

# Test configuration
API_BASE_URL = os.getenv("API_URL", "http://localhost:8000")
CHAT_ENDPOINT = f"{API_BASE_URL}/api/v1/agents/chat/stream"

# Test messages with varying complexity
TEST_MESSAGES = [
    "Bonjour",  # Simple greeting
    "Quel temps fait-il aujourd'hui?",  # Simple question
    "Explique-moi comment fonctionne la photosynthèse",  # Medium complexity
    "Rédige un email professionnel pour demander des congés",  # Complex task
]


@dataclass
class StreamingMetrics:
    """Performance metrics for a single SSE stream."""

    message: str
    time_to_first_token_ms: float
    time_to_last_token_ms: float
    total_tokens: int
    router_latency_ms: float | None
    tokens_per_second: float
    total_response_time_ms: float
    error: str | None = None


async def benchmark_single_message(message: str, session_id: str, user_id: str) -> StreamingMetrics:
    """
    Benchmark SSE streaming for a single message.

    Args:
        message: User message to send
        session_id: Session ID for authentication
        user_id: User ID for request

    Returns:
        StreamingMetrics with performance data
    """
    start_time = time.time()
    time_to_first_token = None
    time_to_router_decision = None
    token_count = 0
    last_token_time = None

    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                CHAT_ENDPOINT,
                json={
                    "message": message,
                    "user_id": user_id,
                    "session_id": session_id,
                },
                headers={
                    "Cookie": f"lia_session={session_id}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    return StreamingMetrics(
                        message=message,
                        time_to_first_token_ms=0,
                        time_to_last_token_ms=0,
                        total_tokens=0,
                        router_latency_ms=None,
                        tokens_per_second=0,
                        total_response_time_ms=(time.time() - start_time) * 1000,
                        error=f"HTTP {response.status_code}: {error_text}",
                    )

                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue  # Skip heartbeats and empty lines

                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        try:
                            data = json.loads(data_str)
                            chunk_type = data.get("type")

                            # Track router decision time
                            if chunk_type == "router_decision" and time_to_router_decision is None:
                                time_to_router_decision = (time.time() - start_time) * 1000

                            # Track first token
                            elif chunk_type == "token":
                                if time_to_first_token is None:
                                    time_to_first_token = (time.time() - start_time) * 1000

                                token_count += 1
                                last_token_time = time.time()

                            # Stream completed
                            elif chunk_type == "done":
                                break

                        except json.JSONDecodeError as e:
                            logger.warning("json_decode_error", line=line, error=str(e))

        # Calculate metrics
        total_time_ms = (time.time() - start_time) * 1000
        time_to_last_token_ms = (last_token_time - start_time) * 1000 if last_token_time else 0

        # Tokens per second (excluding router latency)
        generation_time_s = (time_to_last_token_ms - (time_to_router_decision or 0)) / 1000
        tokens_per_second = token_count / generation_time_s if generation_time_s > 0 else 0

        return StreamingMetrics(
            message=message,
            time_to_first_token_ms=time_to_first_token or 0,
            time_to_last_token_ms=time_to_last_token_ms,
            total_tokens=token_count,
            router_latency_ms=time_to_router_decision,
            tokens_per_second=tokens_per_second,
            total_response_time_ms=total_time_ms,
        )

    except Exception as e:
        return StreamingMetrics(
            message=message,
            time_to_first_token_ms=0,
            time_to_last_token_ms=0,
            total_tokens=0,
            router_latency_ms=None,
            tokens_per_second=0,
            total_response_time_ms=(time.time() - start_time) * 1000,
            error=str(e),
        )


async def run_benchmarks():
    """Run benchmarks for all test messages."""
    # TODO: Replace with actual session_id and user_id from authenticated session
    # For now, using placeholder values (will fail auth without real session)
    session_id = "test-session-id"
    user_id = "test-user-id"

    print("\n" + "=" * 80)
    print("SSE STREAMING PERFORMANCE BENCHMARK")
    print("=" * 80)
    print(f"\nAPI Endpoint: {CHAT_ENDPOINT}")
    print(f"Test Messages: {len(TEST_MESSAGES)}")
    print("\n" + "-" * 80)

    all_metrics = []

    for i, message in enumerate(TEST_MESSAGES, 1):
        print(f"\n[{i}/{len(TEST_MESSAGES)}] Testing: {message[:50]}...")

        metrics = await benchmark_single_message(message, session_id, user_id)

        if metrics.error:
            print(f"  ❌ ERROR: {metrics.error}")
        else:
            print(f"  ✅ Router Latency: {metrics.router_latency_ms:.0f}ms")
            print(f"  ✅ Time to First Token: {metrics.time_to_first_token_ms:.0f}ms")
            print(f"  ✅ Time to Last Token: {metrics.time_to_last_token_ms:.0f}ms")
            print(f"  ✅ Total Tokens: {metrics.total_tokens}")
            print(f"  ✅ Tokens/sec: {metrics.tokens_per_second:.1f}")
            print(f"  ✅ Total Time: {metrics.total_response_time_ms:.0f}ms")

        all_metrics.append(metrics)

        # Small delay between requests
        await asyncio.sleep(1)

    # Calculate aggregates (excluding errors)
    successful_metrics = [m for m in all_metrics if m.error is None]

    if successful_metrics:
        print("\n" + "=" * 80)
        print("AGGREGATE RESULTS")
        print("=" * 80)

        avg_router_latency = sum(
            m.router_latency_ms for m in successful_metrics if m.router_latency_ms
        ) / len([m for m in successful_metrics if m.router_latency_ms])
        avg_ttft = sum(m.time_to_first_token_ms for m in successful_metrics) / len(
            successful_metrics
        )
        avg_ttlt = sum(m.time_to_last_token_ms for m in successful_metrics) / len(
            successful_metrics
        )
        avg_tokens = sum(m.total_tokens for m in successful_metrics) / len(successful_metrics)
        avg_tokens_per_sec = sum(m.tokens_per_second for m in successful_metrics) / len(
            successful_metrics
        )
        avg_total_time = sum(m.total_response_time_ms for m in successful_metrics) / len(
            successful_metrics
        )

        print(f"\nSuccessful Requests: {len(successful_metrics)}/{len(all_metrics)}")
        print(f"Average Router Latency: {avg_router_latency:.0f}ms")
        print(f"Average Time to First Token: {avg_ttft:.0f}ms")
        print(f"Average Time to Last Token: {avg_ttlt:.0f}ms")
        print(f"Average Tokens: {avg_tokens:.0f}")
        print(f"Average Tokens/sec: {avg_tokens_per_sec:.1f}")
        print(f"Average Total Time: {avg_total_time:.0f}ms")

        # SLA Analysis
        print("\n" + "-" * 80)
        print("SLA ANALYSIS (Target: TTFT < 1000ms, Tokens/sec > 20)")
        print("-" * 80)

        ttft_sla_met = sum(1 for m in successful_metrics if m.time_to_first_token_ms < 1000)
        tokens_sla_met = sum(1 for m in successful_metrics if m.tokens_per_second > 20)

        print(
            f"TTFT < 1000ms: {ttft_sla_met}/{len(successful_metrics)} ({ttft_sla_met / len(successful_metrics) * 100:.1f}%)"
        )
        print(
            f"Tokens/sec > 20: {tokens_sla_met}/{len(successful_metrics)} ({tokens_sla_met / len(successful_metrics) * 100:.1f}%)"
        )

    else:
        print("\n❌ All requests failed!")

    print("\n" + "=" * 80)
    print("BENCHMARK COMPLETE")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(run_benchmarks())
