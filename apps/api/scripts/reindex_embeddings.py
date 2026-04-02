"""
Reindex embeddings for dual-vector search strategy.

Reindexes:
1. LangGraph store items (store → store_vectors via AsyncPostgresStore.aput)
2. User interest embeddings (user_interests.embedding)
3. Memory embeddings (content → embedding, trigger_topic → keyword_embedding)
4. Journal embeddings (title+content → embedding, search_hints → keyword_embedding)

Usage:
    DEV:  cd apps/api && python scripts/reindex_embeddings.py
    PROD: docker exec lia-api-prod python scripts/reindex_embeddings.py

Options:
    --dry-run           Preview changes without writing
    --batch-size N      Batch size for Gemini API calls (default: 50)
    --skip-store        Skip LangGraph store reindexing
    --skip-interests    Skip user_interests reindexing
    --skip-memories     Skip memories reindexing
    --skip-journals     Skip journal_entries reindexing
    --only-memories     Only reindex memories
    --only-journals     Only reindex journal_entries
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
    """Reindex user_interests.embedding with Gemini embeddings.

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
    from src.domains.interests.embedding import get_interest_embeddings

    embeddings = get_interest_embeddings()
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


async def reindex_memories(dry_run: bool, batch_size: int) -> dict[str, int]:
    """Reindex memory embeddings with dual-vector strategy.

    Splits the single concatenated embedding into:
    - embedding: content only
    - keyword_embedding: trigger_topic only

    Idempotent: safe to re-run. Skips memories that already have
    keyword_embedding set (unless content embedding also needs update).

    Args:
        dry_run: If True, preview without writing.
        batch_size: Number of memories to embed per Gemini API call.

    Returns:
        Dict with total, reindexed, errors counts.
    """
    from sqlalchemy import select

    from src.domains.memories.models import Memory
    from src.infrastructure.database.session import AsyncSessionLocal
    from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

    embeddings = get_memory_embeddings()
    stats: dict[str, int] = {"total": 0, "reindexed": 0, "errors": 0}

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Memory).where(Memory.content.isnot(None)))
        memories = result.scalars().all()
        stats["total"] = len(memories)
        print(f"[memories] Found {stats['total']} memories to reindex")

        for i in range(0, len(memories), batch_size):
            batch = memories[i : i + batch_size]

            # Build texts: content for embedding, trigger_topic for keyword_embedding
            content_texts = [m.content for m in batch]
            keyword_texts = [m.trigger_topic or "" for m in batch]

            if dry_run:
                print(
                    f"  [DRY-RUN] Would embed batch {i // batch_size + 1} "
                    f"({len(batch)} memories)"
                )
                stats["reindexed"] += len(batch)
                continue

            try:
                # Embed content
                content_vectors = embeddings.embed_documents(content_texts)

                # Embed keywords (only non-empty)
                keyword_indices = [j for j, t in enumerate(keyword_texts) if t.strip()]
                keyword_vectors_map: dict[int, list[float]] = {}
                if keyword_indices:
                    kw_texts = [keyword_texts[j] for j in keyword_indices]
                    kw_vectors = embeddings.embed_documents(kw_texts)
                    for j, vec in zip(keyword_indices, kw_vectors, strict=True):
                        keyword_vectors_map[j] = vec

                for j, memory in enumerate(batch):
                    memory.embedding = content_vectors[j]
                    memory.keyword_embedding = keyword_vectors_map.get(j)
                    stats["reindexed"] += 1

                await session.commit()
                print(
                    f"  [memories] Batch {i // batch_size + 1}: "
                    f"{len(batch)} embedded ({len(keyword_indices)} with keywords)"
                )
            except Exception as e:
                stats["errors"] += len(batch)
                await session.rollback()
                print(f"  [memories] ERROR batch {i // batch_size + 1}: {e}")

    return stats


