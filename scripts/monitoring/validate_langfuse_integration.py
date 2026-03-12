#!/usr/bin/env python3
"""
Langfuse Integration Validation Script (Phase 5)

Validates that Langfuse traces are properly created and contain expected token usage data.
This script is useful for:
- Post-deployment validation
- Debugging token tracking discrepancies
- E2E integration testing

Usage:
    python scripts/validate_langfuse_integration.py

Requirements:
    - Langfuse API credentials configured in .env
    - At least one LLM call made (to generate traces)

Related:
    - ADR-015: Token Tracking Architecture V2
    - Phase 2.1: RC4 Fix (Cache Hit Callbacks)

Known Limitations:
    - Cache hits won't appear in Langfuse traces (by design)
    - Langfuse has eventual consistency (may take 1-2 seconds for traces to appear)
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog
from dotenv import load_dotenv
from tabulate import tabulate

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logger = structlog.get_logger(__name__)


class LangfuseValidator:
    """Validates Langfuse integration and token tracking."""

    def __init__(self):
        """Initialize Langfuse client."""
        load_dotenv()

        self.public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        self.secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        self.host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

        if not self.public_key or not self.secret_key:
            raise ValueError(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set in .env"
            )

        self.api_url = f"{self.host}/api/public"
        self.client = httpx.AsyncClient(
            auth=(self.public_key, self.secret_key),
            timeout=30.0,
        )

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def get_recent_traces(
        self, limit: int = 10, hours: int = 24
    ) -> list[dict[str, Any]]:
        """
        Fetch recent Langfuse traces.

        Args:
            limit: Maximum number of traces to fetch
            hours: Look back window in hours

        Returns:
            List of trace objects
        """
        from_timestamp = datetime.utcnow() - timedelta(hours=hours)

        params = {
            "page": 1,
            "limit": limit,
            "fromTimestamp": from_timestamp.isoformat() + "Z",
        }

        try:
            response = await self.client.get(f"{self.api_url}/traces", params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except httpx.HTTPError as e:
            logger.error("langfuse_api_error", error=str(e), status=e.response.status_code if hasattr(e, 'response') else None)
            return []

    async def get_trace_details(self, trace_id: str) -> dict[str, Any] | None:
        """
        Fetch detailed trace information including observations (LLM calls).

        Args:
            trace_id: Langfuse trace ID

        Returns:
            Trace object with observations, or None if not found
        """
        try:
            response = await self.client.get(f"{self.api_url}/traces/{trace_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(
                "langfuse_trace_details_error",
                trace_id=trace_id,
                error=str(e),
                status=e.response.status_code if hasattr(e, 'response') else None,
            )
            return None

    def extract_token_usage(self, trace: dict[str, Any]) -> dict[str, int]:
        """
        Extract token usage from trace observations.

        Args:
            trace: Trace object with observations

        Returns:
            Dict with total_input_tokens, total_output_tokens, observation_count
        """
        total_input = 0
        total_output = 0
        observation_count = 0

        for obs in trace.get("observations", []):
            # Langfuse observations include usage field for LLM calls
            usage = obs.get("usage")
            if usage:
                total_input += usage.get("input", 0) or usage.get("promptTokens", 0)
                total_output += usage.get("output", 0) or usage.get("completionTokens", 0)
                observation_count += 1

        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "observation_count": observation_count,
        }

    async def validate_trace(self, trace_id: str) -> dict[str, Any]:
        """
        Validate a single trace for token tracking.

        Args:
            trace_id: Langfuse trace ID

        Returns:
            Validation result dict
        """
        trace = await self.get_trace_details(trace_id)
        if not trace:
            return {
                "trace_id": trace_id,
                "status": "error",
                "error": "Trace not found",
            }

        usage = self.extract_token_usage(trace)

        return {
            "trace_id": trace_id,
            "status": "success",
            "name": trace.get("name", "Unknown"),
            "timestamp": trace.get("timestamp"),
            "input_tokens": usage["total_input_tokens"],
            "output_tokens": usage["total_output_tokens"],
            "total_tokens": usage["total_input_tokens"] + usage["total_output_tokens"],
            "observation_count": usage["observation_count"],
            "has_usage_data": usage["total_input_tokens"] > 0 or usage["total_output_tokens"] > 0,
        }

    async def run_validation(self, limit: int = 10, hours: int = 24) -> dict[str, Any]:
        """
        Run full validation suite.

        Args:
            limit: Number of recent traces to validate
            hours: Look back window

        Returns:
            Validation summary
        """
        print(f"\n{'='*80}")
        print(f"Langfuse Integration Validation (Phase 5)")
        print(f"{'='*80}\n")

        print(f"Configuration:")
        print(f"  - Langfuse Host: {self.host}")
        print(f"  - Public Key: {self.public_key[:10]}...")
        print(f"  - Look-back: {hours} hours")
        print(f"  - Limit: {limit} traces\n")

        # Step 1: Fetch recent traces
        print("Step 1: Fetching recent traces...")
        traces = await self.get_recent_traces(limit=limit, hours=hours)
        print(f"  ✅ Found {len(traces)} traces\n")

        if not traces:
            print("⚠️  No traces found. Make sure:")
            print("  1. Langfuse credentials are correct")
            print("  2. At least one LLM call was made in the last 24 hours")
            print("  3. Langfuse instrumentation is enabled in the API\n")
            return {"status": "no_traces", "traces": []}

        # Step 2: Validate each trace
        print("Step 2: Validating traces...")
        validations = []
        for trace in traces:
            trace_id = trace.get("id")
            result = await self.validate_trace(trace_id)
            validations.append(result)

        # Step 3: Generate summary
        print("\n" + "="*80)
        print("Validation Results")
        print("="*80 + "\n")

        # Table view
        table_data = []
        for v in validations:
            if v["status"] == "success":
                table_data.append([
                    v["trace_id"][:16] + "...",
                    v["name"][:30],
                    v["input_tokens"],
                    v["output_tokens"],
                    v["total_tokens"],
                    v["observation_count"],
                    "✅" if v["has_usage_data"] else "❌",
                ])

        if table_data:
            print(tabulate(
                table_data,
                headers=[
                    "Trace ID",
                    "Name",
                    "Input",
                    "Output",
                    "Total",
                    "Obs",
                    "Usage OK",
                ],
                tablefmt="grid",
            ))
        else:
            print("⚠️  No successful validations")

        # Summary statistics
        print("\n" + "="*80)
        print("Summary Statistics")
        print("="*80 + "\n")

        total_traces = len(validations)
        successful = [v for v in validations if v["status"] == "success"]
        with_usage = [v for v in successful if v["has_usage_data"]]
        without_usage = [v for v in successful if not v["has_usage_data"]]
        errors = [v for v in validations if v["status"] == "error"]

        total_input_tokens = sum(v.get("input_tokens", 0) for v in successful)
        total_output_tokens = sum(v.get("output_tokens", 0) for v in successful)
        total_tokens = total_input_tokens + total_output_tokens

        print(f"Total Traces Checked: {total_traces}")
        print(f"  ✅ Successful: {len(successful)}")
        print(f"  ❌ Errors: {len(errors)}")
        print()
        print(f"Token Tracking:")
        print(f"  ✅ Traces with usage data: {len(with_usage)} ({len(with_usage)/total_traces*100:.1f}%)")
        print(f"  ⚠️  Traces without usage data: {len(without_usage)} ({len(without_usage)/total_traces*100:.1f}%)")
        print()
        print(f"Total Tokens:")
        print(f"  - Input: {total_input_tokens:,}")
        print(f"  - Output: {total_output_tokens:,}")
        print(f"  - Total: {total_tokens:,}")
        print()

        # Warnings for traces without usage
        if without_usage:
            print("⚠️  WARNING: Some traces missing token usage data")
            print("   Possible reasons:")
            print("   1. Cache hits (by design - see ADR-015)")
            print("   2. Streaming responses (tokens tracked separately)")
            print("   3. Error responses (no LLM call made)")
            print("   4. Langfuse eventual consistency delay")
            print()

        # Known limitation message
        print("="*80)
        print("Known Limitations (Phase 2.1 - RC4 Fix)")
        print("="*80 + "\n")
        print("⚠️  Cache hits don't appear in Langfuse traces (by design)")
        print("   - Reason: Direct Prometheus increment avoids callback replay")
        print("   - Impact: Langfuse token count < Prometheus token count")
        print("   - Solution: Use Prometheus as authoritative source for cache hit metrics")
        print()
        print("✅ This is expected behavior and documented in ADR-015")
        print()

        return {
            "status": "complete",
            "total_traces": total_traces,
            "successful": len(successful),
            "errors": len(errors),
            "with_usage": len(with_usage),
            "without_usage": len(without_usage),
            "total_tokens": total_tokens,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "traces": validations,
        }


async def main():
    """Main entry point."""
    validator = LangfuseValidator()

    try:
        result = await validator.run_validation(limit=10, hours=24)

        # Exit code based on results
        if result["status"] == "no_traces":
            sys.exit(2)  # Warning: no traces found
        elif result.get("errors", 0) > 0:
            sys.exit(1)  # Error: some validations failed
        else:
            sys.exit(0)  # Success

    except Exception as e:
        logger.error("validation_failed", error=str(e), exc_info=True)
        print(f"\n❌ Validation failed: {e}\n")
        sys.exit(1)

    finally:
        await validator.close()


if __name__ == "__main__":
    asyncio.run(main())
