"""Delivery wording and sender billing; state transitions are proven on PostgreSQL."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage, BaseMessage

from src.domains.peers.models import PeerMessage
from src.domains.users.models import User
from src.infrastructure.llm.usage_metadata import UsageTokens
from src.infrastructure.scheduler import peer_message_delivery as delivery

SENDER_ID, RECIPIENT_ID, CONNECTION_ID = uuid4(), uuid4(), uuid4()


def _message(content: str = "Demande-lui comment il va") -> PeerMessage:
    return PeerMessage(
        id=uuid4(),
        connection_id=CONNECTION_ID,
        sender_id=SENDER_ID,
        recipient_id=RECIPIENT_ID,
        content=content,
        status="delivering",
        attempts=0,
    )


def _user(user_id: UUID, language: str, full_name: str) -> User:
    return User(id=user_id, language=language, full_name=full_name, is_active=True)


@pytest.mark.unit
class TestGenerateDeliveryText:
    async def test_real_template_formats_with_every_ingredient_slot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The REAL prompt file formats — a renamed placeholder fails here.

        Every ingredient is a known mark rather than a lookup: read for real,
        the four builders reached whatever database the environment named —
        the developer's own, from the unit suite — and, each swallowed as
        best-effort, a missing one looked exactly like a present one.
        """
        captured: dict[str, object] = {}

        @asynccontextmanager
        async def _no_database() -> AsyncIterator[object]:
            yield object()

        monkeypatch.setattr(delivery, "get_db_context", _no_database)

        async def _invoke(
            *, messages: list[BaseMessage], llm_type: str, user_id: str, **kwargs: object
        ) -> AIMessage:
            captured.update(messages=messages, llm_type=llm_type, user_id=user_id)
            return AIMessage(
                content="Ton père demande comment tu vas.",
                usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            )

        with (
            patch("src.infrastructure.llm.get_llm", return_value=object()),
            patch(
                "src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation",
                new=AsyncMock(side_effect=_invoke),
            ),
            patch(
                "src.domains.personalities.service.PersonalityService.get_prompt_instruction_for_user",
                new=AsyncMock(return_value="PERSONALITY-MARK"),
            ),
            patch(
                "src.domains.psyche.service.build_psyche_prompt_block",
                new=AsyncMock(return_value="PSYCHE-MARK"),
            ),
            patch(
                "src.domains.journals.portrait_builder.build_journal_user_model_block",
                new=AsyncMock(return_value="PORTRAIT-MARK"),
            ),
            patch(
                "src.domains.agents.middleware.memory_injection.build_psychological_profile",
                new=AsyncMock(return_value=("MEMORY-MARK", None, None)),
            ),
        ):
            text, usage, _model, _records = await delivery._generate_delivery_text(
                _message(), _user(SENDER_ID, "fr", "Jerome"), _user(RECIPIENT_ID, "it", "Marie"), 3
            )
        assert text == "Ton père demande comment tu vas."
        assert (usage.prompt, usage.completion) == (100, 20)
        messages = captured["messages"]
        assert isinstance(messages, list) and isinstance(messages[0], BaseMessage)
        system = messages[0].content
        assert isinstance(system, str)
        assert "Jerome" in system
        assert "<<<RELAYED_MESSAGE_START>>>" in system
        assert "Demande-lui comment il va" in system
        assert "Italian" in system  # recipient language name
        for mark in ("PERSONALITY-MARK", "PSYCHE-MARK", "PORTRAIT-MARK", "MEMORY-MARK"):
            assert mark in system, mark
        assert captured["llm_type"] == "peer_message_delivery"
        assert captured["user_id"] == str(SENDER_ID)  # spec §9: the sender owns the call


@pytest.mark.unit
async def test_successful_generation_accounts_every_token_to_sender_before_dispatch() -> None:
    generated = delivery._DeliveryText("A rendition", UsageTokens(100, 25, 12, 7), "priced-model")
    message = _message()
    with (
        patch.object(delivery, "_generate_delivery_text", AsyncMock(return_value=generated)),
        patch(
            "src.infrastructure.proactive.tracking.track_proactive_tokens", new_callable=AsyncMock
        ) as track,
    ):
        text = await delivery._generate_and_account(
            message, _user(SENDER_ID, "fr", "Sender"), _user(RECIPIENT_ID, "en", "Recipient"), 2
        )
    assert text == generated.text
    args = track.await_args
    assert args is not None
    assert args.kwargs["user_id"] == SENDER_ID
    assert args.kwargs["tokens_in"] == 100 and args.kwargs["tokens_out"] == 25
    assert args.kwargs["tokens_cache"] == 12 and args.kwargs["tokens_cache_write"] == 7
    assert args.kwargs["model_name"] == "priced-model"
    assert args.kwargs["source"] == "scheduled"