async def reindex_journals(dry_run: bool, batch_size: int) -> dict[str, int]:
    """Reindex journal entry embeddings with dual-vector strategy.

    Splits the single concatenated embedding into:
    - embedding: title + content
    - keyword_embedding: search_hints only

    Idempotent: safe to re-run.

    Args:
        dry_run: If True, preview without writing.
        batch_size: Number of entries to embed per Gemini API call.

    Returns:
        Dict with total, reindexed, errors counts.
    """
    from sqlalchemy import select

    from src.domains.journals.embedding import get_journal_embeddings
    from src.domains.journals.models import JournalEntry
    from src.infrastructure.database.session import AsyncSessionLocal

    embeddings = get_journal_embeddings()
    stats: dict[str, int] = {"total": 0, "reindexed": 0, "errors": 0}

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(JournalEntry).where(JournalEntry.content.isnot(None)))
        entries = result.scalars().all()
        stats["total"] = len(entries)
        print(f"[journals] Found {stats['total']} journal entries to reindex")

        for i in range(0, len(entries), batch_size):
            batch = entries[i : i + batch_size]

            # Build texts: title+content for embedding, search_hints for keyword_embedding
            content_texts = [f"{e.title}. {e.content}." for e in batch]
            hint_texts = [
                " ".join(e.search_hints) if e.search_hints else ""
                for e in batch
            ]

            if dry_run:
                print(
                    f"  [DRY-RUN] Would embed batch {i // batch_size + 1} "
                    f"({len(batch)} entries)"
                )
                stats["reindexed"] += len(batch)
                continue

            try:
                # Embed content
                content_vectors = embeddings.embed_documents(content_texts)

                # Embed hints (only non-empty)
                hint_indices = [j for j, t in enumerate(hint_texts) if t.strip()]
                hint_vectors_map: dict[int, list[float]] = {}
                if hint_indices:
                    h_texts = [hint_texts[j] for j in hint_indices]
                    h_vectors = embeddings.embed_documents(h_texts)
                    for j, vec in zip(hint_indices, h_vectors, strict=True):
                        hint_vectors_map[j] = vec

                for j, entry in enumerate(batch):
                    entry.embedding = content_vectors[j]
                    entry.keyword_embedding = hint_vectors_map.get(j)
                    stats["reindexed"] += 1

                await session.commit()
                print(
                    f"  [journals] Batch {i // batch_size + 1}: "
                    f"{len(batch)} embedded ({len(hint_indices)} with hints)"
                )
            except Exception as e:
                stats["errors"] += len(batch)
                await session.rollback()
                print(f"  [journals] ERROR batch {i // batch_size + 1}: {e}")

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
    parser = argparse.ArgumentParser(description="Reindex embeddings (dual-vector strategy)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for API calls")
    parser.add_argument("--skip-store", action="store_true", help="Skip store_vectors reindexing")
    parser.add_argument(
        "--skip-interests", action="store_true", help="Skip user_interests reindexing"
    )
    parser.add_argument("--skip-memories", action="store_true", help="Skip memories reindexing")
    parser.add_argument("--skip-journals", action="store_true", help="Skip journals reindexing")
    parser.add_argument(
        "--only-memories", action="store_true", help="Only reindex memories (skip all others)"
    )
    parser.add_argument(
        "--only-journals", action="store_true", help="Only reindex journals (skip all others)"
    )
    args = parser.parse_args()

    from src.core.config import settings

    # Load API keys from DB (required — keys are stored in admin UI, not .env)
    await _load_api_keys_from_db()

    print(
        f"=== Embedding Reindex: "
        f"{settings.memory_embedding_model} ({settings.memory_embedding_dimensions}d) ==="
    )
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"Batch size: {args.batch_size}")
    print()

    start = time.monotonic()
    results: dict[str, dict[str, int]] = {}

    # --only-* shortcuts
    if args.only_memories:
        results["memories"] = await reindex_memories(args.dry_run, args.batch_size)
    elif args.only_journals:
        results["journals"] = await reindex_journals(args.dry_run, args.batch_size)
    else:
        if not args.skip_store:
            results["store"] = await reindex_store(args.dry_run, args.batch_size)

        if not args.skip_interests:
            results["interests"] = await reindex_interests(args.dry_run, args.batch_size)

        if not args.skip_memories:
            results["memories"] = await reindex_memories(args.dry_run, args.batch_size)

        if not args.skip_journals:
            results["journals"] = await reindex_journals(args.dry_run, args.batch_size)

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
