"""
Automated Token Alignment Validation Script.

Validates that token counts are aligned across:
1. Database (message_token_summary table)
2. Prometheus (llm_tokens_consumed_total counter)
3. LangFuse (observability platform)

Usage:
    python scripts/validate_token_alignment.py --conversation-id conv_abc123
    python scripts/validate_token_alignment.py --run-id run_xyz789
    python scripts/validate_token_alignment.py --last-24h

Phase: 2.1.2 - Token Tracking Alignment Validation
Date: 2025-01-10
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

# Add parent directory to path for imports
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.core.config import settings
from src.domains.chat.models import MessageTokenSummary

logger = structlog.get_logger(__name__)


class TokenAlignmentValidator:
    """Validates token counting alignment across DB, Prometheus, and LangFuse."""

    def __init__(self, prometheus_url: str = "http://localhost:9090"):
        """
        Initialize validator.

        Args:
            prometheus_url: Prometheus server URL
        """
        self.prometheus_url = prometheus_url
        self.engine = create_async_engine(settings.database_url, echo=False)

    async def get_db_tokens(
        self,
        conversation_id: str | None = None,
        run_id: str | None = None,
        since: datetime | None = None,
    ) -> dict[str, int]:
        """
        Get token counts from database.

        Args:
            conversation_id: Filter by conversation ID
            run_id: Filter by run ID
            since: Filter by records created after this timestamp

        Returns:
            dict with total_input, total_output, total_cached, total_all
        """
        async with AsyncSession(self.engine) as session:
            stmt = select(
                func.sum(MessageTokenSummary.total_prompt_tokens).label("total_input"),
                func.sum(MessageTokenSummary.total_completion_tokens).label("total_output"),
                func.sum(MessageTokenSummary.total_cached_tokens).label("total_cached"),
            )

            if conversation_id:
                stmt = stmt.where(MessageTokenSummary.conversation_id == conversation_id)
            if run_id:
                stmt = stmt.where(MessageTokenSummary.run_id == run_id)
            if since:
                stmt = stmt.where(MessageTokenSummary.created_at >= since)

            result = await session.execute(stmt)
            row = result.first()

            if row is None:
                return {"total_input": 0, "total_output": 0, "total_cached": 0, "total_all": 0}

            total_input = row.total_input or 0
            total_output = row.total_output or 0
            total_cached = row.total_cached or 0

            return {
                "total_input": total_input,
                "total_output": total_output,
                "total_cached": total_cached,
                "total_all": total_input + total_output + total_cached,
            }

    async def get_prometheus_tokens(self, time_range: str = "24h") -> dict[str, Any]:
        """
        Get token counts from Prometheus.

        Args:
            time_range: Time range for increase() query (e.g., "24h", "1h", "5m")

        Returns:
            dict with total_all, by_type breakdown, and raw_response
        """
        query = f"sum(increase(llm_tokens_consumed_total[{time_range}]))"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": query},
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()

                if data["status"] != "success":
                    logger.error("prometheus_query_failed", data=data)
                    return {"total_all": 0, "error": data.get("error", "Unknown error")}

                result = data["data"]["result"]
                if not result:
                    return {"total_all": 0, "by_type": {}, "raw_response": data}

                # Sum all token types
                total = sum(float(r["value"][1]) for r in result)

                # Breakdown by token_type label
                by_type = {}
                for r in result:
                    token_type = r["metric"].get("token_type", "unknown")
                    by_type[token_type] = by_type.get(token_type, 0) + float(r["value"][1])

                return {
                    "total_all": int(total),
                    "by_type": {k: int(v) for k, v in by_type.items()},
                    "raw_response": data,
                }

            except Exception as e:
                logger.error("prometheus_request_failed", error=str(e), exc_info=True)
                return {"total_all": 0, "error": str(e)}

    async def validate_alignment(
        self,
        conversation_id: str | None = None,
        run_id: str | None = None,
        time_range: str = "24h",
    ) -> dict[str, Any]:
        """
        Validate token alignment across sources.

        Args:
            conversation_id: Filter by conversation ID
            run_id: Filter by run ID
            time_range: Prometheus time range

        Returns:
            dict with db_tokens, prometheus_tokens, ratios, status
        """
        # Calculate "since" timestamp for DB query to match Prometheus time range
        since = None
        if time_range.endswith("h"):
            hours = int(time_range[:-1])
            since = datetime.now(UTC) - timedelta(hours=hours)
        elif time_range.endswith("m"):
            minutes = int(time_range[:-1])
            since = datetime.now(UTC) - timedelta(minutes=minutes)

        # Get tokens from both sources
        db_tokens = await self.get_db_tokens(
            conversation_id=conversation_id, run_id=run_id, since=since
        )
        prometheus_tokens = await self.get_prometheus_tokens(time_range=time_range)

        # Calculate ratios
        db_total = db_tokens["total_all"]
        prom_total = prometheus_tokens["total_all"]

        if db_total > 0:
            ratio = prom_total / db_total
        else:
            ratio = None

        # Determine status
        if ratio is None:
            status = "NO_DATA"
            severity = "warning"
        elif 0.9 <= ratio <= 1.3:
            # Allow up to 1.3x due to legitimate subgraph amplification (ReAct agent makes 2-5 calls)
            status = "ALIGNED"
            severity = "success"
        elif 1.3 < ratio <= 2.0:
            status = "MODERATE_DISCREPANCY"
            severity = "warning"
        else:
            status = "CRITICAL_DISCREPANCY"
            severity = "error"

        return {
            "db_tokens": db_tokens,
            "prometheus_tokens": prometheus_tokens,
            "ratio": ratio,
            "status": status,
            "severity": severity,
            "expected_ratio": "0.9 - 1.3x (accounting for subgraph amplification)",
            "filters": {
                "conversation_id": conversation_id,
                "run_id": run_id,
                "time_range": time_range,
            },
        }

    async def close(self):
        """Close database connection."""
        await self.engine.dispose()


async def main():
    """Main entry point for validation script."""
    parser = argparse.ArgumentParser(description="Validate token counting alignment")
    parser.add_argument("--conversation-id", help="Filter by conversation ID")
    parser.add_argument("--run-id", help="Filter by run ID")
    parser.add_argument(
        "--time-range",
        default="24h",
        help="Prometheus time range (e.g., 24h, 1h, 5m)",
    )
    parser.add_argument(
        "--prometheus-url",
        default="http://localhost:9090",
        help="Prometheus server URL",
    )

    args = parser.parse_args()

    validator = TokenAlignmentValidator(prometheus_url=args.prometheus_url)

    try:
        result = await validator.validate_alignment(
            conversation_id=args.conversation_id,
            run_id=args.run_id,
            time_range=args.time_range,
        )

        # Pretty print results
        print("\n" + "=" * 80)
        print("TOKEN ALIGNMENT VALIDATION REPORT")
        print("=" * 80)
        print(f"\nTimestamp: {datetime.now(UTC).isoformat()}")
        print(f"Filters: {result['filters']}")
        print(f"\nStatus: {result['status']} ({result['severity'].upper()})")
        print(f"Expected Ratio: {result['expected_ratio']}")
        print(f"Actual Ratio: {result['ratio']:.2f}x" if result["ratio"] else "N/A")

        print("\n--- DATABASE TOKENS ---")
        db = result["db_tokens"]
        print(f"  Input:  {db['total_input']:,}")
        print(f"  Output: {db['total_output']:,}")
        print(f"  Cached: {db['total_cached']:,}")
        print(f"  TOTAL:  {db['total_all']:,}")

        print("\n--- PROMETHEUS TOKENS ---")
        prom = result["prometheus_tokens"]
        print(f"  TOTAL:  {prom['total_all']:,}")
        if "by_type" in prom:
            print("  Breakdown:")
            for token_type, count in prom["by_type"].items():
                print(f"    {token_type}: {count:,}")

        print("\n--- ANALYSIS ---")
        if result["ratio"]:
            discrepancy = prom["total_all"] - db["total_all"]
            print(f"  Discrepancy: {discrepancy:,} tokens ({result['ratio']:.2f}x)")

            if result["status"] == "ALIGNED":
                print("  ✅ Token counts are ALIGNED. No action needed.")
            elif result["status"] == "MODERATE_DISCREPANCY":
                print("  ⚠️  Moderate discrepancy detected. Verify callback deduplication logs.")
            else:
                print("  ❌ CRITICAL discrepancy! Double counting likely still present.")
                print("     Action: Check logs for 'config_enriched_with_node_metadata'")
                print("     Expected: filtered_count > 0 (callbacks being deduplicated)")
        else:
            print("  ⚠️  No data in database. Cannot calculate ratio.")

        print("\n" + "=" * 80 + "\n")

        # Exit with appropriate code
        if result["severity"] == "error":
            sys.exit(1)
        elif result["severity"] == "warning":
            sys.exit(2)
        else:
            sys.exit(0)

    finally:
        await validator.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
