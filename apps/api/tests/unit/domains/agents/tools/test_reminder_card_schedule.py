"""The real reminder tool projects the stored schedule into its registry card."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.i18n_cards import card_label
from src.core.recurrence import RecurrenceSpec, describe
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.reminder_card import ReminderCard
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.reminder_tools import list_reminders_tool
from src.domains.reminders.models import Reminder
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


async def _list_rows(rows: list[Reminder], language: str = "en") -> UnifiedToolOutput:
    runtime = make_tool_runtime(
        user_id=rows[0].user_id,
        thread_id=str(uuid4()),
        side_channel_queue=object(),
        store=MagicMock(),
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    with (
        patch("src.infrastructure.database.session.get_db_context", session),
        patch("src.domains.reminders.service.ReminderService") as service,
        patch(
            "src.domains.agents.tools.runtime_helpers.get_user_preferences",
            AsyncMock(return_value=("Europe/Paris", language, language)),
        ),
    ):
        service.return_value.list_pending_for_user = AsyncMock(return_value=rows)
        assert list_reminders_tool.coroutine is not None
        result = await list_reminders_tool.coroutine(
            runtime=runtime, user_timezone="Europe/Paris", locale=language
        )
    assert isinstance(result, UnifiedToolOutput)
    return result


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
async def test_repeating_reminder_keeps_its_actual_schedule_in_the_card(language: str) -> None:
    user_id = uuid4()
    spec = RecurrenceSpec.model_validate(
        {
            "freq": "weekly",
            "byweekday": [1, 5],
            "anchor_date": "2026-10-05",
            "times": {"at": [{"hour": 9, "minute": 0}]},
            "end": {"kind": "after_count", "after_count": 12},
        }
    )
    row = Reminder(
        id=uuid4(),
        user_id=user_id,
        content="Water the plants",
        trigger_at=datetime(2026, 10, 5, 7, tzinfo=UTC),
        created_at=datetime(2026, 10, 3, tzinfo=UTC),
        recurrence=spec.model_dump(mode="json"),
        status="pending",
        user_timezone="Europe/Paris",
    )
    result = await _list_rows([row], language)
    assert result.success
    item = next(iter(result.registry_updates.values()))
    sentence = describe(spec, language)
    assert item.payload.get("schedule_human") == sentence
    markup = ReminderCard().render(item.payload, RenderContext(language=language))
    assert sentence in markup
    assert "Europe/Paris" in markup
    assert item.payload["status"] == "pending"


async def test_invalid_stored_schedule_cannot_hide_another_pending_reminder() -> None:
    user_id = uuid4()
    rows = [
        Reminder(
            id=uuid4(),
            user_id=user_id,
            content=f"Reminder {index}",
            trigger_at=datetime(2026, 10, 5, 7, tzinfo=UTC),
            created_at=datetime(2026, 10, 3, tzinfo=UTC),
            user_timezone="Europe/Paris",
            status="pending",
            recurrence={},
        )
        for index in range(2)
    ]
    rows[1].recurrence = {
        "freq": "daily",
        "anchor_date": "2026-10-05",
        "times": {"at": [{"hour": 9, "minute": 0}]},
    }
    result = await _list_rows(rows)
    assert result.success
    assert len(result.registry_updates) == 2
    bad = next(
        item for item in result.registry_updates.values() if item.payload["id"] == str(rows[0].id)
    )
    assert bad.payload["schedule_human"] == card_label("unavailable", "en")
    good = next(
        item for item in result.registry_updates.values() if item.payload["id"] == str(rows[1].id)
    )
    assert good.payload["schedule_human"] == describe(rows[1].recurrence_spec, "en")
    assert "Reminder 0" in ReminderCard().render(bad.payload, RenderContext(language="en"))


async def test_registry_does_not_overwrite_reminders_with_the_same_uuid_prefix() -> None:
    user_id = uuid4()
    rows = [
        Reminder(
            id=UUID(f"12345678-0000-4000-8000-{index:012d}"),
            user_id=user_id,
            content=f"Reminder {index}",
            trigger_at=datetime(2026, 10, 5, 7, tzinfo=UTC),
            created_at=datetime(2026, 10, 3, tzinfo=UTC),
            user_timezone="Europe/Paris",
            status="pending",
            recurrence={
                "freq": "daily",
                "anchor_date": "2026-10-05",
                "times": {"at": [{"hour": 9, "minute": 0}]},
            },
        )
        for index in range(2)
    ]
    result = await _list_rows(rows)
    assert result.success
    assert len(result.registry_updates) == 2
    assert {item.payload["id"] for item in result.registry_updates.values()} == {
        str(row.id) for row in rows
    }
