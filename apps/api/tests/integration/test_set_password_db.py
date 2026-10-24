"""Setting an account's password from the server, on real PostgreSQL (ADR-363 amendment).

``set_account_password`` writes in raw SQL — the operator tool's standalone
context, like ``create_admin`` — so only the database reading the row back
proves the UPDATE. The e-mail reset never serves an administrator, and every
self-hosted instance's first account is one WITH a password: this is how its
operator gets back in.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.data.set_password import set_account_password
from src.core.constants import (
    PASSWORD_MIN_DIGITS,
    PASSWORD_MIN_LENGTH,
    PASSWORD_MIN_SPECIAL,
    PASSWORD_MIN_UPPERCASE,
    PASSWORD_SPECIAL_CHARS,
)
from src.core.security import verify_password
from src.domains.users.models import User

pytestmark = pytest.mark.integration


def _policy_password(filler: str = "a") -> str:
    """A password the strict backend policy accepts, built from its own constants."""
    required = (
        "B" * PASSWORD_MIN_UPPERCASE
        + "7" * PASSWORD_MIN_DIGITS
        + PASSWORD_SPECIAL_CHARS[0] * PASSWORD_MIN_SPECIAL
    )
    return required + filler * max(0, PASSWORD_MIN_LENGTH - len(required))


async def _reread(db: AsyncSession, user: User) -> User:
    fresh = await db.scalar(
        select(User).where(User.id == user.id).execution_options(populate_existing=True)
    )
    assert fresh is not None
    return fresh


async def test_the_operator_sets_a_forgotten_administrator_password(
    db_session: AsyncSession, test_superuser: User
) -> None:
    new_password = _policy_password()

    result = await set_account_password(
        db_session, email=test_superuser.email, password=new_password
    )

    stored = await _reread(db_session, test_superuser)
    assert stored.hashed_password is not None
    assert verify_password(new_password, stored.hashed_password)
    assert result.user_id == test_superuser.id
    assert result.is_superuser is True
    assert result.provider is None


async def test_only_the_named_account_changes(
    db_session: AsyncSession, test_user: User, test_superuser: User
) -> None:
    untouched = test_user.hashed_password

    await set_account_password(db_session, email=test_superuser.email, password=_policy_password())

    assert (await _reread(db_session, test_user)).hashed_password == untouched


async def test_a_provider_account_is_told_it_now_has_a_password(
    db_session: AsyncSession, test_user: User
) -> None:
    test_user.oauth_provider = "google"
    test_user.hashed_password = None
    await db_session.commit()

    result = await set_account_password(
        db_session, email=test_user.email, password=_policy_password()
    )

    assert result.provider == "google"
    assert (await _reread(db_session, test_user)).hashed_password is not None


async def test_an_unknown_address_names_no_account(db_session: AsyncSession) -> None:
    with pytest.raises(LookupError):
        await set_account_password(
            db_session, email="nobody@example.com", password=_policy_password()
        )


async def test_a_deleted_account_is_never_given_a_password(
    db_session: AsyncSession, test_user: User
) -> None:
    test_user.deleted_at = datetime.now(UTC)
    before = test_user.hashed_password
    await db_session.commit()

    with pytest.raises(ValueError, match="deleted"):
        await set_account_password(db_session, email=test_user.email, password=_policy_password())

    assert (await _reread(db_session, test_user)).hashed_password == before


async def test_a_weak_password_is_refused_before_anything_is_read(
    db_session: AsyncSession, test_superuser: User
) -> None:
    before = test_superuser.hashed_password

    with pytest.raises(ValueError):
        await set_account_password(db_session, email=test_superuser.email, password="short")

    assert (await _reread(db_session, test_superuser)).hashed_password == before
