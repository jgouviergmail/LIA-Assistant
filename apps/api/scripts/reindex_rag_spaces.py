"""Reindex all RAG Spaces documents from the command line.

Companion to ``reindex_embeddings.py``. Re-embeds every user RAG document with
the currently configured embedding model (``RAG_SPACES_EMBEDDING_MODEL``) and
alters the pgvector column + HNSW index if the dimensionality changed.

This is the in-container equivalent of ``POST /rag-spaces/admin/reindex``. It is
meant to be run from the host itself (where the operator is already
root-equivalent inside the container), so it needs no HTTP call and no admin
session cookie — which keeps a superuser bearer token out of shell history.

Usage:
    DEV:  cd apps/api && python scripts/reindex_rag_spaces.py
    PROD: docker exec lia-api-prod python scripts/reindex_rag_spaces.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()  # Load .env before any src imports

# Import all SQLAlchemy models so relationships resolve correctly
from src.infrastructure.database.registry import import_all_models

import_all_models()


async def _load_api_keys_from_db() -> None:
    """Load LLM API keys from the database into the override cache.

    Embedding calls need the provider API keys, which are stored in the DB
    (configured via the admin UI) rather than in ``.env``. This must run before
    any embedding operation performed outside the application lifespan.
    """
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.infrastructure.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await LLMConfigOverrideCache.load_from_db(db)
    print("[init] API keys loaded from database")


async def main() -> None:
    """Run a full RAG Spaces reindexation to completion and report the outcome."""
    from src.core.config import settings
    from src.domains.rag_spaces.reindex import get_reindex_status, start_reindexation
    from src.infrastructure.database.session import get_db_context

    # API keys live in the DB, not .env — load them before embedding
    await _load_api_keys_from_db()

    # Warm the pricing cache before re-embedding: embedding cost is read from
    # `llm_model_pricing` (ADR-242), and this script re-embeds every user
    # document — the single largest batch the deployment ever runs.
    from src.infrastructure.cache.pricing_cache import refresh_pricing_cache

    try:
        await refresh_pricing_cache()
    except Exception as exc:  # noqa: BLE001 - reporting must not block a reindex
        print(f"WARNING: pricing cache unavailable, cost metrics will read 0 ({exc})")

    print(
        f"=== RAG Spaces Reindex: {settings.rag_spaces_embedding_model} "
        f"({settings.rag_spaces_embedding_dimensions}d) ==="
    )

    async with get_db_context() as db:
        result = await start_reindexation(db, run_in_background=False)

    print(f"  {result['message']}")

    # Final counts come from the Redis status snapshot written on completion
    status = await get_reindex_status()
    processed = status.get("processed_documents")
    failed = status.get("failed_documents")
    if processed is not None:
        print(f"  Documents: {processed} reindexed, {failed} failed")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
