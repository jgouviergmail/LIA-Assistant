"""What a push wake brings to the heartbeat decision (ADR-261).

- the Gmail preview NEVER advances an anchor (a refused wake must not swallow
  mail the next tick would have seen);
- the aggregator consumes the wake's messages and advances the anchor only
  then; without a wake it keeps the delta fast-path;
- calendar changes are merged (deduplicated) into the upcoming events;
- the FRESH line names the provider.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.heartbeat import wake_context
from src.domains.heartbeat.wake_context import (
    fetch_mail_metadata,
    fresh_section,
    gmail_delta_preview,
    merge_wake_events,
    wake_or_delta_messages,
)
from src.domains.push_channels.wake import WakePayload

pytestmark = pytest.mark.unit


def _wake(provider: str, **kwargs: object) -> WakePayload:
    return WakePayload(
        user_id=uuid.uuid4(), provider=provider, enqueued_at=datetime.now(UTC), **kwargs
    )


async def test_gmail_preview_lists_ids_without_storing_any_anchor() -> None:
    client = AsyncMock()
    client.get_history = AsyncMock(
        return_value={
            "historyId": "500",
            "history": [
                {"messagesAdded": [{"message": {"id": "m1"}}, {"message": {"id": "m2"}}]},
                {"messagesAdded": [{"message": {"id": "m1"}}]},
            ],
        }
    )
    with patch.object(wake_context, "advance_gmail_anchor", AsyncMock()) as advance:
        ids, new_anchor = await gmail_delta_preview(client, "400")
    assert (ids, new_anchor) == (["m1", "m2"], "500")
    client.get_history.assert_awaited_once_with(start_history_id="400")
    advance.assert_not_awaited()


async def test_gmail_preview_fails_open() -> None:
    client = AsyncMock()
    client.get_history = AsyncMock(side_effect=RuntimeError("404 expired"))
    assert await gmail_delta_preview(client, "400") == ([], None)


async def test_metadata_fetch_is_bounded_and_tolerant() -> None:
    client = AsyncMock()
    calls: list[str] = []

    async def _get(message_id: str, **_: object) -> dict | None:
        calls.append(message_id)
        if message_id == "bad":
            raise RuntimeError("boom")
        return {"id": message_id}

    client.get_message = AsyncMock(side_effect=_get)
    ids = ["bad"] + [f"m{i}" for i in range(20)]
    messages = await fetch_mail_metadata(client, ids)
    assert len(calls) == 10  # PUSH_WAKE_MAIL_MAX_MESSAGES
    assert [m["id"] for m in messages] == [f"m{i}" for i in range(9)]


async def test_wake_messages_replace_the_delta_and_advance_the_anchor() -> None:
    wake = _wake(
        "google_gmail",
        messages=({"id": "m1", "from": "a"}, {"id": "m2", "from": "b"}),
        new_history_id="777",
    )
    client = AsyncMock()
    with (
        patch.object(wake_context, "advance_gmail_anchor", AsyncMock()) as advance,
        patch("src.domains.heartbeat.gmail_delta.delta_messages_or_none", AsyncMock()) as delta,
    ):
        messages = await wake_or_delta_messages(wake, client, wake.user_id, max_emails=1)
    assert messages == [{"id": "m1", "from": "a"}]
    advance.assert_awaited_once_with(wake.user_id, "777")
    delta.assert_not_awaited()


async def test_without_a_wake_the_delta_fast_path_is_kept() -> None:
    client = AsyncMock()
    with (
        patch.object(wake_context, "advance_gmail_anchor", AsyncMock()) as advance,
        patch(
            "src.domains.heartbeat.gmail_delta.delta_messages_or_none",
            AsyncMock(return_value=[{"id": "d1"}]),
        ) as delta,
    ):
        messages = await wake_or_delta_messages(None, client, uuid.uuid4(), max_emails=5)
    assert messages == [{"id": "d1"}]
    advance.assert_not_awaited()
    delta.assert_awaited_once()


async def test_a_calendar_wake_never_touches_the_mail_path() -> None:
    wake = _wake("google_calendar", events=({"id": "e1"},))
    with patch(
        "src.domains.heartbeat.gmail_delta.delta_messages_or_none", AsyncMock(return_value=None)
    ):
        assert await wake_or_delta_messages(wake, AsyncMock(), wake.user_id, 5) is None


def test_calendar_events_are_merged_and_deduplicated() -> None:
    wake = _wake("google_calendar", events=({"id": "e2", "summary": "new"}, {"id": "e1"}))
    merged = merge_wake_events(wake, [{"id": "e1", "summary": "old"}])
    assert merged == [{"id": "e1", "summary": "old"}, {"id": "e2", "summary": "new"}]
    assert merge_wake_events(None, [{"id": "e1"}]) == [{"id": "e1"}]
    assert merge_wake_events(_wake("google_gmail"), [{"id": "e1"}]) == [{"id": "e1"}]


def test_fresh_section_names_the_provider() -> None:
    assert "mail" in (fresh_section("google_gmail") or "")
    assert "calendar" in (fresh_section("google_calendar") or "")
    assert fresh_section(None) is None
    assert fresh_section("google_drive") is None


def test_the_fresh_sentence_comes_from_the_versioned_prompt_file() -> None:
    """A prompt fragment never lives in a ``.py`` (CLAUDE.md).

    The module holds the EVENT ("new mail arrived minutes ago"); the sentence
    around it — including the rule that an interruption still has to earn
    itself — is the versioned file's, so it can be reworded without a deploy
    of code and reviewed as a prompt.
    """
    from src.domains.agents.prompts.prompt_loader import load_prompt

    template = load_prompt("heartbeat_wake_fresh_prompt")
    assert "{trigger}" in template
    rendered = fresh_section("google_gmail") or ""
    assert rendered == template.strip().format(trigger="new mail arrived minutes ago")
    # The file, not the module, carries the behavioural clause.
    assert "earn itself" in rendered
