#!/usr/bin/env python3
"""
Migrate memories from LangGraph AsyncPostgresStore to custom PostgreSQL table.

This script COPIES (not moves) memory data from the LangGraph store's internal
tables to the new `memories` PostgreSQL table with pgvector embeddings.

Strategy:
1. Read all items from the LangGraph store's `(user_id, "memories")` namespace
2. Map each item's value dict to the new Memory model
3. Re-embed each memory (the store doesn't expose vectors via its API)
4. Insert into the new `memories` table
5. Validate counts match

Original data in the LangGraph store is PRESERVED as fallback.

Usage:
    # Dry run (no writes)
    python scripts/migrate_memories_to_postgresql.py --dry-run

    # Execute migration
    python scripts/migrate_memories_to_postgresql.py

    # Validate only (check counts after migration)
    python scripts/migrate_memories_to_postgresql.py --validate-only

Requirements:
    - PostgreSQL running with both LangGraph store and new memories table
    - OPENAI_API_KEY set for re-embedding
    - Run from the apps/api directory (or set PYTHONPATH)

Phase: v1.14.0 — Memory migration to PostgreSQL custom
Created: 2026-03-30
"""

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Add the API source to the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))


async def migrate(dry_run: bool = False, validate_only: bool = False) -> dict:
    """Run the migration.

    Args:
        dry_run: If True, only show what would be migrated without writing.
        validate_only: If True, only check counts in both systems.

    Returns:
        Stats dict with counts and errors.
    """
    from src.core.config import settings  # noqa: F401 — triggers env loading
    from src.infrastructure.database.registry import import_all_models

    import_all_models()

    stats = {
        "store_users": 0,
        "store_memories": 0,
        "migrated": 0,
        "skipped": 0,
        "errors": 0,
        "new_table_count": 0,
    }

    # Get the LangGraph store
    from src.domains.agents.context.store import get_tool_context_store

    store = await get_tool_context_store()
    if not store:
        print("ERROR: Could not initialize LangGraph store")
        return stats

    # Find all user IDs with memories in the store
    if hasattr(store, "_conn") and store._conn is not None:
        conn = store._conn
        query = """
            SELECT DISTINCT namespace[1] as user_id
            FROM store
            WHERE namespace[2] = 'memories'
            AND array_length(namespace, 1) >= 2
        """
        async with conn.cursor() as cursor:
            await cursor.execute(query)
            rows = await cursor.fetchall()
            user_ids = [row["user_id"] for row in rows if row.get("user_id")]
    else:
        print("ERROR: Store connection not available")
        return stats

    stats["store_users"] = len(user_ids)
    print(f"Found {len(user_ids)} users with memories in LangGraph store")

    if validate_only:
        # Just count in both systems
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            from src.domains.memories.repository import MemoryRepository

            repo = MemoryRepository(db)
            for user_id_str in user_ids:
                # Count in store
                results = await store.asearch(
                    (user_id_str, "memories"), query="", limit=1000
                )
                store_count = len(results)
                stats["store_memories"] += store_count

                # Count in new table
                try:
                    new_count = await repo.get_count_for_user(uuid.UUID(user_id_str))
                    stats["new_table_count"] += new_count
                except Exception:
                    pass

                print(f"  User {user_id_str[:8]}...: store={store_count}, new_table={new_count}")

        print(f"\nTotal: store={stats['store_memories']}, new_table={stats['new_table_count']}")
        return stats

    # Prepare embedding model for re-embedding
    from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

    embeddings = get_memory_embeddings()

    from src.domains.memories.service import _build_memory_embedding_text
    from src.infrastructure.database.session import get_db_context

    for user_id_str in user_ids:
        print(f"\nProcessing user {user_id_str[:8]}...")

        # Get all memories from store
        try:
            results = await store.asearch(
                (user_id_str, "memories"), query="", limit=1000
            )
        except Exception as e:
            print(f"  ERROR reading store for user {user_id_str[:8]}: {e}")
            stats["errors"] += 1
            continue

        stats["store_memories"] += len(results)
        print(f"  Found {len(results)} memories in store")

        if dry_run:
            for item in results:
                if isinstance(item.value, dict):
                    content = item.value.get("content", "")[:60]
                    category = item.value.get("category", "?")
                    print(f"    [DRY] {category}: {content}")
                    stats["migrated"] += 1
            continue

        # Migrate each memory
        async with get_db_context() as db:
            from src.domains.memories.models import Memory

            for item in results:
                if not isinstance(item.value, dict):
                    stats["skipped"] += 1
                    continue

                try:
                    value = item.value
                    content = value.get("content", "")
                    if not content:
                        stats["skipped"] += 1
                        continue

                    trigger_topic = value.get("trigger_topic", "")

                    # Re-embed
                    embed_text = _build_memory_embedding_text(content, trigger_topic)
                    embedding = await embeddings.aembed_query(embed_text)

                    # Parse created_at
                    created_at_raw = value.get("created_at")
                    if isinstance(created_at_raw, str):
                        try:
                            created_at = datetime.fromisoformat(
                                created_at_raw.replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            created_at = datetime.now(UTC)
                    elif isinstance(created_at_raw, datetime):
                        created_at = created_at_raw
                    else:
                        created_at = datetime.now(UTC)

                    # Parse last_accessed_at
                    last_accessed_raw = value.get("last_accessed_at")
                    last_accessed_at = None
                    if isinstance(last_accessed_raw, str):
                        try:
                            last_accessed_at = datetime.fromisoformat(
                                last_accessed_raw.replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            pass

                    memory = Memory(
                        user_id=uuid.UUID(user_id_str),
                        content=content,
                        category=value.get("category", "personal"),
                        emotional_weight=int(value.get("emotional_weight", 0)),
                        trigger_topic=trigger_topic,
                        usage_nuance=value.get("usage_nuance", ""),
                        importance=float(value.get("importance", 0.7)),
                        usage_count=int(value.get("usage_count", 0)),
                        last_accessed_at=last_accessed_at,
                        pinned=bool(value.get("pinned", False)),
                        embedding=embedding,
                        char_count=len(content),
                    )
                    # Override timestamps
                    memory.created_at = created_at
                    memory.updated_at = created_at

                    db.add(memory)
                    stats["migrated"] += 1

                except Exception as e:
                    print(f"    ERROR migrating memory: {e}")
                    stats["errors"] += 1

            await db.commit()
            print(f"  Migrated {stats['migrated']} memories for this user")

    print(f"\n=== Migration Complete ===")
    print(f"Users processed: {stats['store_users']}")
    print(f"Store memories: {stats['store_memories']}")
    print(f"Migrated: {stats['migrated']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Errors: {stats['errors']}")

    return stats


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate memories from LangGraph store to PostgreSQL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without writing",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only check counts in both systems",
    )
    args = parser.parse_args()

    result = asyncio.run(migrate(dry_run=args.dry_run, validate_only=args.validate_only))

    if result["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
