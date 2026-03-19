"""
Seed script for system RAG spaces (FAQ knowledge base).

Idempotent: creates the FAQ space if missing, re-indexes only if content changed.

Usage:
    cd apps/api
    .venv/Scripts/python -m scripts.seed_system_rag

    Or via Taskfile:
    task db:seed:system-rag
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Load .env before any application imports (Settings requires DATABASE_URL etc.)
# .env is at monorepo root (../../ from apps/api/)
_script_dir = Path(__file__).resolve().parent
_api_dir = _script_dir.parent
_env_file = _api_dir / ".env"
if not _env_file.exists():
    _env_file = _api_dir.parent.parent / ".env"  # monorepo root
if _env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(_env_file)


async def main() -> None:
    """Seed the system FAQ RAG space."""
    # Register ALL SQLAlchemy models before any DB operation.
    # Without this, relationship() string references fail with InvalidRequestError.
    from src.infrastructure.database.registry import import_all_models

    import_all_models()

    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.domains.rag_spaces.system_indexer import SystemSpaceIndexer
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.observability.logging import get_logger

    logger = get_logger(__name__)

    async with get_db_context() as db:
        # Load API keys from DB into memory cache (required for embeddings)
        await LLMConfigOverrideCache.load_from_db(db)

        indexer = SystemSpaceIndexer(db)
        result = await indexer.index_faq_space()

    status = result["status"]
    if status == "success":
        logger.info(
            "seed_system_rag_complete",
            chunks_created=result["chunks_created"],
            content_hash=result["content_hash"],
        )
        print(
            f"System FAQ space indexed: {result['chunks_created']} chunks "
            f"(hash: {result['content_hash'][:12]}...)"
        )
    elif status == "skipped":
        logger.info("seed_system_rag_skipped", content_hash=result["content_hash"])
        print("System FAQ space already up to date — skipped.")
    else:
        logger.error("seed_system_rag_failed", error=result.get("error"))
        print(f"ERROR: {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
