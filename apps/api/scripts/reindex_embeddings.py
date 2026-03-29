"""
Reindex embeddings after E5 (384 dims) → OpenAI (1536 dims) migration.

Reindexes:
1. LangGraph store items (store → store_vectors via AsyncPostgresStore.aput)
2. User interest embeddings (user_interests.embedding)

Usage:
    DEV:  cd apps/api && python scripts/reindex_embeddings.py
    PROD: docker exec lia-api-prod python scripts/reindex_embeddings.py

Options:
    --dry-run       Preview changes without writing
    --batch-size N  Batch size for OpenAI API calls (default: 50)
    --skip-store    Skip LangGraph store reindexing
    --skip-interests Skip user_interests reindexing
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()  # Load .env before any src imports

# Import all SQLAlchemy models so relationships resolve correctly
from src.infrastructure.database.registry import import_all_models

import_all_models()


async def reindex_store(dry_run: bool, batch_size: int) -> dict[str, int]:
    """Reindex LangGraph store_vectors via AsyncPostgresStore.aput().

    Reads all items from the ``store`` table, then re-puts them through
    the store API so LangGraph auto-extracts text from configured fields
    and generates new 1536-dim embeddings.

    Args:
        dry_run: If True, preview without writing.
        batch_size: Not used for store (items re-put one by one).

    Returns:
        Stats dict with total, reindexed, errors counts.
    """
    from psycopg import AsyncConnection
    from psycopg.rows import dict_row

    from src.core.config import settings
    from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

    database_url_str = str(settings.database_url)
    psycopg_url = database_url_str.replace("postgresql+asyncpg://", "postgresql://")

    conn = await AsyncConnection.connect(
        psycopg_url, autocommit=True, prepare_threshold=0, row_factory=dict_row
    )

    embeddings = get_memory_embeddings()

    from langgraph.store.postgres import AsyncPostgresStore

    store = AsyncPostgresStore(
        conn=conn,
        index={
            "dims": settings.memory_embedding_dimensions,
            "embed": embeddings,
            "fields": ["content", "text", "trigger_topic", "memory"],
        },
    )
    await store.setup()

    # Read all items from store table
    rows = await conn.execute("SELECT prefix, key, value FROM store")
    items = await rows.fetchall()

    stats: dict[str, int] = {"total": len(items), "reindexed": 0, "errors": 0}
    print(f"[store] Found {stats['total']} items to reindex")

    for i, item in enumerate(items):
        prefix_str = item["prefix"]
        # LangGraph stores namespace as dot-separated string
        namespace = tuple(prefix_str.split(".")) if "." in prefix_str else (prefix_str,)
        key = item["key"]
        value = json.loads(item["value"]) if isinstance(item["value"], str) else item["value"]

        if dry_run:
            fields_present = [
                f for f in ["content", "text", "trigger_topic", "memory"] if f in value
            ]
            print(f"  [DRY-RUN] Would reindex ({prefix_str}, {key}) fields={fields_present}")
            stats["reindexed"] += 1
            continue

        try:
            await store.aput(namespace, key, value)
            stats["reindexed"] += 1
            if (i + 1) % 10 == 0:
                print(f"  [store] Progress: {i + 1}/{stats['total']}")
        except Exception as e:
            stats["errors"] += 1
            print(f"  [store] ERROR reindexing ({prefix_str}, {key}): {e}")

    await conn.close()
    return stats


async def reindex_interests(dry_run: bool, batch_size: int) -> dict[str, int]:
    """Reindex user_interests.embedding with OpenAI embeddings.

    Queries all interests with a topic, batches them for embedding,
    and updates the embedding column.

    Args:
        dry_run: If True, preview without writing.
        batch_size: Number of interests to embed per API call.

    Returns:
        Stats dict with total, reindexed, errors counts.
    """
    from sqlalchemy import select

    from src.domains.interests.models import UserInterest
    from src.infrastructure.database.session import AsyncSessionLocal
    from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

    embeddings = get_memory_embeddings()
    stats: dict[str, int] = {"total": 0, "reindexed": 0, "errors": 0}

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserInterest).where(UserInterest.topic.isnot(None)))
        interests = result.scalars().all()
        stats["total"] = len(interests)
        print(f"[interests] Found {stats['total']} interests to reindex")

        for i in range(0, len(interests), batch_size):
            batch = interests[i : i + batch_size]
            topics = [interest.topic for interest in batch]

            if dry_run:
                print(
                    f"  [DRY-RUN] Would embed batch {i // batch_size + 1} "
                    f"({len(topics)} topics)"
                )
                stats["reindexed"] += len(topics)
                continue

            try:
                vectors = embeddings.embed_documents(topics)
                for interest, vector in zip(batch, vectors, strict=True):
                    interest.embedding = vector
                    stats["reindexed"] += 1
                await session.commit()
                print(f"  [interests] Batch {i // batch_size + 1}: " f"{len(topics)} embedded")
            except Exception as e:
                stats["errors"] += len(batch)
                await session.rollback()
                print(f"  [interests] ERROR batch {i // batch_size + 1}: {e}")

    return stats


async def _load_api_keys_from_db() -> None:
    """Load LLM API keys from database into cache.

    The application stores API keys in the database (configured via admin UI).
    This must be called before any embedding operation outside the app lifespan.
    """
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.infrastructure.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await LLMConfigOverrideCache.load_from_db(db)
    print("[init] API keys loaded from database")


async def main() -> None:
    """Run the reindex pipeline."""
    parser = argparse.ArgumentParser(description="Reindex embeddings after E5 → OpenAI migration")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for API calls")
    parser.add_argument("--skip-store", action="store_true", help="Skip store_vectors reindexing")
    parser.add_argument(
        "--skip-interests", action="store_true", help="Skip user_interests reindexing"
    )
    args = parser.parse_args()

    from src.core.config import settings

    # Load API keys from DB (required — keys are stored in admin UI, not .env)
    await _load_api_keys_from_db()

    print(
        f"=== Embedding Reindex: E5 (384) → OpenAI "
        f"{settings.memory_embedding_model} ({settings.memory_embedding_dimensions}) ==="
    )
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"Batch size: {args.batch_size}")
    print()

    start = time.monotonic()
    results: dict[str, dict[str, int]] = {}

    if not args.skip_store:
        results["store"] = await reindex_store(args.dry_run, args.batch_size)

    if not args.skip_interests:
        results["interests"] = await reindex_interests(args.dry_run, args.batch_size)

    elapsed = round(time.monotonic() - start, 1)
    print(f"\n=== Done in {elapsed}s ===")
    for name, stats in results.items():
        print(
            f"  {name}: {stats['reindexed']}/{stats['total']} reindexed, "
            f"{stats['errors']} errors"
        )

    total_errors = sum(s["errors"] for s in results.values())
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
