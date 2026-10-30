"""The dashboard's text build reads the person's SMS ONCE for its two prompts (E13).

Measured (spec 2026-10-21 §0ter D-H6): one page load read the SMS store three
times — the card, then the greeting and the synthesis each on their own. The
greeting needs the counts and the synthesis the excerpts, and one read with the
excerpts serves both. What must NOT change is the consent check: each prompt
still asks, before and after its model call, whether the snapshot it carries
is current (D10).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

import src.domains.briefing.llm as llm
import src.domains.briefing.service as service_module
import src.domains.briefing.sms_context as sms_context
from src.domains.briefing.schemas import CardSection, CardStatus, SmsData
from src.domains.briefing.service import BriefingService
from src.domains.sms.summary import SmsSignal
from tests.unit.domains.briefing.page_load_harness import full_payloads, make_user

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)


def _signal(owner: UUID) -> SmsSignal:
    return SmsSignal(
        timezone="Europe/Paris",
        total=12,
        window_total=3,
        window_start=NOW - timedelta(hours=24),
        as_of=NOW,
        latest_at=NOW,
        owner=owner,
        revision=0,
        stamp="3:2026-10-28T09:00:00Z",
        messages=[],
    )


def _cards_with_sms() -> Any:
    payloads = full_payloads()
    sections = {
        name: CardSection(status=CardStatus.OK, data=data, generated_at=NOW)
        for name, data in payloads.items()
    }
    sections["sms"] = CardSection(
        status=CardStatus.OK,
        data=SmsData(total=12, window_total=3, window_start=NOW, as_of=NOW, latest_at=NOW),
        generated_at=NOW,
    )
    return service_module.CardsBundle(**sections)


@pytest.fixture
def quiet_collaborators(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    invoke = AsyncMock(return_value=("Bonjour.", None))
    monkeypatch.setattr(llm, "_invoke_and_track", invoke)
    monkeypatch.setattr(llm, "_resolve_personality", AsyncMock(return_value=""))
    monkeypatch.setattr(llm, "_resolve_user_model_block", AsyncMock(return_value=""))
    monkeypatch.setattr(sms_context, "record_surface_consultations", lambda **_: None)
    monkeypatch.setattr(BriefingService, "_record_cards_turn", AsyncMock(return_value=None))
    return invoke


async def test_text_build_reads_sms_once(
    monkeypatch: pytest.MonkeyPatch, quiet_collaborators: AsyncMock
) -> None:
    reads: list[bool] = []

    async def read_signal(owner: UUID, *, include_bodies: bool = True, on_read: Any = None):
        reads.append(include_bodies)
        if on_read is not None:
            on_read()
        return _signal(owner)

    monkeypatch.setattr(sms_context, "read_sms_signal", read_signal)
    monkeypatch.setattr(llm, "sms_signal_current", AsyncMock(return_value=True))
    user = make_user()

    text = await BriefingService(user).build_text(cards=_cards_with_sms())  # type: ignore[arg-type]

    assert reads == [True]  # one read, with the excerpts the synthesis needs
    assert text.greeting.text == "Bonjour."
    assert text.synthesis is not None
    prompts = [call.kwargs["rendered"] for call in quiet_collaborators.await_args_list]
    assert len(prompts) == 2 and all('"dated_count":3' in prompt for prompt in prompts)


async def test_sms_revoked_between_prompts_drops_text(
    monkeypatch: pytest.MonkeyPatch, quiet_collaborators: AsyncMock
) -> None:
    """Consent withdrawn after the read: neither prompt reaches a model with it."""
    monkeypatch.setattr(
        sms_context, "read_sms_signal", AsyncMock(side_effect=lambda owner, **_: _signal(owner))
    )
    monkeypatch.setattr(llm, "sms_signal_current", AsyncMock(return_value=False))
    user = make_user()

    text = await BriefingService(user).build_text(cards=_cards_with_sms())  # type: ignore[arg-type]

    quiet_collaborators.assert_not_awaited()
    assert text.synthesis is None
    assert text.greeting.text  # the fallback greeting, never an empty page


async def test_unexpected_sms_failure_leaves_the_text_without_sms(
    monkeypatch: pytest.MonkeyPatch, quiet_collaborators: AsyncMock
) -> None:
    """A read failing for an unforeseen reason never fails ``/synthesis``: no SMS in the prompts."""
    monkeypatch.setattr(
        sms_context, "read_sms_signal", AsyncMock(side_effect=ValueError("bad row"))
    )
    monkeypatch.setattr(llm, "sms_signal_current", AsyncMock(return_value=True))

    text = await BriefingService(make_user()).build_text(cards=_cards_with_sms())  # type: ignore[arg-type]

    assert text.greeting.text == "Bonjour."
    prompts = [call.kwargs["rendered"] for call in quiet_collaborators.await_args_list]
    assert prompts and not any("dated_count" in prompt for prompt in prompts)


async def test_no_sms_card_reads_nothing(
    monkeypatch: pytest.MonkeyPatch, quiet_collaborators: AsyncMock
) -> None:
    read = AsyncMock()
    monkeypatch.setattr(sms_context, "read_sms_signal", read)
    cards = _cards_with_sms().model_copy(
        update={"sms": CardSection(status=CardStatus.HIDDEN, generated_at=NOW)}
    )

    await BriefingService(make_user()).build_text(cards=cards)  # type: ignore[arg-type]

    read.assert_not_awaited()
