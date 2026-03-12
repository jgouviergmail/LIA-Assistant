"""
Pattern Learner Training Script.

Sends a list of test queries to the API multiple times to train the pattern learner.
Each successful execution records the pattern for future optimization.

Usage:
    # IMPORTANT: You need a valid session cookie from your browser!
    # 1. Open your app in browser and login
    # 2. Open DevTools > Application > Cookies > copy 'lia_session' value
    # 3. Pass it to this script with --session

    # File mode with session authentication
    python scripts/train_pattern_learner.py --file queries.txt --session "YOUR_SESSION_COOKIE" --repeat 20

    # Interactive mode
    python scripts/train_pattern_learner.py --interactive --session "YOUR_SESSION_COOKIE"

    # Inline mode
    python scripts/train_pattern_learner.py -q "recherche contacts" -q "liste emails" --session "YOUR_SESSION"

    # With custom API settings
    python scripts/train_pattern_learner.py --base-url http://localhost:8000 --session "YOUR_SESSION"

Requirements:
    pip install httpx

Created: 2026-01-12
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_BASE_URL = os.getenv("API_URL", "http://localhost:8000") + "/api/v1"
DEFAULT_REPEAT = 20
DEFAULT_DELAY_BETWEEN_QUERIES = 1.0  # seconds
DEFAULT_TIMEOUT = 120.0  # seconds


# ============================================================================
# Training Runner
# ============================================================================


class PatternLearnerTrainer:
    """Trainer for pattern learner via API requests."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        session_cookie: str | None = None,
        repeat: int = DEFAULT_REPEAT,
        delay: float = DEFAULT_DELAY_BETWEEN_QUERIES,
        timeout: float = DEFAULT_TIMEOUT,
        verbose: bool = True,
        insecure: bool = False,
    ):
        self.base_url = base_url
        self.session_cookie = session_cookie
        self.repeat = repeat
        self.delay = delay
        self.timeout = timeout
        self.verbose = verbose
        self.insecure = insecure
        self.user_id: str | None = None  # Will be fetched from /users/me

        # Stats
        self.stats = {
            "total_queries": 0,
            "successful": 0,
            "failed": 0,
            "errors": {},
        }

    async def _fetch_user_id(self, client: httpx.AsyncClient) -> bool:
        """Fetch user_id from session by calling /users/me endpoint."""
        if not self.session_cookie:
            print("❌ No session cookie provided. Use --session to pass your session cookie.")
            print("   How to get it:")
            print("   1. Open your app in browser and login")
            print("   2. Open DevTools (F12) > Application > Cookies")
            print("   3. Copy the 'lia_session' cookie value")
            return False

        try:
            response = await client.get(
                f"{self.base_url}/auth/me",
                cookies={"lia_session": self.session_cookie},
            )

            if response.status_code == 401:
                print(
                    "❌ Session expired or invalid. Please login again and get a new session cookie."
                )
                return False

            if response.status_code != 200:
                print(f"❌ Failed to fetch user info: HTTP {response.status_code}")
                return False

            data = response.json()
            self.user_id = data.get("id")

            if not self.user_id:
                print("❌ Could not extract user_id from /users/me response")
                return False

            print(
                f"✅ Authenticated as: {data.get('email', 'unknown')} (id: {self.user_id[:8]}...)"
            )
            return True

        except Exception as e:
            print(f"❌ Failed to authenticate: {e}")
            return False

    async def train(self, queries: list[str]) -> dict:
        """
        Run training with given queries.

        Args:
            queries: List of user queries to send

        Returns:
            Training statistics
        """
        total = len(queries) * self.repeat
        print("🎯 Pattern Learner Training")
        print(f"   Queries: {len(queries)}")
        print(f"   Repeat: {self.repeat}x")
        print(f"   Total requests: {total}")
        print(f"   Base URL: {self.base_url}")
        print()

        start_time = time.time()

        async with httpx.AsyncClient(timeout=self.timeout, verify=not self.insecure) as client:
            # Step 1: Authenticate and get user_id
            if not await self._fetch_user_id(client):
                self.stats["errors"]["AuthenticationFailed"] = 1
                return self.stats

            print()
            for iteration in range(self.repeat):
                print(f"📍 Iteration {iteration + 1}/{self.repeat}")

                for idx, query in enumerate(queries):
                    success = await self._send_query(client, query, iteration, idx)
                    self.stats["total_queries"] += 1

                    if success:
                        self.stats["successful"] += 1
                    else:
                        self.stats["failed"] += 1

                    # Progress indicator
                    progress = self.stats["total_queries"] / total * 100
                    print(
                        f"   Progress: {progress:.1f}% ({self.stats['successful']}✓ {self.stats['failed']}✗)"
                    )

                    # Delay between queries
                    if self.delay > 0:
                        await asyncio.sleep(self.delay)

                print()

        elapsed = time.time() - start_time
        self.stats["elapsed_seconds"] = elapsed
        self.stats["queries_per_second"] = (
            self.stats["total_queries"] / elapsed if elapsed > 0 else 0
        )

        self._print_summary()
        return self.stats

    async def _send_query(
        self,
        client: httpx.AsyncClient,
        query: str,
        iteration: int,
        query_idx: int,
    ) -> bool:
        """Send a single query to the API."""
        # CRITICAL: Use UNIQUE session_id for EACH request to simulate new conversation
        # This ensures pattern learning records each execution independently
        # (like user clicking "delete conversation" before each test)
        import uuid

        unique_id = uuid.uuid4().hex[:8]
        session_id = f"pattern_train_{unique_id}"

        payload = {
            "message": query,
            "user_id": self.user_id,  # Use authenticated user_id
            "session_id": session_id,
        }

        headers = {"Content-Type": "application/json"}
        cookies = {"lia_session": self.session_cookie} if self.session_cookie else {}

        try:
            # Use streaming endpoint to ensure full execution
            async with client.stream(
                "POST",
                f"{self.base_url}/agents/chat/stream",
                json=payload,
                headers=headers,
                cookies=cookies,
            ) as response:
                if response.status_code != 200:
                    error_key = f"HTTP_{response.status_code}"
                    self.stats["errors"][error_key] = self.stats["errors"].get(error_key, 0) + 1
                    if self.verbose:
                        print(f"   ⚠️  [{query[:30]}...] HTTP {response.status_code}")
                    return False

                # Consume the stream to ensure full execution
                chunks_received = 0
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        chunks_received += 1
                        try:
                            chunk = json.loads(line[6:])
                            # Check for completion
                            if chunk.get("type") in ["done", "end", "error"]:
                                break
                        except json.JSONDecodeError:
                            pass

                if self.verbose:
                    print(f"   ✅ [{query[:40]}...] ({chunks_received} chunks)")

                return True

        except httpx.TimeoutException:
            self.stats["errors"]["Timeout"] = self.stats["errors"].get("Timeout", 0) + 1
            if self.verbose:
                print(f"   ⏱️  [{query[:30]}...] Timeout")
            return False

        except httpx.ConnectError:
            self.stats["errors"]["ConnectError"] = self.stats["errors"].get("ConnectError", 0) + 1
            if self.verbose:
                print(f"   🔌 [{query[:30]}...] Connection failed")
            return False

        except Exception as e:
            error_type = type(e).__name__
            self.stats["errors"][error_type] = self.stats["errors"].get(error_type, 0) + 1
            if self.verbose:
                print(f"   ❌ [{query[:30]}...] {error_type}: {e}")
            return False

    def _print_summary(self):
        """Print training summary."""
        print("=" * 60)
        print("📊 Training Summary")
        print("=" * 60)
        print(f"   Total queries sent: {self.stats['total_queries']}")
        print(
            f"   Successful: {self.stats['successful']} ({self.stats['successful']/self.stats['total_queries']*100:.1f}%)"
        )
        print(
            f"   Failed: {self.stats['failed']} ({self.stats['failed']/self.stats['total_queries']*100:.1f}%)"
        )
        print(f"   Duration: {self.stats['elapsed_seconds']:.1f}s")
        print(f"   Throughput: {self.stats['queries_per_second']:.2f} q/s")

        if self.stats["errors"]:
            print()
            print("   Errors by type:")
            for error_type, count in sorted(self.stats["errors"].items(), key=lambda x: -x[1]):
                print(f"     - {error_type}: {count}")

        print()
        print("✨ Run 'task patterns:list' to see learned patterns")


