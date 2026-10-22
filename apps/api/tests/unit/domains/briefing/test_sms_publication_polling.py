"""Cache readiness polling must not repeatedly open the live SMS source."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.briefing.constants import SECTION_NAMES, SECTION_SMS
from src.domains.briefing.schemas import CardSection, CardStatus, SmsData
from src.domains.briefing.service import BriefingService
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def _service(*, hidden_sms: bool = False) -> BriefingService:
    """Build a service from loaded user columns without opening a database."""
    return BriefingService(
        User(
            id=uuid4(),
            email="polling@example.com",
            full_name="Polling fixture",
            language="fr",
            timezone="UTC",
            briefing_preferences={"hidden": [SECTION_SMS] if hidden_sms else [], "order": []},
        )
    )


def _sms() -> SmsData:
    now = datetime.now(UTC)
    return SmsData(total=1, window_total=1, window_start=now, as_of=now, latest_at=now)


@pytest.mark.parametrize("missing_section", ["weather", "mails"])
async def test_incomplete_bundle_polling_never_opens_sms(
    monkeypatch: pytest.MonkeyPatch, missing_section: str
) -> None:
    service = _service()
    missing_key = service._cache_key(missing_section)
    cached = CardSection(status=CardStatus.EMPTY, generated_at=datetime.now(UTC))

    async def read_cache(key: str) -> CardSection | None:
        return None if key == missing_key else cached

    sms = AsyncMock(return_value=_sms())
    monkeypatch.setattr(service, "_read_cache", read_cache)
    monkeypatch.setattr("src.domains.briefing.service.fetch_sms", sms)

    for _ in range(6):
        assert await service._published_bundle() is None

    sms.assert_not_awaited()


async def test_ready_bundle_reads_live_sms_once_without_rereading_other_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    cache = AsyncMock(
        return_value=CardSection(status=CardStatus.EMPTY, generated_at=datetime.now(UTC))
    )
    data = _sms()
    sms = AsyncMock(return_value=data)
    monkeypatch.setattr(service, "_read_cache", cache)
    monkeypatch.setattr("src.domains.briefing.service.fetch_sms", sms)

    bundle = await service._published_bundle()

    assert bundle is not None and bundle.sms.data == data
    sms.assert_awaited_once_with(user_id=service.user.id, include_messages=True)
    assert cache.await_count == len(SECTION_NAMES) - 1


async def test_hidden_sms_is_not_opened_when_other_sections_are_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(hidden_sms=True)
    monkeypatch.setattr(
        service,
        "_read_cache",
        AsyncMock(
            return_value=CardSection(status=CardStatus.EMPTY, generated_at=datetime.now(UTC))
        ),
    )
    sms = AsyncMock(return_value=_sms())
    monkeypatch.setattr("src.domains.briefing.service.fetch_sms", sms)

    bundle = await service._published_bundle()

    assert bundle is not None and bundle.sms.status is CardStatus.HIDDEN
    sms.assert_not_awaited()
