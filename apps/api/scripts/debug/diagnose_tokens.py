#!/usr/bin/env python
"""
Diagnostic script to verify token tracking.

Usage:
    python scripts/diagnose_tokens.py

This script checks:
1. The latest token_summary records in DB
2. The latest messages with their metadata
3. Token values to identify if the issue is at the:
   - Tracking level (callbacks not called)
   - Persistence level (DB not updated)
   - Retrieval level (get_aggregated_summary_from_db fails)
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta

from sqlalchemy import desc, select

from src.domains.chat.models import Message, TokenSummary
from src.infrastructure.database import get_db_context


async def main():
    """Main diagnostic."""
    print("=== TOKEN TRACKING DIAGNOSTIC ===\n")

    async with get_db_context() as db:
        # 1. Latest TokenSummary (10 most recent)
        print("Latest TokenSummary in DB (10 most recent):")
        print("-" * 100)

        result = await db.execute(
            select(TokenSummary).order_by(desc(TokenSummary.updated_at)).limit(10)
        )
        summaries = result.scalars().all()

        if not summaries:
            print("NO TokenSummary in DB! Tracking is not working.")
        else:
            for summary in summaries:
                print(f"Run ID: {summary.run_id}")
                print(f"  User ID: {summary.user_id}")
                print(f"  Conversation ID: {summary.conversation_id}")
                print(f"  Tokens IN: {summary.total_prompt_tokens}")
                print(f"  Tokens OUT: {summary.total_completion_tokens}")
                print(f"  Tokens CACHE: {summary.total_cached_tokens}")
                print(f"  Cost EUR: {summary.total_cost_eur}")
                print(f"  Updated: {summary.updated_at}")
                print()

        # 2. Latest messages (5 most recent)
        print("\nLatest Messages in DB (5 most recent):")
        print("-" * 100)

        result = await db.execute(select(Message).order_by(desc(Message.created_at)).limit(5))
        messages = result.scalars().all()

        for msg in messages:
            print(f"Message ID: {msg.id}")
            print(f"  Role: {msg.role}")
            print(f"  Content preview: {msg.content[:100]}...")
            print(f"  Created: {msg.created_at}")
            print()

        # 3. Global statistics
        print("\nGlobal statistics:")
        print("-" * 100)

        result = await db.execute(select(TokenSummary))
        all_summaries = result.scalars().all()

        total_tokens_in = sum(s.total_prompt_tokens for s in all_summaries)
        total_tokens_out = sum(s.total_completion_tokens for s in all_summaries)
        total_cost = sum(float(s.total_cost_eur) for s in all_summaries)

        print(f"Total TokenSummary records: {len(all_summaries)}")
        print(f"Total tokens IN: {total_tokens_in}")
        print(f"Total tokens OUT: {total_tokens_out}")
        print(f"Total cost EUR: {total_cost:.6f}")

        # 4. Recent records (last 24h)
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_summaries = [s for s in all_summaries if s.updated_at > yesterday]

        print(f"\nTokenSummary records (last 24h): {len(recent_summaries)}")

        if len(recent_summaries) == 0:
            print("WARNING: No records created in the last 24h!")
            print("   -> This suggests tracking is no longer working recently.")

        # 5. Check if any tokens are at 0
        zero_summaries = [
            s
            for s in all_summaries
            if s.total_prompt_tokens == 0 and s.total_completion_tokens == 0
        ]
        if zero_summaries:
            print(f"\nWARNING: {len(zero_summaries)} TokenSummary with tokens at 0 (possible errors)")

    print("\n=== END OF DIAGNOSTIC ===")


if __name__ == "__main__":
    asyncio.run(main())
