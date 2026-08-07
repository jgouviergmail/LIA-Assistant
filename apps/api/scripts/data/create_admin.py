"""Create or promote the admin user (manual operator tool).

The backend password policy is the single authority: every path goes through
``validate_password_strict`` before hashing (ADR-215, B11). No default
password exists, and the secret NEVER travels through argv — it is read from
stdin (piped) or an interactive hidden prompt.

Usage (from within the API container):
    echo '<password>' | python -m scripts.data.create_admin --email admin@x.tld --name "Admin"
    python -m scripts.data.create_admin --email admin@x.tld   # interactive getpass

The installer's atomic path is ``scripts.data.bootstrap_install`` (one stdin
JSON document, admin + provider keys in one transaction); this tool remains
for manual recovery only.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_NAME = "Admin User"


async def ensure_admin(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
) -> uuid.UUID:
    """Create the admin, or promote an existing account; flush, never commit.

    Raw SQL on purpose (standalone-script context: the User model's
    relationships require the full registry import). Idempotent: an existing
    superuser is untouched; an existing non-admin is promoted.

    Args:
        db: Session whose transaction the caller owns.
        email: Admin email address.
        password: Raw password — validated by the BACKEND policy before
            hashing; never logged.
        full_name: Display name for a newly created account.

    Returns:
        The admin user's id.

    Raises:
        ValueError: When the password fails the strict backend policy.
    """
    from src.core.security import get_password_hash
    from src.core.security.password_validation import validate_password_strict

    validate_password_strict(password)

    result = await db.execute(
        text("SELECT id, is_superuser FROM users WHERE email = :email"),
        {"email": email},
    )
    existing = result.fetchone()
    if existing:
        user_id, is_superuser = existing
        if not is_superuser:
            await db.execute(
                text("UPDATE users SET is_superuser = true WHERE id = :id"),
                {"id": user_id},
            )
            await db.flush()
        return uuid.UUID(str(user_id))

    new_id = uuid.uuid4()
    now = datetime.now(UTC)
    await db.execute(
        text("""
            INSERT INTO users (id, email, hashed_password, full_name,
                               is_active, is_verified, is_superuser,
                               created_at, updated_at)
            VALUES (:id, :email, :hashed_password, :full_name,
                    true, true, true, :now, :now)
            """),
        {
            "id": str(new_id),
            "email": email,
            "hashed_password": get_password_hash(password),
            "full_name": full_name,
            "now": now,
        },
    )
    await db.flush()
    return new_id


def _read_password() -> str:
    """Read the password from piped stdin, else an interactive hidden prompt."""
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\n")
    return getpass.getpass("Admin password (input hidden): ")


async def _run(email: str, full_name: str) -> None:
    from src.infrastructure.database.session import AsyncSessionLocal

    password = _read_password()
    if not password:
        print("ERROR: an admin password is required (no default exists).")
        raise SystemExit(2)
    async with AsyncSessionLocal() as session:
        admin_id = await ensure_admin(session, email=email, password=password, full_name=full_name)
        await session.commit()
    print(f"Admin ready: {email} (id={admin_id})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or promote the admin user (password via stdin/getpass)."
    )
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument(
        "--name", default=DEFAULT_NAME, help=f"Admin full name (default: {DEFAULT_NAME})"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(_run(args.email, args.name))
    except Exception as exc:  # operator tool: surface the reason, exit non-zero
        print(f"ERROR: failed to create admin user: {exc}")
        sys.exit(1)
