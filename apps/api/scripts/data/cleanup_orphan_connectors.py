"""
Cleanup orphan connectors (status != 'active') from database.

This script removes connectors that are in error/inactive/revoked state,
which can cause issues with the bulk connect flow.

Usage:
    cd apps/api
    python scripts/cleanup_orphan_connectors.py --dry-run  # Preview changes
    python scripts/cleanup_orphan_connectors.py            # Execute cleanup
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
api_root = Path(__file__).parent.parent
project_root = api_root.parent.parent  # LIA root
sys.path.insert(0, str(api_root))

# Load .env file from project root
from dotenv import load_dotenv

env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    print(f"[WARN] .env file not found: {env_file}")
    print("       Make sure you are in the correct directory.")

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.connectors.models import Connector, ConnectorStatus
from src.infrastructure.database.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)


async def list_orphan_connectors(session: AsyncSession) -> list[Connector]:
    """Find all connectors with status != 'active'."""
    stmt = select(Connector).where(Connector.status != ConnectorStatus.ACTIVE.value)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_orphan_connectors(session: AsyncSession, dry_run: bool = True) -> int:
    """Delete orphan connectors."""
    orphans = await list_orphan_connectors(session)

    if not orphans:
        print("\n[OK] No orphan connectors found.")
        return 0

    print(f"\n[INFO] Found {len(orphans)} orphan connector(s):\n")
    print("-" * 80)
    print(f"{'ID':<10} {'User ID':<38} {'Type':<20} {'Status':<12}")
    print("-" * 80)

    for conn in orphans:
        print(f"{conn.id:<10} {str(conn.user_id):<38} {conn.connector_type:<20} {conn.status:<12}")

    print("-" * 80)

    if dry_run:
        print("\n[DRY-RUN] No deletions performed.")
        print("          Re-run without --dry-run to delete.")
        return len(orphans)

    # Delete orphan connectors
    for conn in orphans:
        await session.delete(conn)

    await session.commit()
    print(f"\n[OK] {len(orphans)} orphan connector(s) deleted.")
    return len(orphans)


async def main(dry_run: bool = True) -> None:
    """Main cleanup function."""
    print("=" * 80)
    print("ORPHAN CONNECTORS CLEANUP")
    print("=" * 80)

    try:
        async with AsyncSessionLocal() as session:
            count = await delete_orphan_connectors(session, dry_run=dry_run)

            if count > 0 and not dry_run:
                logger.info("cleanup_complete", deleted_count=count)

    except Exception as exc:
        logger.error("cleanup_failed", error=str(exc), exc_info=True)
        print(f"\n[ERROR] Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean up orphan connectors")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display connectors to delete without deleting them",
    )
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run))
