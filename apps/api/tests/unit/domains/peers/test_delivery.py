"""Delivery engine tests (Lot 4) — revalidation, §9 attribution, taxonomy.

`_generate_delivery_text` is exercised once against the REAL prompt template
(placeholders proven); `deliver_claimed_message` is tested with the generation
patched — its oracles are the guard codes, the sender-side token attribution,
the dispatch targets and the retry taxonomy.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.peers.models import PeerConnectionStatus
from src.infrastructure.llm.usage_metadata import UsageTokens
from src.infrastructure.scheduler import peer_message_delivery as delivery
from tests.helpers.notifications import ScriptedChannels, scripted_dispatcher, sse_only

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
def accounting_session(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The session a failure is counted on: its own, never the claim's."""
    session = AsyncMock()

    @asynccontextmanager
    async def _context() -> AsyncIterator[AsyncMock]:
        yield session

    monkeypatch.setattr(delivery, "get_db_context", _context)
    return session


@pytest.fixture
def not_blocked():
    with patch(
        "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
        new=AsyncMock(return_value=False),
    ):
        yield


async def _deliver_through(
    channels: ScriptedChannels, repo: AsyncMock, *, track: AsyncMock | None = None
) -> str:
    """Deliver one message through the REAL dispatcher over scripted channels."""
    with (
        patch(
            "src.infrastructure.scheduler.peer_message_delivery.PeersRepository",
            return_value=repo,
        ),
        patch(
            "src.infrastructure.scheduler.peer_message_delivery._generate_delivery_text",
            new=AsyncMock(
                return_value=delivery._DeliveryText("Livré !", UsageTokens(100, 20, 0), "m")
            ),
        ),
        patch(
            "src.infrastructure.scheduler.peer_message_delivery.NotificationDispatcher",
            new=scripted_dispatcher(channels),
        ),
        patch(
            "src.infrastructure.proactive.tracking.track_proactive_tokens",
            new=track if track is not None else AsyncMock(),
        ),
    ):
        return await delivery.deliver_claimed_message(_message(), _db(_users()))


@pytest.mark.unit
class TestGenerateDeliveryText:
    async def test_real_template_formats_with_every_ingredient_slot(self, monkeypatch):
        """The REAL prompt file formats — a renamed placeholder fails here.

        Every ingredient is a known mark rather than a lookup: read for real,
        the four builders reached whatever database the environment named —
        the developer's own, from the unit suite — and, each swallowed as
        best-effort, a missing one looked exactly like a present one.
        """
        captured: dict = {}

        @asynccontextmanager
        async def _no_database() -> AsyncIterator[object]:
            yield object()

        monkeypatch.setattr(delivery, "get_db_context", _no_database)

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
        system = captured["messages"][0].content
        assert "Jerome" in system
        assert "<<<RELAYED_MESSAGE_START>>>" in system
        assert "Demande-lui comment il va" in system
        assert "Italian" in system  # recipient language name
        for mark in ("PERSONALITY-MARK", "PSYCHE-MARK", "PORTRAIT-MARK", "MEMORY-MARK"):
            assert mark in system, mark
        assert captured["llm_type"] == "peer_message_delivery"
        assert captured["user_id"] == str(SENDER_ID)  # spec §9: the sender owns the call


