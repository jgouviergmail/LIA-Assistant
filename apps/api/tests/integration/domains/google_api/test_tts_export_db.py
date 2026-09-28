"""The consumption exports see every paid synthesis once — on real PostgreSQL (ADR-324).

A chat answer read aloud is on its bubble AND on its run's row; a radio
session is on its row alone. The summary reads the runs, so both count and
neither twice; the detail lists the bubble for the chat (provider, model,
dollars) and the run's row only where no bubble carries its speech.
"""

from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal

import pytest
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.chat.models import MessageTokenSummary
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.google_api.export_service import (
    export_consumption_summary_csv,
    export_tts_usage_csv,
)
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def _rows(response: StreamingResponse) -> list[dict[str, str]]:
    chunks = [chunk async for chunk in response.body_iterator]
    body = "".join(c if isinstance(c, str) else bytes(c).decode() for c in chunks)
    return list(csv.DictReader(io.StringIO(body.lstrip("\ufeff"))))


async def test_each_billed_synthesis_is_exported_once(async_session: AsyncSession) -> None:
    owner = User(email=f"tts-export-{uuid.uuid4().hex[:8]}@test.local", hashed_password="x")
    async_session.add(owner)
    await async_session.flush()
    conversation = Conversation(user_id=owner.id)
    async_session.add(conversation)
    await async_session.flush()
    chat_run, radio_run, quiet_run = (f"run-{uuid.uuid4().hex}" for _ in range(3))
    async_session.add_all(
        [
            MessageTokenSummary(
                user_id=owner.id,
                session_id="s",
                run_id=chat_run,
                conversation_id=conversation.id,
                tts_characters=400,
                tts_cost_eur=Decimal("0.006"),
            ),
            MessageTokenSummary(
                user_id=owner.id,
                session_id=radio_run,
                run_id=radio_run,
                tts_characters=2000,
                tts_cost_eur=Decimal("0.03"),
            ),
            MessageTokenSummary(user_id=owner.id, session_id="s", run_id=quiet_run),
            ConversationMessage(
                conversation_id=conversation.id,
                role="assistant",
                content="An answer read aloud.",
                message_metadata={"run_id": chat_run},
                tts_provider="openai",
                tts_model="tts-1",
                tts_characters=400,
                tts_cost_usd=Decimal("0.0066"),
                tts_cost_eur=Decimal("0.006"),
            ),
        ]
    )
    await async_session.flush()

    response, count = await export_tts_usage_csv(async_session, user_id=owner.id)
    detail = {row["run_id"]: row for row in await _rows(response)}

    assert count == 2 and set(detail) == {chat_run, radio_run}
    assert (detail[chat_run]["tts_provider"], detail[chat_run]["cost_usd"]) == ("openai", "0.0066")
    radio = detail[radio_run]
    assert (radio["tts_provider"], radio["message_id"], radio["cost_usd"]) == ("", "", "")
    assert (radio["characters"], radio["cost_eur"]) == ("2000", "0.03")

    response, _ = await export_consumption_summary_csv(async_session, user_id=owner.id)
    (summary,) = await _rows(response)
    assert (
        summary["total_tts_runs"],
        summary["total_tts_characters"],
        summary["total_tts_cost_eur"],
    ) == ("2", "2400", "0.036")
