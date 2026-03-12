#!/usr/bin/env python3
"""
SSE Streaming Performance Benchmark Runner

Wrapper script that handles authentication and runs benchmark.

Usage:
    # With existing user credentials
    python scripts/run_benchmark.py --email user@example.com --password yourpassword

    # With test user (creates if needed)
    python scripts/run_benchmark.py --test-user

    # Custom API URL and test password
    python scripts/run_benchmark.py --test-user --api-url http://localhost:8000 --test-password MySecurePass123!

Environment Variables:
    BENCHMARK_TEST_PASSWORD: Password for test user (default: BenchmarkPassword123!)
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import httpx
from benchmark_sse_streaming import (
    TEST_MESSAGES,
    benchmark_single_message,
)


async def create_test_user(api_url: str, password: str) -> dict:
    """Create a test user for benchmarking."""
    async with httpx.AsyncClient() as client:
        # Create user
        response = await client.post(
            f"{api_url}/api/v1/auth/register",
            json={
                "email": "benchmark@example.com",
                "password": password,
                "full_name": "Benchmark User",
            },
        )

        if response.status_code == 201:
            print("✅ Test user created")
            return response.json()
        if response.status_code == 400 and (
            "already exists" in response.text.lower()
            or "already registered" in response.text.lower()
        ):
            print("ℹ️  Test user already exists")
            return {"email": "benchmark@example.com"}
        print(f"❌ Failed to create test user: {response.status_code}")
        print(response.text)
        sys.exit(1)


async def login_user(api_url: str, email: str, password: str) -> tuple[str, str]:
    """Login and get session_id + user_id."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/api/v1/auth/login",
            json={"email": email, "password": password},
        )

        if response.status_code != 200:
            print(f"❌ Login failed: {response.status_code}")
            print(response.text)
            sys.exit(1)

        # Extract session_id from cookie (cookie name is 'lia_session')
        session_id = None
        for cookie in response.cookies.jar:
            if cookie.name in ("session_id", "lia_session"):
                session_id = cookie.value
                break

        if not session_id:
            print("❌ No session_id in response cookies")
            print(f"Available cookies: {[c.name for c in response.cookies.jar]}")
            sys.exit(1)

        user_data = response.json()
        user_id = user_data["user"]["id"]

        print(f"✅ Logged in as {email}")
        print(f"   User ID: {user_id}")
        print(f"   Session ID: {session_id[:20]}...")

        return session_id, user_id


async def run_benchmarks_with_auth(api_url: str, session_id: str, user_id: str) -> None:
    """Run benchmarks with authenticated session."""
    print("\n" + "=" * 80)
    print("SSE STREAMING PERFORMANCE BENCHMARK")
    print("=" * 80)
    print(f"\nAPI Endpoint: {api_url}/api/v1/agents/chat/stream")
    print(f"Test Messages: {len(TEST_MESSAGES)}")
    print(f"User ID: {user_id}")
    print("\n" + "-" * 80)

    all_metrics = []

    for i, message in enumerate(TEST_MESSAGES, 1):
        print(f"\n[{i}/{len(TEST_MESSAGES)}] Testing: {message[:50]}...")

        metrics = await benchmark_single_message(message, session_id, user_id)

        if metrics.error:
            print(f"  ❌ ERROR: {metrics.error}")
        else:
            if metrics.router_latency_ms:
                print(f"  ✅ Router Latency: {metrics.router_latency_ms:.0f}ms")
            else:
                print("  ⚠️  No router latency")
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

        avg_router_latency = (
            sum(m.router_latency_ms for m in successful_metrics if m.router_latency_ms)
            / len([m for m in successful_metrics if m.router_latency_ms])
            if any(m.router_latency_ms for m in successful_metrics)
            else 0
        )
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

        ttft_pct = ttft_sla_met / len(successful_metrics) * 100
        tokens_pct = tokens_sla_met / len(successful_metrics) * 100
        print(f"TTFT < 1000ms: {ttft_sla_met}/{len(successful_metrics)} " f"({ttft_pct:.1f}%)")
        print(
            f"Tokens/sec > 20: {tokens_sla_met}/{len(successful_metrics)} " f"({tokens_pct:.1f}%)"
        )

        # Overall verdict
        print("\n" + "=" * 80)
        if ttft_sla_met == len(successful_metrics) and tokens_sla_met == len(successful_metrics):
            print("✅ VERDICT: ALL SLA TARGETS MET")
        elif ttft_sla_met >= len(successful_metrics) * 0.8:
            print("⚠️  VERDICT: MOST SLA TARGETS MET (>80%)")
        else:
            print("❌ VERDICT: SLA TARGETS NOT MET")

    else:
        print("\n❌ All requests failed!")

    print("\n" + "=" * 80)
    print("BENCHMARK COMPLETE")
    print("=" * 80 + "\n")


async def main():
    """Main entry point for benchmark runner."""
    parser = argparse.ArgumentParser(description="Run SSE streaming performance benchmarks")
    parser.add_argument(
        "--api-url",
        default=os.getenv("API_URL", "http://localhost:8000"),
        help="API base URL (default: $API_URL or http://localhost:8000)",
    )
    parser.add_argument("--email", help="User email for authentication")
    parser.add_argument("--password", help="User password for authentication")
    parser.add_argument(
        "--test-user",
        action="store_true",
        help="Use test user (creates if needed)",
    )
    parser.add_argument(
        "--test-password",
        help="Password for test user (overrides BENCHMARK_TEST_PASSWORD)",
    )

    args = parser.parse_args()

    # Determine credentials
    if args.test_user:
        print("📊 Using test user for benchmarks")
        # Get password from args, env, or default
        test_password = (
            args.test_password or os.getenv("BENCHMARK_TEST_PASSWORD") or "BenchmarkPassword123!"
        )
        await create_test_user(args.api_url, test_password)
        email = "benchmark@example.com"
        password = test_password
    elif args.email and args.password:
        email = args.email
        password = args.password
    else:
        print("❌ Error: Provide either --test-user or --email/--password")
        sys.exit(1)

    # Authenticate
    session_id, user_id = await login_user(args.api_url, email, password)

    # Run benchmarks
    await run_benchmarks_with_auth(args.api_url, session_id, user_id)


if __name__ == "__main__":
    asyncio.run(main())