@pytest.mark.unit
@pytest.mark.usefixtures("accounting_session")
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

    async def test_a_cancel_is_committed_before_its_notice(self, not_blocked):
        """The cancel is the record, the sender's notice best-effort.

        Left pending, a notice whose archive failed in the database aborted the
        claim session's transaction, and the sweep's COMMIT rolled the cancel back
        in silence (measured on PostgreSQL): the message was claimed again ten
        minutes later, for ever.
        """
        events: list[str] = []
        repo = _repo(blocked=True)
        repo.cancel_message.side_effect = lambda *_args: events.append("cancel")
        db = _db(_users())
        db.commit.side_effect = lambda: events.append("commit")

        async def _notice(*_args: object) -> None:
            events.append("notice")

        with (
            patch(
                "src.infrastructure.scheduler.peer_message_delivery.PeersRepository",
                return_value=repo,
            ),
            patch(
                "src.infrastructure.scheduler.peer_message_delivery._notify_sender",
                new=_notice,
            ),
        ):
            outcome = await delivery.deliver_claimed_message(_message(), db)

        assert outcome == "cancelled_blocked"
        assert events == ["cancel", "commit", "notice"]

    async def test_the_model_is_asked_with_no_transaction_open(
        self, not_blocked, accounting_session
    ):
        """The claim session's reads are committed before the generation (ADR-304).

        Left open, the transaction sat ``idle in transaction`` for as long as the model
        answered: a pooled connection pinned by a wait, and since AC-028 a session the
        server ends past its idle bound.
        """
        events: list[str] = []
        repo = _repo()

        async def _count(*_args: object, **_kwargs: object) -> int:
            events.append("count")
            return 3

        repo.count_messages_today_for_pair.side_effect = _count
        db = _db(_users())
        db.commit.side_effect = lambda: events.append("commit")

        async def _generate(*_args: object) -> object:
            events.append("generate")
            raise RuntimeError("the model is down")

        with (
            patch(
                "src.infrastructure.scheduler.peer_message_delivery.PeersRepository",
                return_value=repo,
            ),
            patch(
                "src.infrastructure.scheduler.peer_message_delivery._generate_delivery_text",
                new=_generate,
            ),
        ):
            outcome = await delivery.deliver_claimed_message(_message(), db)

        assert outcome == "pending"
        assert events == ["count", "commit", "generate"]

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
        track = AsyncMock()
        channels = ScriptedChannels()
        outcome = await _deliver_through(channels, repo, track=track)

        assert outcome == "delivered"
        # §9 oracle (a)+(b): tokens booked to the SENDER, never the recipient.
        assert track.await_args.kwargs["user_id"] == SENDER_ID
        assert track.await_args.kwargs["task_type"] == "peer_message"
        # Recipient got the relayed message; sender got the confirmation.
        assert [sent.user_id for sent in channels.sent] == [RECIPIENT_ID, SENDER_ID]
        assert channels.sent[0].task_type == "peer_message"
        repo.mark_message_delivered.assert_awaited_once()

    async def test_a_dispatch_that_reached_nobody_is_a_retryable_failure(self, not_blocked):
        """An SSE event alone reached an open tab or nobody (audit AC-003).

        Filed « delivered », the message left the queue for good while its
        recipient found nothing, and its sender was told it had arrived.
        """
        repo = _repo()
        channels = sse_only()
        outcome = await _deliver_through(channels, repo)

        assert outcome == "pending"  # the next sweep tries again
        assert repo.mark_message_failed.await_args.args[1] == "dispatch_error"
        repo.mark_message_delivered.assert_not_awaited()
        assert [sent.user_id for sent in channels.sent] == [RECIPIENT_ID]  # no « delivered »

    async def test_an_undelivered_message_at_the_cap_tells_the_sender_it_failed(self, not_blocked):
        repo = _repo()
        repo.mark_message_failed.return_value = "failed"
        channels = ScriptedChannels(archived=False)
        outcome = await _deliver_through(channels, repo)

        assert outcome == "failed"
        repo.mark_message_delivered.assert_not_awaited()
        # The second dispatch is the sender's « failed » notice, never « delivered ».
        assert [sent.user_id for sent in channels.sent] == [RECIPIENT_ID, SENDER_ID]
        assert channels.sent[1].content == delivery.ProactiveMessages.peer_message_failed_body(
            "Marie", "fr"
        )

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

    async def test_a_failure_is_counted_on_a_session_of_its_own(
        self, not_blocked, accounting_session: AsyncMock
    ) -> None:
        """A database error in the dispatch's archive aborts the claim session's
        transaction: counted there, the failure raises in its turn and the
        message never reaches its cap (measured on PostgreSQL: 25P02)."""
        claim_repo, accounting_repo = _repo(), _repo()

        def _repository(session: object) -> AsyncMock:
            return accounting_repo if session is accounting_session else claim_repo

        with (
            patch(
                "src.infrastructure.scheduler.peer_message_delivery.PeersRepository",
                side_effect=_repository,
            ),
            patch(
                "src.infrastructure.scheduler.peer_message_delivery._generate_delivery_text",
                new=AsyncMock(side_effect=RuntimeError("llm down")),
            ),
        ):
            outcome = await delivery.deliver_claimed_message(_message(), _db(_users()))

        assert outcome == "pending"
        accounting_repo.mark_message_failed.assert_awaited_once()
        claim_repo.mark_message_failed.assert_not_awaited()

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