# ============================================================================
# CLI
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Train pattern learner by sending queries to API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # IMPORTANT: Get your session cookie first!
  # 1. Open app in browser, login
  # 2. DevTools (F12) > Application > Cookies > copy 'lia_session'

  # Interactive mode
  python scripts/train_pattern_learner.py --interactive --session "YOUR_COOKIE"

  # From file (one query per line)
  python scripts/train_pattern_learner.py --file queries.txt --session "YOUR_COOKIE" --repeat 20

  # Inline queries
  python scripts/train_pattern_learner.py -q "recherche contacts" --session "YOUR_COOKIE" --repeat 10

  # Using environment variable (recommended)
  export LIA_SESSION="your_cookie_value"
  python scripts/train_pattern_learner.py --file queries.txt --repeat 20
        """,
    )

    # Input modes
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "-q",
        "--queries",
        nargs="+",
        help="Queries to send (can specify multiple)",
    )
    input_group.add_argument(
        "-f",
        "--file",
        type=str,
        help="File containing queries (one per line)",
    )
    input_group.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Interactive mode - enter queries manually",
    )

    # Authentication (REQUIRED)
    parser.add_argument(
        "-s",
        "--session",
        type=str,
        help="Session cookie value (lia_session). Can also use LIA_SESSION env var.",
    )

    # Training options
    parser.add_argument(
        "-r",
        "--repeat",
        type=int,
        default=DEFAULT_REPEAT,
        help=f"Number of times to repeat each query (default: {DEFAULT_REPEAT})",
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=float,
        default=DEFAULT_DELAY_BETWEEN_QUERIES,
        help=f"Delay between queries in seconds (default: {DEFAULT_DELAY_BETWEEN_QUERIES})",
    )

    # API options
    parser.add_argument(
        "--base-url",
        type=str,
        default=DEFAULT_BASE_URL,
        help=f"API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )

    # SSL options
    parser.add_argument(
        "-k",
        "--insecure",
        action="store_true",
        default=False,
        help="Disable SSL certificate verification (for self-signed certs)",
    )

    # Output options
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=True,
        help="Verbose output (default: True)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output file for results (JSON)",
    )

    args = parser.parse_args()

    # Collect queries
    queries = []

    if args.queries:
        queries = args.queries
    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"❌ File not found: {args.file}")
            sys.exit(1)
        queries = [
            line.strip()
            for line in file_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
    elif args.interactive:
        print("🎯 Interactive Mode - Enter queries (empty line to finish):")
        while True:
            try:
                query = input("> ").strip()
                if not query:
                    break
                queries.append(query)
            except EOFError:
                break

    if not queries:
        print("❌ No queries provided")
        sys.exit(1)

    # Get session cookie from args or environment
    import os

    session_cookie = args.session or os.environ.get("LIA_SESSION")

    if not session_cookie:
        print("❌ No session cookie provided!")
        print()
        print("   How to get your session cookie:")
        print("   1. Open your app in browser and login")
        print("   2. Open DevTools (F12) > Application > Cookies")
        print("   3. Copy the 'lia_session' cookie value")
        print()
        print("   Then either:")
        print("   - Pass it with: --session 'YOUR_COOKIE_VALUE'")
        print("   - Or set env var: export LIA_SESSION='YOUR_COOKIE_VALUE'")
        sys.exit(1)

    print(f"\n📝 Queries to train ({len(queries)}):")
    for i, q in enumerate(queries, 1):
        print(f"   {i}. {q}")
    print()

    # Run training
    trainer = PatternLearnerTrainer(
        base_url=args.base_url,
        session_cookie=session_cookie,
        repeat=args.repeat,
        delay=args.delay,
        timeout=args.timeout,
        verbose=args.verbose,
        insecure=args.insecure,
    )

    stats = asyncio.run(trainer.train(queries))

    # Save results if requested
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
        print(f"📁 Results saved to: {args.output}")


if __name__ == "__main__":
    main()
