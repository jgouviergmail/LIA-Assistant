"""The installer's first account, on real PostgreSQL (owner decision 2026-10-22).

``ensure_admin`` writes the row in raw SQL (the installer's standalone
context), so no unit test executes its INSERT: the JSONB grid in particular is
proven only by the database reading it back.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.data.create_admin import ensure_admin
from src.core.constants import (
    PASSWORD_MIN_DIGITS,
    PASSWORD_MIN_LENGTH,
    PASSWORD_MIN_SPECIAL,
    PASSWORD_MIN_UPPERCASE,
    PASSWORD_SPECIAL_CHARS,
)
from src.domains.auth.new_account_columns import new_account_columns
from src.domains.users.models import User

pytestmark = pytest.mark.integration


def _policy_password() -> str:
    """A password the strict backend policy accepts, built from its own constants."""
    required = (
        "A" * PASSWORD_MIN_UPPERCASE
        + "1" * PASSWORD_MIN_DIGITS
        + PASSWORD_SPECIAL_CHARS[0] * PASSWORD_MIN_SPECIAL
    )
    return required + "a" * max(0, PASSWORD_MIN_LENGTH - len(required))


async def test_the_first_account_starts_like_every_new_account(db_session: AsyncSession) -> None:
    user_id = await ensure_admin(
        db_session,
        email="first-admin@example.com",
        password=_policy_password(),
        full_name="First Admin",
    )

    user = await db_session.scalar(
        select(User).where(User.id == user_id).execution_options(populate_existing=True)
    )
    assert user is not None
    assert user.is_superuser
    for column, value in new_account_columns().items():
        assert getattr(user, column) == value, column
