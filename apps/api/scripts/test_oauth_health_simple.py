#!/usr/bin/env python3
"""
Simple OAuth health test script - runs inside the API container context.

Usage (from api container):
    cd /app && python scripts/test_oauth_health_simple.py simulate-warning 34c679c8-1bde-4d96-b741-f615a5ab924d 30
    cd /app && python scripts/test_oauth_health_simple.py simulate-critical 34c679c8-1bde-4d96-b741-f615a5ab924d
    cd /app && python scripts/test_oauth_health_simple.py restore 34c679c8-1bde-4d96-b741-f615a5ab924d
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID


def init_app():
    """Initialize app to load all ORM models."""
    # This import triggers model registration
    import src.main  # noqa: F401


async def modify_connector_expiration(connector_id: str, minutes_until_expiry: int):
    """Modify connector credentials to simulate expiration."""
    # Import after app init
    from sqlalchemy import text

    from src.core.security import decrypt_data, encrypt_data
    from src.domains.connectors.schemas import ConnectorCredentials
    from src.infrastructure.database import get_db_context

    async with get_db_context() as session:
        # Use raw SQL to avoid ORM relationship issues
        result = await session.execute(
            text("""
                SELECT id, connector_type, credentials_encrypted
                FROM connectors
                WHERE id = :connector_id
            """),
            {"connector_id": connector_id},
        )
        row = result.fetchone()

        if not row:
            print(f"❌ Connector {connector_id} not found")
            return False

        connector_id_db, connector_type, credentials_encrypted = row
        print(f"Found connector: {connector_type}")

        # Decrypt current credentials
        try:
            credentials_json = decrypt_data(credentials_encrypted)
            credentials = ConnectorCredentials.model_validate_json(credentials_json)
        except Exception as e:
            print(f"❌ Failed to decrypt credentials: {e}")
            return False

        # Modify expires_at
        old_expires = credentials.expires_at
        new_expires_at = datetime.now(UTC) + timedelta(minutes=minutes_until_expiry)
        credentials.expires_at = new_expires_at

        # Re-encrypt and save
        new_credentials_json = credentials.model_dump_json()
        new_encrypted = encrypt_data(new_credentials_json)

        await session.execute(
            text("""
                UPDATE connectors
                SET credentials_encrypted = :credentials
                WHERE id = :connector_id
            """),
            {"credentials": new_encrypted, "connector_id": connector_id},
        )
        await session.commit()

        if minutes_until_expiry <= 0:
            status = "CRITICAL"
        elif minutes_until_expiry <= 60:
            status = "WARNING"
        else:
            status = "HEALTHY"

        print(f"✅ Connector modified")
        print(f"   Old expires_at: {old_expires}")
        print(f"   New expires_at: {new_expires_at}")
        print(f"   Expected status: {status}")
        return True


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python scripts/test_oauth_health_simple.py simulate-warning <connector_id> [minutes]")
        print("  python scripts/test_oauth_health_simple.py simulate-critical <connector_id>")
        print("  python scripts/test_oauth_health_simple.py restore <connector_id>")
        sys.exit(1)

    command = sys.argv[1]
    connector_id = sys.argv[2]

    # Initialize app first to load all models
    print("🔄 Initializing app...")
    init_app()
    print("✅ App initialized")

    if command == "simulate-warning":
        minutes = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        asyncio.run(modify_connector_expiration(connector_id, minutes))
    elif command == "simulate-critical":
        asyncio.run(modify_connector_expiration(connector_id, -60))
    elif command == "restore":
        asyncio.run(modify_connector_expiration(connector_id, 120))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
