"""Delivery engine tests (Lot 4) — revalidation, §9 attribution, taxonomy.

`_generate_delivery_text` is exercised once against the REAL prompt template
(placeholders proven); `deliver_claimed_message` is tested with the generation
patched — its oracles are the guard codes, the sender-side token attribution,
the dispatch targets and the retry taxonomy.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.peers.models import PeerConnectionStatus
from src.infrastructure.scheduler import peer_message_delivery as delivery

SENDER_ID = uuid4()
RECIPIENT_ID = uuid4()
CONNECTION_ID = uuid4()


def _message(content="Demande-lui comment il va"):
    return SimpleNamespace(
        id=uuid4(),
        connection_id=CONNECTION_ID,
        sender_id=SENDER_ID,
        recipient_id=RECIPIENT_ID,
        content=content,
        status="delivering",
        attempts=0,
    )


def _user(user_id, language="fr", full_name="Someone", is_active=True):
    return SimpleNamespace(
        id=user_id,
        language=language,
        full_name=full_name,
        is_active=is_active,
        deleted_at=None,
    )


def _repo(connection_status=PeerConnectionStatus.ACCEPTED.value, blocked=False):
    repo = AsyncMock()
    repo.get_by_id.return_value = SimpleNamespace(id=CONNECTION_ID, status=connection_status)
    repo.has_block_between.return_value = blocked
    repo.count_messages_today_for_pair.return_value = 3
    repo.mark_message_failed.return_value = "pending"
    repo.mark_message_delivered.return_value = True
    return repo


def _db(users: dict):
    db = AsyncMock()

    async def _get(model, key):
        return users.get(key)

    db.get.side_effect = _get
    return db


def _users():
    return {
        SENDER_ID: _user(SENDER_ID, "fr", "Jerome"),
        RECIPIENT_ID: _user(RECIPIENT_ID, "it", "Marie"),
    }


@pytest.fixture
def not_blocked():
    with patch(
        "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
        new=AsyncMock(return_value=False),
    ):
        yield


@pytest.mark.unit
class TestGenerateDeliveryText:
    async def test_real_template_formats_with_every_ingredient_slot(self):
        """The REAL prompt file formats — a renamed placeholder fails here."""
        captured: dict = {}

        async def _invoke(**kwargs):
            captured["messages"] = kwargs["messages"]
            captured["llm_type"] = kwargs["llm_type"]
            captured["user_id"] = kwargs["user_id"]
            return SimpleNamespace(
                text="Ton père demande comment tu vas.",
                usage_metadata={"input_tokens": 100, "output_tokens": 20},
            )

        with (
            patch("src.infrastructure.llm.get_llm", return_value=object()),
            patch(
                "src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation",
                new=AsyncMock(side_effect=_invoke),
            ),
        ):
            text, tin, tout, _tcache = await delivery._generate_delivery_text(
                _message(), _user(SENDER_ID, "fr", "Jerome"), _user(RECIPIENT_ID, "it", "Marie"), 3
            )
        assert text == "Ton père demande comment tu vas."
        assert (tin, tout) == (100, 20)
        system = captured["messages"][0].content
        assert "Jerome" in system
        assert "<<<RELAYED_MESSAGE_START>>>" in system
        assert "Demande-lui comment il va" in system
        assert "Italian" in system  # recipient language name
        assert captured["llm_type"] == "peer_message_delivery"
        assert captured["user_id"] == str(SENDER_ID)  # spec §9: the sender owns the call


@pytest.mark.unit
class TestDeliverClaimedMessage:
    async def test_blocked_pair_cancels_and_notifies_sender(self, not_blocked):
        repo = _repo(blocked=True)
        notify = AsyncMock()
        with (
            patch(
                "src.infrastructure.scheduler.peer_message_delivery.PeersRepository",
                return_value=repo,
            ),
            patch("src.infrastructure.scheduler.peer_message_delivery._notify_sender", new=notify),
        ):
            outcome = await delivery.deliver_claimed_message(_message(), _db(_users()))
        assert outcome == "cancelled_blocked"
        repo.cancel_message.assert_awaited_once()
        notify.assert_awaited_once()  # sender told neutrally

    @pytest.mark.parametrize("expired", [None, "", "   "])
    async def test_an_expired_directive_is_cancelled_instead_of_relayed(self, expired, not_blocked):
        """ADR-186 retention meets an undelivered message.

        `expires_at` is stamped at ENQUEUE and the reaper clears texts on every
        status, so a message deferred past its horizon (a recipient who never
        resolves a HITL, a suspended account) loses its directive while still
        pending — and the reaper runs immediately BEFORE the claim in the same
        sweep. Relaying "" would make the recipient's assistant invent a
        message and tell the sender it was delivered. It must die instead.
        """
        repo = _repo()
        notify = AsyncMock()
        generate = AsyncMock()
        with (
            patch(
                "src.infrastructure.scheduler.peer_message_delivery.PeersRepository",
                return_value=repo,
            ),
            patch("src.infrastructure.scheduler.peer_message_delivery._notify_sender", new=notify),
            patch(
                "src.infrastructure.scheduler.peer_message_delivery._generate_delivery_text",
                new=generate,
            ),
        ):
            outcome = await delivery.deliver_claimed_message(_message(expired), _db(_users()))

        assert outcome == "cancelled_content_expired"
        repo.cancel_message.assert_awaited_once()
        notify.assert_awaited_once()  # the sender learns it never left
        generate.assert_not_awaited()  # no LLM call, no invented message
        repo.mark_message_delivered.assert_not_awaited()

    async def test_sender_at_quota_cancels(self):
        repo = _repo()
        with (
            patch(
                "src.infrastructure.scheduler.peer_message_delivery.PeersRepository",
                return_value=repo,
            ),
            patch(
                "src.infrastructure.scheduler.peer_message_delivery._notify_sender", new=AsyncMock()
            ),
            patch(
                "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
                new=AsyncMock(return_value=True),
            ),
        ):
            outcome = await delivery.deliver_claimed_message(_message(), _db(_users()))
        assert outcome == "cancelled_sender_blocked"  # spec §9d

    async def test_success_tracks_tokens_to_the_sender_then_delivers(self, not_blocked):
        repo = _repo()
        dispatch = AsyncMock()
        track = AsyncMock()
        message = _message()
        with (
            patch(
                "src.infrastructure.scheduler.peer_message_delivery.PeersRepository",
                return_value=repo,
            ),
            patch(
                "src.infrastructure.scheduler.peer_message_delivery._generate_delivery_text",
                new=AsyncMock(return_value=("Livré !", 100, 20, 0)),
            ),
            patch(
                "src.infrastructure.scheduler.peer_message_delivery.NotificationDispatcher"
            ) as dispatcher_cls,
            patch("src.infrastructure.proactive.tracking.track_proactive_tokens", new=track),
        ):
            dispatcher_cls.return_value.dispatch = dispatch
            outcome = await delivery.deliver_claimed_message(message, _db(_users()))

        assert outcome == "delivered"
        # §9 oracle (a)+(b): tokens booked to the SENDER, never the recipient.
        assert track.await_args.kwargs["user_id"] == SENDER_ID
        assert track.await_args.kwargs["task_type"] == "peer_message"
        # Recipient got the relayed message; sender got the confirmation.
        recipients = [call.kwargs["user"].id for call in dispatch.await_args_list]
        assert recipients == [RECIPIENT_ID, SENDER_ID]
        assert dispatch.await_args_list[0].kwargs["task_type"] == "peer_message"
        repo.mark_message_delivered.assert_awaited_once()

    async def test_generation_failure_retries_without_sender_noise(self, not_blocked):
        repo = _repo()
        repo.mark_message_failed.return_value = "pending"
        notify = AsyncMock()
        with (
            patch(
                "src.infrastructure.scheduler.peer_message_delivery.PeersRepository",
                return_value=repo,
            ),
            patch(
                "src.infrastructure.scheduler.peer_message_delivery._generate_delivery_text",
                new=AsyncMock(side_effect=RuntimeError("llm down")),
            ),
            patch("src.infrastructure.scheduler.peer_message_delivery._notify_sender", new=notify),
        ):
            outcome = await delivery.deliver_claimed_message(_message(), _db(_users()))
        assert outcome == "pending"  # will retry at the next sweep
        repo.mark_message_failed.assert_awaited_once()
        assert repo.mark_message_failed.await_args.args[1] == "llm_error"
        notify.assert_not_awaited()  # retries are silent for the sender

    async def test_exhausted_attempts_notify_the_sender(self, not_blocked):
        repo = _repo()
        repo.mark_message_failed.return_value = "failed"
        notify = AsyncMock()
        with (
            patch(
                "src.infrastructure.scheduler.peer_message_delivery.PeersRepository",
                return_value=repo,
            ),
            patch(
                "src.infrastructure.scheduler.peer_message_delivery._generate_delivery_text",
                new=AsyncMock(side_effect=RuntimeError("llm down")),
            ),
            patch("src.infrastructure.scheduler.peer_message_delivery._notify_sender", new=notify),
        ):
            outcome = await delivery.deliver_claimed_message(_message(), _db(_users()))
        assert outcome == "failed"
        notify.assert_awaited_once()

    async def test_max_attempts_comes_from_settings(self, not_blocked):
        """Threshold read from settings — never hardcoded (house rule)."""
        repo = _repo()
        with (
            patch(
                "src.infrastructure.scheduler.peer_message_delivery.PeersRepository",
                return_value=repo,
            ),
            patch(
                "src.infrastructure.scheduler.peer_message_delivery._generate_delivery_text",
                new=AsyncMock(side_effect=RuntimeError("x")),
            ),
            patch(
                "src.infrastructure.scheduler.peer_message_delivery._notify_sender", new=AsyncMock()
            ),
        ):
            await delivery.deliver_claimed_message(_message(), _db(_users()))
        assert (
            repo.mark_message_failed.await_args.kwargs["max_attempts"]
            == settings.peers_delivery_max_attempts
        )
