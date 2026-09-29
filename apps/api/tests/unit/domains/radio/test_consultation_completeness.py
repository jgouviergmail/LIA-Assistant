"""A radio read remains visible when it is empty, fails or is cancelled."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from src.domains.agents.effects import treatment_recorder as recorder_module
from src.domains.agents.effects.treatments import Treatment
from src.domains.radio import adapters

pytestmark = pytest.mark.unit
USER = UUID("00000000-0000-4000-8000-0000000000d1")
NOW = datetime(2026, 9, 29, tzinfo=UTC)


@pytest.fixture
def filed(monkeypatch: pytest.MonkeyPatch) -> list[Treatment]:
    rows: list[Treatment] = []

    async def flush(batch: list[Treatment]) -> None:
        rows.extend(batch)

    monkeypatch.setattr(recorder_module, "_flush", flush)
    return rows


@pytest.mark.parametrize("failure", [None, RuntimeError, asyncio.CancelledError])
async def test_notification_poll_records_empty_failed_and_cancelled_reads(
    monkeypatch: pytest.MonkeyPatch, filed: list[Treatment], failure: type[BaseException] | None
) -> None:
    async def read(*args: object, **kwargs: object) -> list[object]:
        if failure:
            raise failure()
        return []

    monkeypatch.setattr(adapters, "read_flash_notes", read)
    source = adapters.NotificationFlashes(USER, "radio_audit")
    if failure:
        with pytest.raises(failure):
            await source.since(NOW)
    else:
        assert await source.since(NOW) == []
    [row] = filed
    assert (row.tool_name, row.user_id, row.run_id, row.source) == (
        "radio:notifications",
        str(USER),
        "radio_audit",
        "user",
    )
    assert row.outcome == ("failed" if failure else "ok")


@pytest.mark.parametrize("failure", [None, RuntimeError, asyncio.CancelledError])
async def test_reading_news_material_is_a_consultation_even_without_stories(
    monkeypatch: pytest.MonkeyPatch, filed: list[Treatment], failure: type[BaseException] | None
) -> None:
    async def read(*args: object, **kwargs: object) -> list[object]:
        if failure:
            raise failure()
        return []

    monkeypatch.setattr(adapters, "news_candidates", read)
    source = adapters.NewsDesk(
        user_id=USER, run_id="radio_audit", disabled_feeds=frozenset(), clock=lambda: NOW
    )
    if failure:
        with pytest.raises(failure):
            await source.candidates(heard_keys=frozenset(), heard_stories=frozenset())
    else:
        assert await source.candidates(heard_keys=frozenset(), heard_stories=frozenset()) == []
    [row] = filed
    assert (row.tool_name, row.run_id, row.source) == ("radio:news", "radio_audit", "user")
    assert row.outcome == ("failed" if failure else "ok")
