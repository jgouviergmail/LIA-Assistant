"""What the settings show of how the person writes, and forgetting it (ADR-383)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.core.security.utils import encrypt_data
from src.domains.writing_style.repository import StoredStyle
from src.domains.writing_style.service import WritingStyleService

pytestmark = pytest.mark.unit
LEARNED = datetime(2026, 11, 13, 9, tzinfo=UTC)


def _service(stored: StoredStyle | None, *, forgot: bool = True) -> tuple[Any, MagicMock]:
    db = MagicMock()
    db.commit = AsyncMock()
    service = WritingStyleService(db)
    service.repository = MagicMock(
        read=AsyncMock(return_value=stored), forget=AsyncMock(return_value=forgot)
    )
    return service, db


def _row(encrypted: str | None, mails_read: int = 12) -> Any:
    return SimpleNamespace(profile_encrypted=encrypted, mails_read=mails_read, built_at=LEARNED)


async def test_a_learned_style_is_shown_with_when_it_is_learned_again() -> None:
    service, _db = _service(StoredStyle(True, _row(encrypt_data("Signs « Seb »."))))

    shown = await service.read(uuid4())

    assert shown.enabled and shown.profile == "Signs « Seb »." and shown.mails_read == 12
    assert shown.learned_at == LEARNED
    assert shown.renews_at == LEARNED + timedelta(days=settings.writing_style_max_age_days)


async def test_too_few_sent_mails_show_what_was_read_and_no_style() -> None:
    service, _db = _service(StoredStyle(True, _row(None, mails_read=2)))

    shown = await service.read(uuid4())

    assert shown.profile is None and shown.mails_read == 2 and shown.learned_at == LEARNED


async def test_nothing_learned_yet_and_a_switched_off_style_read_as_such() -> None:
    service, _db = _service(StoredStyle(False, None))

    shown = await service.read(uuid4())

    assert not shown.enabled and shown.profile is None and shown.mails_read is None
    assert shown.learned_at is None and shown.renews_at is None


async def test_a_style_that_cannot_be_read_back_reads_as_not_learned() -> None:
    service, _db = _service(StoredStyle(True, _row("not-a-fernet-token")))

    shown = await service.read(uuid4())

    assert shown.profile is None and shown.mails_read is None and shown.learned_at is None


async def test_an_unknown_account_is_refused() -> None:
    service, _db = _service(None)

    with pytest.raises(BaseAPIException):
        await service.read(uuid4())


async def test_forgetting_removes_the_profile_and_commits() -> None:
    service, db = _service(StoredStyle(True, None), forgot=True)

    assert await service.forget(uuid4()) is True
    db.commit.assert_awaited_once()
