"""
Load Testing Script for HITL Streaming.

This script simulates realistic user load on HITL streaming endpoints to measure:
- TTFT (Time To First Token) under load
- Throughput (requests/sec)
- Error rates
- Latency percentiles (p50, p95, p99)
- Resource utilization (memory, CPU)

Usage:
    # Run with default settings (10 concurrent users, 100 requests)
    python scripts/load_test_hitl_streaming.py

    # Run with custom load profile
    python scripts/load_test_hitl_streaming.py --users 50 --requests 500 --duration 300

    # Run with authentication
    python scripts/load_test_hitl_streaming.py --api-key YOUR_API_KEY

    # Export results to JSON
    python scripts/load_test_hitl_streaming.py --output results.json

Requirements:
    pip install httpx asyncio aiohttp

Phase 4.3: HITL Streaming Load Testing
"""

import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

import httpx

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_BASE_URL = os.getenv("API_URL", "http://localhost:8000") + "/api/v1"
DEFAULT_CONCURRENT_USERS = 10
DEFAULT_TOTAL_REQUESTS = 100
DEFAULT_DURATION_SECONDS = None  # None = request-based, not time-based


# ============================================================================
# Load Testing Scenarios
# ============================================================================


class HITLStreamingLoadTester:
    """Load tester for HITL streaming endpoints."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        concurrent_users: int = DEFAULT_CONCURRENT_USERS,
        total_requests: int = DEFAULT_TOTAL_REQUESTS,
        duration_seconds: int | None = DEFAULT_DURATION_SECONDS,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.concurrent_users = concurrent_users
        self.total_requests = total_requests
        self.duration_seconds = duration_seconds

        # Metrics storage
        self.metrics = {
            "ttft_samples": [],  # Time to first token
            "total_duration_samples": [],  # Total request duration
            "token_count_samples": [],  # Tokens per request
            "errors": defaultdict(int),  # Error counts by type
            "status_codes": defaultdict(int),  # HTTP status codes
            "requests_completed": 0,
            "requests_failed": 0,
            "start_time": None,
            "end_time": None,
        }

    async def run_load_test(self) -> dict[str, Any]:
        """
        Run load test with configured parameters.

        Returns:
            dict: Test results with metrics and summary
        """
        print("🚀 Starting HITL Streaming Load Test")
        print(f"   Base URL: {self.base_url}")
        print(f"   Concurrent Users: {self.concurrent_users}")
        print(f"   Total Requests: {self.total_requests}")
        if self.duration_seconds:
            print(f"   Duration: {self.duration_seconds}s")
        print()

        self.metrics["start_time"] = time.time()

        # Create task pool
        tasks = []
        requests_per_user = self.total_requests // self.concurrent_users

        for user_id in range(self.concurrent_users):
            task = asyncio.create_task(self._simulate_user(user_id, requests_per_user))
            tasks.append(task)

        # Wait for all users to complete
        await asyncio.gather(*tasks, return_exceptions=True)

        self.metrics["end_time"] = time.time()

        # Calculate summary statistics
        summary = self._calculate_summary()

        return summary

    async def _simulate_user(self, user_id: int, num_requests: int):
        """
        Simulate a single user making multiple HITL streaming requests.

        Args:
            user_id: User identifier
            num_requests: Number of requests this user should make
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            for request_num in range(num_requests):
                try:
                    # Check duration limit
                    if self.duration_seconds:
                        elapsed = time.time() - self.metrics["start_time"]
                        if elapsed >= self.duration_seconds:
                            break

                    # Execute single request with HITL streaming
                    await self._execute_hitl_streaming_request(client, user_id, request_num)

                    # Small delay between requests (simulate realistic user behavior)
                    await asyncio.sleep(0.5)

                except Exception as e:
                    self.metrics["errors"][type(e).__name__] += 1
                    self.metrics["requests_failed"] += 1
                    print(f"❌ User {user_id} request {request_num} failed: {e}")

    async def _execute_hitl_streaming_request(
        self, client: httpx.AsyncClient, user_id: int, request_num: int
    ):
        """
        Execute a single HITL streaming request and measure metrics.

        Simulates:
        1. User sends message → HITL interrupt
        2. Stream receives: metadata → question tokens → complete
        3. Measure TTFT and total duration

        Args:
            client: HTTP client
            user_id: User identifier
            request_num: Request number
        """
        # Generate unique conversation session
        session_id = f"load_test_user_{user_id}_session_{request_num}"
        test_user_id = str(uuid.uuid4())

        # Prepare request payload
        payload = {
            "message": "Recherche jean",  # Trigger HITL (contacts search)
            "user_id": test_user_id,
            "session_id": session_id,
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Track timing
        request_start = time.time()
        first_token_time = None
        total_tokens = 0
        chunk_count = 0

        try:
            # Execute SSE streaming request
            async with client.stream(
                "POST",
                f"{self.base_url}/agents/chat/stream",
                json=payload,
                headers=headers,
            ) as response:
                self.metrics["status_codes"][response.status_code] += 1

                if response.status_code != 200:
                    self.metrics["requests_failed"] += 1
                    print(f"⚠️  User {user_id} request {request_num}: HTTP {response.status_code}")
                    return

                # Parse SSE stream
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        chunk_data = line[6:]  # Remove "data: " prefix
                        try:
                            chunk = json.loads(chunk_data)

                            # Track first token timing (TTFT)
                            if first_token_time is None and chunk.get("type") in [
                                "token",
                                "hitl_question_token",
                            ]:
                                first_token_time = time.time() - request_start
                                self.metrics["ttft_samples"].append(first_token_time)

                            # Count tokens
                            if chunk.get("type") in ["token", "hitl_question_token"]:
                                content = chunk.get("content", "")
                                total_tokens += len(content.split())
                                chunk_count += 1

                            # Check for completion
                            if chunk.get("type") in ["done", "hitl_interrupt_complete"]:
                                break

                        except json.JSONDecodeError:
                            pass  # Skip malformed chunks

            # Record metrics
            total_duration = time.time() - request_start
            self.metrics["total_duration_samples"].append(total_duration)
            self.metrics["token_count_samples"].append(total_tokens)
            self.metrics["requests_completed"] += 1

            # Log progress
            if (request_num + 1) % 10 == 0:
                print(
                    f"✅ User {user_id} completed {request_num + 1} requests "
                    f"(TTFT: {first_token_time:.3f}s, Tokens: {total_tokens})"
                )

        except httpx.TimeoutException:
            self.metrics["errors"]["TimeoutException"] += 1
            self.metrics["requests_failed"] += 1
            print(f"⏱️  User {user_id} request {request_num} timed out")

        except Exception as e:
            self.metrics["errors"][type(e).__name__] += 1
            self.metrics["requests_failed"] += 1
            print(f"❌ User {user_id} request {request_num} error: {e}")

    def _calculate_summary(self) -> dict[str, Any]:
        """Calculate summary statistics from collected metrics."""
        duration = self.metrics["end_time"] - self.metrics["start_time"]

        summary = {
            "test_config": {
                "base_url": self.base_url,
                "concurrent_users": self.concurrent_users,
                "total_requests": self.total_requests,
                "duration_seconds": self.duration_seconds,
            },
            "execution": {
                "actual_duration_seconds": round(duration, 2),
                "requests_completed": self.metrics["requests_completed"],
                "requests_failed": self.metrics["requests_failed"],
                "success_rate": (
                    self.metrics["requests_completed"]
                    / (self.metrics["requests_completed"] + self.metrics["requests_failed"])
                    * 100
                    if (self.metrics["requests_completed"] + self.metrics["requests_failed"]) > 0
                    else 0.0
                ),
                "throughput_rps": (
                    self.metrics["requests_completed"] / duration if duration > 0 else 0.0
                ),
            },
            "ttft_metrics": {},
            "duration_metrics": {},
            "token_metrics": {},
            "errors": dict(self.metrics["errors"]),
            "status_codes": dict(self.metrics["status_codes"]),
        }

        # TTFT statistics
        if self.metrics["ttft_samples"]:
            summary["ttft_metrics"] = {
                "min_ms": round(min(self.metrics["ttft_samples"]) * 1000, 2),
                "max_ms": round(max(self.metrics["ttft_samples"]) * 1000, 2),
                "mean_ms": round(statistics.mean(self.metrics["ttft_samples"]) * 1000, 2),
                "median_ms": round(statistics.median(self.metrics["ttft_samples"]) * 1000, 2),
                "p95_ms": round(self._percentile(self.metrics["ttft_samples"], 0.95) * 1000, 2),
                "p99_ms": round(self._percentile(self.metrics["ttft_samples"], 0.99) * 1000, 2),
                "samples": len(self.metrics["ttft_samples"]),
            }

        # Total duration statistics
        if self.metrics["total_duration_samples"]:
            summary["duration_metrics"] = {
                "min_ms": round(min(self.metrics["total_duration_samples"]) * 1000, 2),
                "max_ms": round(max(self.metrics["total_duration_samples"]) * 1000, 2),
                "mean_ms": round(statistics.mean(self.metrics["total_duration_samples"]) * 1000, 2),
                "median_ms": round(
                    statistics.median(self.metrics["total_duration_samples"]) * 1000, 2
                ),
                "p95_ms": round(
                    self._percentile(self.metrics["total_duration_samples"], 0.95) * 1000, 2
                ),
                "p99_ms": round(
                    self._percentile(self.metrics["total_duration_samples"], 0.99) * 1000, 2
                ),
            }

        # Token statistics
        if self.metrics["token_count_samples"]:
            summary["token_metrics"] = {
                "min_tokens": min(self.metrics["token_count_samples"]),
                "max_tokens": max(self.metrics["token_count_samples"]),
                "mean_tokens": round(statistics.mean(self.metrics["token_count_samples"]), 2),
                "total_tokens": sum(self.metrics["token_count_samples"]),
            }

        return summary

    @staticmethod
    def _percentile(data: list[float], percentile: float) -> float:
        """Calculate percentile value from data."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile)
        return sorted_data[min(index, len(sorted_data) - 1)]


# ============================================================================
# Result Reporting
# ============================================================================


def print_summary(summary: dict[str, Any]):
    """Print formatted summary to console."""
    print()
    print("=" * 80)
    print("📊 HITL STREAMING LOAD TEST RESULTS")
    print("=" * 80)
    print()

    # Test configuration
    print("🔧 Test Configuration:")
    for key, value in summary["test_config"].items():
        print(f"   {key}: {value}")
    print()

    # Execution summary
    print("⚡ Execution Summary:")
    exec_summary = summary["execution"]
    print(f"   Duration: {exec_summary['actual_duration_seconds']}s")
    print(f"   Requests Completed: {exec_summary['requests_completed']}")
    print(f"   Requests Failed: {exec_summary['requests_failed']}")
    print(f"   Success Rate: {exec_summary['success_rate']:.2f}%")
    print(f"   Throughput: {exec_summary['throughput_rps']:.2f} req/s")
    print()

    # TTFT metrics (critical for UX)
    if summary["ttft_metrics"]:
        print("🎯 Time To First Token (TTFT) - Critical UX Metric:")
        ttft = summary["ttft_metrics"]
        print(f"   Min: {ttft['min_ms']}ms")
        print(f"   Mean: {ttft['mean_ms']}ms")
        print(f"   Median: {ttft['median_ms']}ms")
        print(
            f"   P95: {ttft['p95_ms']}ms {'✅' if ttft['p95_ms'] < 300 else '⚠️ (target: <300ms)'}"
        )
        print(f"   P99: {ttft['p99_ms']}ms")
        print(f"   Max: {ttft['max_ms']}ms")
        print(f"   Samples: {ttft['samples']}")
        print()

    # Duration metrics
    if summary["duration_metrics"]:
        print("⏱️  Total Request Duration:")
        dur = summary["duration_metrics"]
        print(f"   Min: {dur['min_ms']}ms")
        print(f"   Mean: {dur['mean_ms']}ms")
        print(f"   Median: {dur['median_ms']}ms")
        print(f"   P95: {dur['p95_ms']}ms")
        print(f"   P99: {dur['p99_ms']}ms")
        print(f"   Max: {dur['max_ms']}ms")
        print()

    # Token metrics
    if summary["token_metrics"]:
        print("📝 Token Metrics:")
        tokens = summary["token_metrics"]
        print(f"   Total Tokens: {tokens['total_tokens']}")
        print(f"   Mean Tokens/Request: {tokens['mean_tokens']}")
        print(f"   Min: {tokens['min_tokens']}, Max: {tokens['max_tokens']}")
        print()

    # Errors
    if summary["errors"]:
        print("❌ Errors:")
        for error_type, count in summary["errors"].items():
            print(f"   {error_type}: {count}")
        print()

    # Status codes
    if summary["status_codes"]:
        print("📡 HTTP Status Codes:")
        for code, count in summary["status_codes"].items():
            print(f"   {code}: {count}")
        print()

    print("=" * 80)


def export_results(summary: dict[str, Any], output_file: str):
    """Export results to JSON file."""
    summary["timestamp"] = datetime.now().isoformat()

    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"📄 Results exported to: {output_file}")


# ============================================================================
# Main Entry Point
# ============================================================================


def main():
    """Main entry point for load testing script."""
    parser = argparse.ArgumentParser(description="Load testing script for HITL streaming endpoints")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of API (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--api-key",
        help="API key for authentication (optional)",
    )
    parser.add_argument(
        "--users",
        type=int,
        default=DEFAULT_CONCURRENT_USERS,
        help=f"Number of concurrent users (default: {DEFAULT_CONCURRENT_USERS})",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=DEFAULT_TOTAL_REQUESTS,
        help=f"Total number of requests (default: {DEFAULT_TOTAL_REQUESTS})",
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Duration in seconds (overrides --requests if set)",
    )
    parser.add_argument(
        "--output",
        help="Output file for JSON results (optional)",
    )

    args = parser.parse_args()

    # Create load tester
    tester = HITLStreamingLoadTester(
        base_url=args.base_url,
        api_key=args.api_key,
        concurrent_users=args.users,
        total_requests=args.requests,
        duration_seconds=args.duration,
    )

    # Run load test
    try:
        summary = asyncio.run(tester.run_load_test())

        # Print results
        print_summary(summary)

        # Export to file if requested
        if args.output:
            export_results(summary, args.output)

        # Exit with appropriate code based on success rate
        success_rate = summary["execution"]["success_rate"]
        if success_rate < 95.0:
            print(f"\n⚠️  WARNING: Success rate below 95% ({success_rate:.2f}%)")
            exit(1)
        else:
            print(f"\n✅ All tests passed (success rate: {success_rate:.2f}%)")
            exit(0)

    except KeyboardInterrupt:
        print("\n🛑 Load test interrupted by user")
        exit(130)
    except Exception as e:
        print(f"\n❌ Load test failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()
