"""Set an account's password from the server (operator recovery tool, ADR-363).

The e-mail reset never serves an administrator (ADR-363), and every self-hosted
instance's first account is an administrator WITH a password: this command is
how its operator gets back in. As for ``create_admin``, the backend password
policy is the single authority, and the secret NEVER travels through argv — it
is read from piped stdin, or typed twice at a hidden prompt.

Usage (from within the API container):
    python -m scripts.data.set_password --email admin@x.tld        # asks twice, hidden
    echo '<password>' | python -m scripts.data.set_password --email admin@x.tld

In order: a password the policy refuses, an unknown address and a deleted
account change nothing; the new hash is committed; THEN the account is signed
out of every device — never before, or a stolen session would survive a
password that never changed. Every reset link issued earlier stops working by
construction (it is bound to the old hash). No ``admin_audit_log`` row: its
``admin_user_id`` is a NOT NULL reference to an account and the operator is
none (the automatic-deletion precedent); the structured log records the act.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

#: What the command reports when the session store cannot sign the account out.
_SESSIONS_NOT_REVOKED = (
    "ERROR: the password IS set, but the account could not be signed out of its "
    "devices ({error}). Run the command again once the session store answers."
)


@dataclass(frozen=True, slots=True)
class PasswordSet:
    """What the command changed, for its report."""

    user_id: uuid.UUID
    is_superuser: bool
    provider: str | None


async def set_account_password(db: AsyncSession, *, email: str, password: str) -> PasswordSet:
    """Write a new password hash for the account an address names; flush, never commit.

    Raw SQL on purpose (standalone-script context, as ``create_admin``: the User
    model's relationships require the full registry import).

    Args:
        db: Session whose transaction the caller owns.
        email: The account's address, matched exactly.
        password: The new raw password — validated by the BACKEND policy before
            anything is read; never logged.

    Returns:
        The account's id, whether it is an administrator, and the provider it
        also signs in with (it has a password from now on).

    Raises:
        ValueError: When the policy refuses the password, or the account is
            deleted (its address is kept for billing, its person is gone).
        LookupError: When no account has this address.
    """
    from src.core.security import get_password_hash
    from src.core.security.password_validation import validate_password_strict

    validate_password_strict(password)

    row = (
        await db.execute(
            text(
                "SELECT id, is_superuser, deleted_at, oauth_provider FROM users "
                "WHERE email = :email"
            ),
            {"email": email},
        )
    ).fetchone()
    if row is None:
        raise LookupError("no account has this address")
    user_id, is_superuser, deleted_at, provider = row
    if deleted_at is not None:
        raise ValueError("the account is deleted: it is never given a password")

    await db.execute(
        text("UPDATE users SET hashed_password = :hashed, updated_at = :now WHERE id = :id"),
        {"hashed": get_password_hash(password), "now": datetime.now(UTC), "id": user_id},
    )
    await db.flush()
    return PasswordSet(
        user_id=uuid.UUID(str(user_id)), is_superuser=bool(is_superuser), provider=provider
    )


def read_new_password() -> str | None:
    """Read the new password from piped stdin, else typed twice at a hidden prompt.

    Returns:
        The password (empty when nothing was given), or None when the two typed
        passwords differ.
    """
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("New password (input hidden): ")
    if getpass.getpass("Same password again: ") != first:
        return None
    return first


async def _run(email: str, password: str) -> int:
    """Set the password, then sign the account out of every device.

    Args:
        email: The account's address.
        password: The new raw password.

    Returns:
        The process exit code.
    """
    from src.infrastructure.cache import redis as session_redis
    from src.infrastructure.cache import session_store
    from src.infrastructure.database import session as database

    try:
        async with database.AsyncSessionLocal() as db:
            changed = await set_account_password(db, email=email, password=password)
            await db.commit()
    except (LookupError, ValueError) as refusal:
        print(f"ERROR: {refusal} — nothing was changed.")
        return 1

    try:
        store = session_store.SessionStore(await session_redis.get_redis_session())
        revoked = await store.delete_all_user_sessions(str(changed.user_id))
    except Exception as error:  # operator tool: the password is set either way
        print(_SESSIONS_NOT_REVOKED.format(error=type(error).__name__))
        return 1
    finally:
        await session_redis.close_redis()

    logger.warning(
        "account_password_set_from_server",
        user_id=str(changed.user_id),
        is_superuser=changed.is_superuser,
        sessions_revoked=revoked,
    )
    role = "an administrator" if changed.is_superuser else "not an administrator"
    print(f"Password set for {email} (id={changed.user_id}, {role}).")
    print(f"{revoked} session(s) signed out; earlier reset links no longer work.")
    if changed.provider:
        print(f"This account also signs in with {changed.provider}: it now has a password too.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments and run the command.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Set an account's password from the server (password via stdin/getpass)."
    )
    parser.add_argument("--email", required=True, help="The account's address")
    args = parser.parse_args(argv)
    password = read_new_password()
    if password is None:
        print("ERROR: the two passwords differ — nothing was changed.")
        return 2
    if not password:
        print("ERROR: a password is required (no default exists) — nothing was changed.")
        return 2
    return asyncio.run(_run(args.email, password))


if __name__ == "__main__":
    sys.exit(main())
