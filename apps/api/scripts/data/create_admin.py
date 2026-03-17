"""
Create admin user for first-time setup.

Uses raw SQL to avoid SQLAlchemy model relationship resolution issues
that occur when running as a standalone script.

Usage (from within the API container):
    python -m scripts.data.create_admin
    python -m scripts.data.create_admin --email admin@mycompany.com --password MySecurePass123

Environment:
    Reads DATABASE_URL from settings (via .env or environment variables).
"""

import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.core.config import settings
from src.core.security import get_password_hash
from src.infrastructure.database.session import AsyncSessionLocal

DEFAULT_EMAIL = "admin@example.com"
DEFAULT_ADMIN_PASS = "admin123"
DEFAULT_NAME = "Admin User"


async def create_admin(email: str, password: str, full_name: str) -> None:
    """Create an admin user if one does not already exist.

    Uses raw SQL to avoid ORM relationship resolution issues when running
    as a standalone script (User model has relationships to Personality,
    Connector, Conversation, etc. that require all models to be imported).
    """
    async with AsyncSessionLocal() as session:
        # Check if user already exists
        result = await session.execute(
            text("SELECT id, is_superuser FROM users WHERE email = :email"),
            {"email": email},
        )
        existing = result.fetchone()

        if existing:
            user_id, is_superuser = existing
            print(f"\n⚠ User '{email}' already exists (superuser={is_superuser}).")
            if not is_superuser:
                await session.execute(
                    text("UPDATE users SET is_superuser = true WHERE id = :id"),
                    {"id": user_id},
                )
                await session.commit()
                print(f"  → Promoted to superuser.")
            else:
                print(f"  → No changes needed.")
            return

        # Create admin user via raw SQL
        now = datetime.now(timezone.utc)
        await session.execute(
            text("""
                INSERT INTO users (id, email, hashed_password, full_name, is_active, is_verified, is_superuser, created_at, updated_at)
                VALUES (:id, :email, :hashed_password, :full_name, true, true, true, :now, :now)
            """),
            {
                "id": str(uuid.uuid4()),
                "email": email,
                "hashed_password": get_password_hash(password),
                "full_name": full_name,
                "now": now,
            },
        )
        await session.commit()

        print(f"\n✅ Admin user created successfully!")
        print(f"   Email:    {email}")
        print(f"   Password: {'*' * len(password)}")
        print(f"   Name:     {full_name}")
        print(f"\n   You can now log in at the application's login page.")
        print(f"   ⚠ Change the default password after first login!")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create admin user for first-time setup.")
    parser.add_argument(
        "--email",
        default=DEFAULT_EMAIL,
        help=f"Admin email address (default: {DEFAULT_EMAIL})",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_ADMIN_PASS,
        help=f"Admin password (default: {DEFAULT_ADMIN_PASS})",
    )
    parser.add_argument(
        "--name",
        default=DEFAULT_NAME,
        help=f"Admin full name (default: {DEFAULT_NAME})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(create_admin(args.email, args.password, args.name))
    except Exception as exc:
        print(f"\n❌ Failed to create admin user: {exc}")
        sys.exit(1)
