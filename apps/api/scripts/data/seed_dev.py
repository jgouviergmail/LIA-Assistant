"""
Seed development database with test data.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import get_password_hash
from src.domains.auth.models import User
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.personalities.models import Personality  # noqa: F401 — required for User relationship resolution
from src.infrastructure.database.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)


async def seed_users(session: AsyncSession) -> list[User]:
    """Seed test users."""
    users_data = [
        {
            "email": "admin@example.com",
            "hashed_password": get_password_hash("admin123"),
            "full_name": "Admin User",
            "is_active": True,
            "is_verified": True,
            "is_superuser": True,
        },
        {
            "email": "user1@example.com",
            "hashed_password": get_password_hash("user123"),
            "full_name": "Test User 1",
            "is_active": True,
            "is_verified": True,
            "is_superuser": False,
        },
        {
            "email": "user2@example.com",
            "hashed_password": get_password_hash("user123"),
            "full_name": "Test User 2",
            "is_active": True,
            "is_verified": True,
            "is_superuser": False,
        },
        {
            "email": "unverified@example.com",
            "hashed_password": get_password_hash("user123"),
            "full_name": "Unverified User",
            "is_active": False,
            "is_verified": False,
            "is_superuser": False,
        },
        {
            "email": "oauth@example.com",
            "hashed_password": None,
            "full_name": "OAuth User",
            "is_active": True,
            "is_verified": True,
            "is_superuser": False,
            "oauth_provider": "google",
            "oauth_provider_id": "google_12345",
            "picture_url": "https://via.placeholder.com/150",
        },
    ]

    users = []
    for user_data in users_data:
        user = User(**user_data)
        session.add(user)
        users.append(user)

    await session.flush()
    logger.info("seeded_users", count=len(users))
    return users


async def seed_connectors(session: AsyncSession, users: list[User]) -> None:
    """Seed test connectors."""
    if len(users) < 2:
        return

    connectors_data = [
        {
            "user_id": users[1].id,  # user1
            "connector_type": ConnectorType.GMAIL.value,
            "status": ConnectorStatus.ACTIVE.value,
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
            "credentials_encrypted": "fake_encrypted_credentials_1",
            "metadata": {
                "email": "user1@example.com",
                "connected_at": "2025-01-15T00:00:00Z",
            },
        },
        {
            "user_id": users[1].id,  # user1
            "connector_type": ConnectorType.GOOGLE_DRIVE.value,
            "status": ConnectorStatus.ACTIVE.value,
            "scopes": ["https://www.googleapis.com/auth/drive.readonly"],
            "credentials_encrypted": "fake_encrypted_credentials_2",
            "metadata": {
                "email": "user1@example.com",
                "connected_at": "2025-01-15T00:00:00Z",
            },
        },
        {
            "user_id": users[2].id,  # user2
            "connector_type": ConnectorType.GMAIL.value,
            "status": ConnectorStatus.ACTIVE.value,
            "scopes": ["https://www.googleapis.com/auth/gmail.send"],
            "credentials_encrypted": "fake_encrypted_credentials_3",
            "metadata": {
                "email": "user2@example.com",
                "connected_at": "2025-01-15T00:00:00Z",
            },
        },
    ]

    for connector_data in connectors_data:
        connector = Connector(**connector_data)
        session.add(connector)

    await session.flush()
    logger.info("seeded_connectors", count=len(connectors_data))


async def main() -> None:
    """Main seed function."""
    logger.info(
        "seeding_database_start",
        environment=settings.environment,
        database_url=str(settings.database_url),
    )

    try:
        async with AsyncSessionLocal() as session:
            # Seed users
            users = await seed_users(session)

            # Seed connectors
            await seed_connectors(session, users)

            # Commit all changes
            await session.commit()

        logger.info("seeding_database_complete")
        print("\n✅ Database seeded successfully!")
        print(f"   - Created {len(users)} users")
        print("   - Admin user: admin@example.com / admin123")
        print("   - Test user: user1@example.com / user123")
        print("   - Test user: user2@example.com / user123")
        print("   - Created 3 test connectors")

    except Exception as exc:
        logger.error("seeding_database_failed", error=str(exc), exc_info=True)
        print(f"\n❌ Database seeding failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
