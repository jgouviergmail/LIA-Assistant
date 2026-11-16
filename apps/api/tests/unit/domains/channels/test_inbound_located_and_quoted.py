"""A shared point and a reply reach the turn whole (Telegram lot 8).

A pin was dropped (the bot answered nothing) and a reply reached LIA as its
words alone. The person's position is now the turn's consented geolocation —
« near me » reads it as it reads the browser's — and stated in words; a place
is stated as the place it names; a reply carries the message it answers,
except an answer to a question, which the question already frames.

Through the real gateway, the engine substituted (as ``test_inbound_handler``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.channels.abstractions import ChannelInboundMessage, ChannelLocation
from src.domains.channels.inbound_handler import InboundMessageHandler
from src.domains.channels.message_words import located_words, with_quote
from src.domains.channels.models import ChannelType
from tests.fixtures.instruction_runtime import instruction_runtime

pytestmark = pytest.mark.unit

#: The person's language — never the instance's, so nothing passes by falling back.
_PERSON = next(code for code in ("it", "es") if code != settings.default_language)


def _message(text: str | None = None, **extra: Any) -> ChannelInboundMessage:
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="12345",
        text=text,
        message_id="5",
        raw_data={},
        **extra,
    )


async def _turn(message: ChannelInboundMessage, **kwargs: Any) -> dict[str, Any]:
    """Run the person's turn; what the engine was asked to answer."""
    seen: list[dict[str, Any]] = []

    async def response(**engine: Any) -> AsyncIterator[ChatStreamChunk]:
        seen.append(engine)
        yield ChatStreamChunk(type="token", content="ok")

    owner = uuid4()
    sender = AsyncMock(send_message=AsyncMock(return_value="1"), send_typing_indicator=AsyncMock())
    with (
        instruction_runtime(owner),
        patch(
            "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
            AsyncMock(return_value=kwargs.get("pending_hitl")),
        ),
        patch("src.domains.agents.api.service.AgentService") as service,
    ):
        service.return_value.stream_chat_response = MagicMock(side_effect=response)
        await InboundMessageHandler(sender=sender).handle(
            message=message,
            user_id=owner,
            user_language=_PERSON,
            user_timezone="Europe/Rome",
            user_memory_enabled=True,
            user_journals_enabled=False,
            user_psyche_enabled=False,
            user_voice_enabled=False,
            user_execution_mode="pipeline",
            conversation_id="conv-1",
            pending_hitl=kwargs.get("pending_hitl"),
            hitl_decision=kwargs.get("hitl_decision"),
        )
    [engine] = seen
    return engine


async def test_a_shared_position_is_the_turn_s_position() -> None:
    position = ChannelLocation(45.46427, 9.18951, accuracy_m=20.0)

    engine = await _turn(_message(location=position))

    assert engine["user_message"] == located_words(position, _PERSON)
    geolocation = engine["browser_context"].geolocation
    assert (geolocation.lat, geolocation.lon, geolocation.accuracy) == (45.46427, 9.18951, 20.0)


async def test_a_shared_place_is_named_never_taken_for_the_person_s_position() -> None:
    place = ChannelLocation(45.46421, 9.19040, title="Duomo", address="Piazza del Duomo")

    engine = await _turn(_message(location=place))

    assert engine["user_message"] == located_words(place, _PERSON)
    assert engine["browser_context"] is None


async def test_a_reply_carries_the_message_it_answers() -> None:
    engine = await _turn(_message("and this one?", quoted_text="2. Lyon"))

    assert engine["user_message"] == with_quote("and this one?", "2. Lyon")
    assert engine["browser_context"] is None


#: A question pending in the discussion, as ``HITLStore.get_pending`` returns it.
_ASKED = {"action_requests": [{"type": "plan_approval"}], "count": 1, "run_id": "run-asked"}


@pytest.mark.parametrize(
    "answer",
    [{"pending_hitl": _ASKED}, {"pending_hitl": _ASKED, "hitl_decision": {"action": "confirm"}}],
    ids=["typed", "pressed"],
)
async def test_an_answer_to_a_question_is_its_words_alone(answer: dict[str, Any]) -> None:
    """The question frames it: a quote of that question would be read as the answer."""
    engine = await _turn(_message("yes", quoted_text="Shall I send it?"), **answer)

    assert engine["user_message"] == "yes"
    assert engine["original_run_id"] == "run-asked"
