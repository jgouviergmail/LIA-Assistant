"""The Telegram paths speak the person's language and say what happened (ADR-323).

A channel update has no request of its own: the turn a HITL button resumes
declares the person's language for its whole run, and until the person is known
the bot answers in the language their Telegram client declares. A voice message
too long for the transcriber is TOLD so — it used to read « I could not
understand you », which sends the person to repeat the same message. A chat
blocked after too many OTP attempts is told it is blocked — it used to read
« invalid code », which invites the very attempt the block refuses. A
deactivated account, or a binding its owner switched off, is told so too, and
never resumed nor linked.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.i18n import language_scope, resolve_language
from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.inbound_handler import InboundMessageHandler
from src.domains.channels.models import ChannelType
from src.domains.channels.router import (
    _handle_hitl_callback,
    _handle_otp_verification,
    process_telegram_update,
)
from src.domains.channels.service import OtpAttemptsExhaustedError
from src.domains.users.models import User
from src.infrastructure.channels.telegram.formatter import get_bot_message
from src.infrastructure.channels.telegram.hitl_keyboard import (
    get_button_label,
    question_fingerprint,
)
from src.infrastructure.channels.telegram.voice import (
    MAX_VOICE_DURATION_SECONDS,
    voice_duration_cap_seconds,
)
from src.infrastructure.channels.telegram.webhook_handler import client_language_of

pytestmark = pytest.mark.unit

_BINDINGS = "src.domains.channels.repository.UserChannelBindingRepository"
_USERS = "src.domains.users.repository.UserRepository"
_SESSION = "src.infrastructure.database.session.get_db_context"
_SENDER = "src.infrastructure.channels.telegram.sender.TelegramSender"
_HANDLER = "src.domains.channels.inbound_handler.InboundMessageHandler"
_CONVERSATIONS = "src.domains.conversations.repository.ConversationRepository"


def _person_language() -> str:
    """A language that is not the instance default, so nothing passes by chance."""
    return next(code for code in ("it", "es") if code != settings.default_language)


def _declared_language() -> str:
    """A declared language that is neither the instance default nor the person's."""
    taken = {settings.default_language, _person_language()}
    return next(code for code in ("de", "en", "es") if code not in taken)


def _row(language: str, *, is_active: bool = True) -> User:
    """A real ``User`` row — the shape the channel reader returns, never a mock."""
    return User(
        id=uuid4(),
        email="person@example.com",
        full_name="Alex",
        is_active=is_active,
        language=language,
        timezone="Europe/Rome",
        memory_enabled=True,
        journals_enabled=True,
        psyche_enabled=True,
    )


def _binding(*, is_active: bool = True) -> MagicMock:
    binding = MagicMock()
    binding.user_id = uuid4()
    binding.is_active = is_active
    return binding


@asynccontextmanager
async def _session() -> AsyncIterator[MagicMock]:
    yield MagicMock()


def _cache(*, claim_held: bool = False, down: bool = False) -> MagicMock:
    """The cache a button press claims the person's turn in."""
    cache = MagicMock()
    if down:
        cache.set = AsyncMock(side_effect=ConnectionError("cache down"))
    else:
        cache.set = AsyncMock(return_value=not claim_held)
    cache.eval = AsyncMock(return_value=1)
    return cache


def _nx_cache() -> MagicMock:
    """A cache whose ``SET NX`` answers as Redis does: the first write wins."""
    held: set[str] = set()

    async def _set(key: str, _value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in held:
            return False
        held.add(key)
        return True

    cache = MagicMock()
    cache.set = AsyncMock(side_effect=_set)
    cache.eval = AsyncMock(return_value=1)
    return cache


#: The person's conversation — a UUID, as the real row's id is: compared as
#: text with the button's callback data, a missing ``str()`` would never match.
_OWN_CONVERSATION = uuid4()

#: The pending question's message id, as the streaming service writes it.
_QUESTION_ID = f"hitl_{_OWN_CONVERSATION}_interrupt-1"

#: A pending question as ``HITLStore.get_pending`` returns it — what the
#: streaming service writes, flattened. A top-level ``type`` was frozen here:
#: a key no interaction writes (review 12).
_PENDING: dict[str, Any] = {
    "action_requests": [{"type": "plan_approval"}],
    "count": 1,
    "run_id": "run-asked",
    "interrupt_ts": "2026-09-26T00:00:00+00:00",
    "message_id": _QUESTION_ID,
}


def _conversations(own: UUID | None) -> MagicMock:
    """The repository the button path reads the person's own conversation from.

    Patched at the repository, never at ``_own_conversation_id``: the read's
    failure semantics are what the button path depends on.
    """
    repository = MagicMock()
    repository.get_active_for_user = AsyncMock(
        return_value=None if own is None else MagicMock(id=own)
    )
    return repository


async def test_a_resumed_hitl_turn_speaks_the_persons_language() -> None:
    person = _person_language()
    heard: list[str] = []
    received: dict[str, Any] = {}

    async def _handle(**kwargs: Any) -> None:
        heard.append(resolve_language())
        received.update(kwargs)

    bindings = MagicMock()
    bindings.get_by_channel_id = AsyncMock(return_value=_binding())
    store = MagicMock()
    store.get_pending = AsyncMock(return_value=_PENDING)
    users = MagicMock()
    users.get_by_id = AsyncMock(return_value=_row(person))
    handler = MagicMock()
    handler.handle = AsyncMock(side_effect=_handle)

    with (
        patch(_SESSION, _session),
        patch(_BINDINGS, return_value=bindings),
        patch(
            "src.infrastructure.cache.redis.get_redis_session",
            new=AsyncMock(return_value=_cache()),
        ),
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch("src.domains.agents.utils.hitl_store.HITLStore", return_value=store),
        patch(_USERS, return_value=users),
        patch(_CONVERSATIONS, return_value=_conversations(_OWN_CONVERSATION)),
        patch(_SENDER),
        patch(_HANDLER, return_value=handler),
    ):
        await _handle_hitl_callback(_callback())

    assert heard == [person]
    # The account's own choices reach the resumed turn — the profile DTO the
    # reader used to return carried neither flag, so both read False.
    assert received["user_journals_enabled"] is True
    assert received["user_psyche_enabled"] is True
    # Scoped: the polling bot runs every update in one task.
    assert resolve_language() == settings.default_language


def _callback(
    action: str = "approve", *, question: str = _QUESTION_ID, message_id: str | None = None
) -> ChannelInboundMessage:
    """A press on a button of ``question``, as Telegram hands it back."""
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="12345",
        callback_data=f"hitl:{action}:{_OWN_CONVERSATION}:{question_fingerprint(question)}",
        message_id=message_id,
    )


@pytest.mark.parametrize(
    ("account_active", "binding_active", "told"),
    [
        (False, True, "account_inactive"),
        (True, False, "channel_disabled"),
        (False, False, "account_inactive"),
    ],
)
async def test_a_refused_button_press_is_told_why_in_the_person_s_language(
    account_active: bool, binding_active: bool, told: str
) -> None:
    """Never resumed: the person is told what stands in the way, in their language."""
    person = _person_language()
    bindings = MagicMock()
    bindings.get_by_channel_id = AsyncMock(return_value=_binding(is_active=binding_active))
    users = MagicMock()
    users.get_by_id = AsyncMock(return_value=_row(person, is_active=account_active))
    sender = MagicMock()
    sender.send_message = AsyncMock()
    handler = MagicMock()
    handler.handle = AsyncMock()

    with (
        patch(_SESSION, _session),
        patch(_BINDINGS, return_value=bindings),
        patch(_USERS, return_value=users),
        patch(
            "src.infrastructure.cache.redis.get_redis_session",
            new=AsyncMock(return_value=_nx_cache()),
        ),
        patch(_SENDER, return_value=sender),
        patch(_HANDLER, return_value=handler),
    ):
        await _handle_hitl_callback(_callback())

    # Both are read whatever their state — the refusal needs the person.
    assert bindings.get_by_channel_id.await_args.kwargs == {"include_inactive": True}
    assert users.get_by_id.await_args.kwargs == {"include_inactive": True}
    sender.send_message.assert_awaited_once()
    recipient, said = sender.send_message.await_args.args
    assert (recipient, said.text) == ("12345", get_bot_message(told, person))
    handler.handle.assert_not_awaited()


async def test_a_refused_button_is_told_once_per_window() -> None:
    """Every press of a refused account drew its own reply: the button door
    answers through the message door's notice — counted on every press, told
    once per window."""
    from structlog.testing import capture_logs

    bindings = MagicMock()
    bindings.get_by_channel_id = AsyncMock(return_value=_binding())
    users = MagicMock()
    users.get_by_id = AsyncMock(return_value=_row(_person_language(), is_active=False))
    sender = MagicMock()
    sender.send_message = AsyncMock()
    before = _rejected("account_inactive")

    with (
        patch(_SESSION, _session),
        patch(_BINDINGS, return_value=bindings),
        patch(_USERS, return_value=users),
        patch(
            "src.infrastructure.cache.redis.get_redis_session",
            new=AsyncMock(return_value=_nx_cache()),
        ),
        patch(_SENDER, return_value=sender),
        capture_logs() as logs,
    ):
        for _ in range(3):
            await _handle_hitl_callback(_callback())

    assert sender.send_message.await_count == 1
    assert _rejected("account_inactive") == before + 3
    # The door's own event — the counter carries no door label.
    refused = [e for e in logs if e["event"] == "telegram_hitl_callback_refused"]
    assert [(e["reason"], e["log_level"]) for e in refused] == [("account_inactive", "warning")] * 3


async def test_a_failed_button_lookup_is_answered() -> None:
    """A read that fails is answered in the declared language, never dropped."""
    declared = _declared_language()
    bindings = MagicMock()
    bindings.get_by_channel_id = AsyncMock(side_effect=RuntimeError("database unavailable"))
    sender = MagicMock()
    sender.send_text = AsyncMock()

    with (
        patch(_SESSION, _session),
        patch(_BINDINGS, return_value=bindings),
        patch(_SENDER, return_value=sender),
        language_scope(declared),
    ):
        await _handle_hitl_callback(_callback())

    sender.send_text.assert_awaited_once_with("12345", get_bot_message("error", declared))


async def test_the_link_reply_leaves_once_its_session_is_closed() -> None:
    """No transaction stays open across the Telegram call (ADR-304)."""
    open_sessions: list[bool] = []
    seen: list[bool] = []

    @asynccontextmanager
    async def _tracked() -> AsyncIterator[MagicMock]:
        open_sessions.append(True)
        try:
            yield MagicMock()
        finally:
            open_sessions.pop()

    person = _person_language()
    sender = MagicMock()
    sender.send_text = AsyncMock(side_effect=lambda *_args: seen.append(bool(open_sessions)))
    users = MagicMock()
    users.get_by_id = AsyncMock(return_value=_row(person))
    service_cls = MagicMock()
    service_cls.verify_otp = AsyncMock(return_value={"user_id": str(uuid4())})
    service_cls.return_value.create_binding = AsyncMock()

    with (
        patch(_SENDER, return_value=sender),
        patch("src.domains.channels.router.ChannelService", service_cls),
        patch(_SESSION, _tracked),
        patch(_USERS, return_value=users),
    ):
        await _handle_otp_verification("123456", "999", "telegram", {})

    service_cls.return_value.create_binding.assert_awaited_once()
    sender.send_text.assert_awaited_once_with("999", get_bot_message("otp_success", person))
    assert seen == [False]


async def test_a_deactivated_account_is_never_linked() -> None:
    """The code names a deactivated account: told so in its language, never bound."""
    person = _person_language()
    sender = MagicMock()
    sender.send_text = AsyncMock()
    users = MagicMock()
    users.get_by_id = AsyncMock(return_value=_row(person, is_active=False))
    service_cls = MagicMock()
    service_cls.verify_otp = AsyncMock(return_value={"user_id": str(uuid4())})
    service_cls.return_value.create_binding = AsyncMock()

    with (
        patch(_SENDER, return_value=sender),
        patch("src.domains.channels.router.ChannelService", service_cls),
        patch(_SESSION, _session),
        patch(_USERS, return_value=users),
    ):
        await _handle_otp_verification("123456", "999", "telegram", {})

    assert users.get_by_id.await_args.kwargs == {"include_inactive": True}
    service_cls.return_value.create_binding.assert_not_awaited()
    sender.send_text.assert_awaited_once_with("999", get_bot_message("account_inactive", person))


@pytest.mark.parametrize(
    "failure",
    [OperationalError("SELECT", {}, Exception("down")), OSError("connection refused")],
    ids=["database_error", "connection_error"],
)
async def test_an_account_nobody_could_read_is_never_linked(failure: Exception) -> None:
    """Fail CLOSED: an unread account may be a deactivated one. The person is
    answered — in the declared language, nobody being known — and nothing is bound;
    a connection failure (not a ``SQLAlchemyError``) is answered too."""
    declared = _declared_language()
    sender = MagicMock()
    sender.send_text = AsyncMock()
    users = MagicMock()
    users.get_by_id = AsyncMock(side_effect=failure)
    service_cls = MagicMock()
    service_cls.verify_otp = AsyncMock(return_value={"user_id": str(uuid4())})
    service_cls.return_value.create_binding = AsyncMock()

    with (
        patch(_SENDER, return_value=sender),
        patch("src.domains.channels.router.ChannelService", service_cls),
        patch(_SESSION, _session),
        patch(_USERS, return_value=users),
        language_scope(declared),
    ):
        await _handle_otp_verification("123456", "999", "telegram", {})

    service_cls.return_value.create_binding.assert_not_awaited()
    sender.send_text.assert_awaited_once_with("999", get_bot_message("error", declared))


async def test_an_account_gone_since_the_code_was_issued_is_never_linked() -> None:
    declared = _declared_language()
    sender = MagicMock()
    sender.send_text = AsyncMock()
    users = MagicMock()
    users.get_by_id = AsyncMock(return_value=None)
    service_cls = MagicMock()
    service_cls.verify_otp = AsyncMock(return_value={"user_id": str(uuid4())})
    service_cls.return_value.create_binding = AsyncMock()

    with (
        patch(_SENDER, return_value=sender),
        patch("src.domains.channels.router.ChannelService", service_cls),
        patch(_SESSION, _session),
        patch(_USERS, return_value=users),
        language_scope(declared),
    ):
        await _handle_otp_verification("123456", "999", "telegram", {})

    service_cls.return_value.create_binding.assert_not_awaited()
    sender.send_text.assert_awaited_once_with("999", get_bot_message("error", declared))


def _update(language_code: str | None) -> dict[str, Any]:
    sender: dict[str, Any] = {"id": 999}
    if language_code is not None:
        sender["language_code"] = language_code
    return {
        "update_id": 1,
        "message": {"message_id": 7, "chat": {"id": 999}, "from": sender, "text": "hello"},
    }


@pytest.mark.parametrize(
    ("client", "expected"),
    [
        ("it", "it"),
        ("zh-hans", "zh-CN"),
        ("pt-br", None),  # a language LIA does not speak declares nothing
        (None, None),
    ],
)
def test_the_client_language_is_read_from_the_update(
    client: str | None, expected: str | None
) -> None:
    assert client_language_of(_update(client)) == expected
    button = {"callback_query": {"from": {"id": 1, "language_code": client}, "data": "x"}}
    assert client_language_of(button) == expected


def test_a_client_language_this_instance_does_not_speak_declares_nothing() -> None:
    """Read like the Accept-Language it is: an instance narrowed to two
    languages answers a German client in its own default, never in German —
    which the fixed list of six let through."""
    with patch("src.core.i18n.SUPPORTED_LANGUAGES", ["fr", "en"]):
        assert client_language_of(_update("de")) is None
        assert client_language_of(_update("en-GB")) == "en"


async def test_an_unknown_person_is_answered_in_their_client_s_language() -> None:
    """Before the person is known, their Telegram client's language speaks (ADR-323)."""
    client = _person_language()
    bindings = MagicMock()
    bindings.get_by_channel_id = AsyncMock(return_value=None)
    sender = MagicMock()
    sender.send_message = AsyncMock()

    with (
        patch(_SESSION, _session),
        patch(_BINDINGS, return_value=bindings),
        patch("src.infrastructure.cache.redis.get_redis_session", new=AsyncMock()),
        patch(_SENDER, return_value=sender),
    ):
        await process_telegram_update(_update(client))

    told = sender.send_message.await_args.args[1].text
    assert told == get_bot_message("unbound", client)
    # Scoped to the update: the polling bot runs every update in one task.
    assert resolve_language() == settings.default_language


async def test_a_voice_message_too_long_is_told_so_and_never_transcribed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Within Telegram's 120 s, past the STT's 60: this note used to pass the
    # gate, be refused by the STT and be answered « I could not understand ».
    monkeypatch.setattr(settings, "voice_stt_max_duration_seconds", 60)
    sender = AsyncMock()
    handler = InboundMessageHandler(sender=sender)
    message = ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="12345",
        voice_file_id="voice-1",
        voice_duration_seconds=90,
    )

    with (
        patch("src.infrastructure.channels.telegram.bot.get_bot", return_value=MagicMock()),
        patch(
            "src.infrastructure.channels.telegram.voice.transcribe_voice_message",
            new=AsyncMock(),
        ) as transcribe,
    ):
        text = await handler._transcribe_voice(message, "12345", "en")

    assert text is None
    transcribe.assert_not_awaited()
    told = sender.send_message.call_args.args[1].text
    # The cap stated is the cap the transcription holds.
    assert told == get_bot_message("voice_too_long", "en").format(max_seconds=60)
    assert "max 60 s" in told


@pytest.mark.parametrize("language", ["fr", "en", "es", "de", "it", "zh-CN"])
def test_the_too_long_sentence_states_the_cap_in_every_language(language: str) -> None:
    cap = voice_duration_cap_seconds()
    told = get_bot_message("voice_too_long", language).format(max_seconds=cap)

    assert str(cap) in told
    assert "{" not in told and "}" not in told


async def test_a_too_long_voice_message_is_still_measured() -> None:
    handler = InboundMessageHandler(sender=AsyncMock())
    message = ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="12345",
        voice_file_id="voice-1",
        voice_duration_seconds=MAX_VOICE_DURATION_SECONDS + 1,
    )

    with (
        patch("src.infrastructure.channels.telegram.bot.get_bot", return_value=MagicMock()),
        patch("src.domains.channels.inbound_handler.channel_voice_duration_seconds") as histogram,
    ):
        await handler._transcribe_voice(message, "12345", "en")

    histogram.labels.return_value.observe.assert_called_once_with(MAX_VOICE_DURATION_SECONDS + 1)


async def test_a_blocked_chat_is_told_it_is_blocked() -> None:
    declared = _declared_language()
    sender = MagicMock()
    sender.send_text = AsyncMock()

    with (
        patch(_SENDER, return_value=sender),
        patch(
            "src.domains.channels.router.ChannelService.verify_otp",
            new=AsyncMock(side_effect=OtpAttemptsExhaustedError),
        ),
        language_scope(declared),
    ):
        await _handle_otp_verification("123456", "999", "telegram", {})

    sender.send_text.assert_awaited_once_with("999", get_bot_message("otp_blocked", declared))


async def test_a_failed_link_is_told_in_the_account_s_language() -> None:
    """The code names the account: its language, not the webhook's (ADR-323)."""
    person = _person_language()
    sender = MagicMock()
    sender.send_text = AsyncMock()
    users = MagicMock()
    users.get_by_id = AsyncMock(return_value=_row(person))
    service_cls = MagicMock()
    service_cls.verify_otp = AsyncMock(return_value={"user_id": str(uuid4())})
    service_cls.return_value.create_binding = AsyncMock(side_effect=RuntimeError("constraint"))

    with (
        patch(_SENDER, return_value=sender),
        patch("src.domains.channels.router.ChannelService", service_cls),
        patch(_SESSION, _session),
        patch(_USERS, return_value=users),
    ):
        await _handle_otp_verification("123456", "999", "telegram", {})

    sender.send_text.assert_awaited_once_with("999", get_bot_message("error", person))


@pytest.mark.parametrize(
    ("cache", "told"),
    [(_cache(claim_held=True), "busy"), (_cache(down=True), "error")],
    ids=["turn_running", "cache_down"],
)
async def test_a_button_waits_for_the_person_s_turn(cache: MagicMock, told: str) -> None:
    """A double tap, or a press during a running turn, never resumes the graph twice;
    a cache nobody can reach is answered, never swallowed."""
    person = _person_language()
    bindings = MagicMock()
    bindings.get_by_channel_id = AsyncMock(return_value=_binding())
    users = MagicMock()
    users.get_by_id = AsyncMock(return_value=_row(person))
    sender = MagicMock()
    sender.send_message = AsyncMock()
    handler = MagicMock()
    handler.handle = AsyncMock()

    with (
        patch(_SESSION, _session),
        patch(_BINDINGS, return_value=bindings),
        patch(_USERS, return_value=users),
        patch(
            "src.infrastructure.cache.redis.get_redis_session", new=AsyncMock(return_value=cache)
        ),
        patch(_SENDER, return_value=sender),
        patch(_HANDLER, return_value=handler),
    ):
        await _handle_hitl_callback(_callback())

    handler.handle.assert_not_awaited()
    # Answered by the message door's own code: the same claim, the same words.
    sender.send_message.assert_awaited_once()
    recipient, said = sender.send_message.await_args.args
    assert (recipient, said.text) == ("12345", get_bot_message(told, person))


async def test_a_resumed_button_releases_the_turn_it_claimed() -> None:
    from src.infrastructure.locks.redis_claim import RELEASE_SCRIPT

    cache = _cache()
    bindings = MagicMock()
    bindings.get_by_channel_id = AsyncMock(return_value=_binding())
    store = MagicMock()
    store.get_pending = AsyncMock(return_value=_PENDING)
    users = MagicMock()
    users.get_by_id = AsyncMock(return_value=_row(_person_language()))
    handler = MagicMock()
    handler.handle = AsyncMock()

    with (
        patch(_SESSION, _session),
        patch(_BINDINGS, return_value=bindings),
        patch(_USERS, return_value=users),
        patch(
            "src.infrastructure.cache.redis.get_redis_session", new=AsyncMock(return_value=cache)
        ),
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch("src.domains.agents.utils.hitl_store.HITLStore", return_value=store),
        patch(_CONVERSATIONS, return_value=_conversations(_OWN_CONVERSATION)),
        patch(_SENDER),
        patch(_HANDLER, return_value=handler),
    ):
        await _handle_hitl_callback(_callback())

    handler.handle.assert_awaited_once()
    released = cache.eval.await_args.args
    assert released[0] == RELEASE_SCRIPT
    assert released[3] == cache.set.await_args.args[1]  # the token it claimed with


def _rejected(reason: str) -> float:
    from src.infrastructure.observability.metrics_channels import (
        channel_messages_rejected_total,
    )

    return float(
        channel_messages_rejected_total.labels(channel_type="telegram", reason=reason)._value.get()
    )


class _ButtonWorld:
    """The button path's collaborators, one fake each, the person known."""

    def __init__(
        self, *, pending: dict[str, Any] | None, own: UUID | None = _OWN_CONVERSATION
    ) -> None:
        self.person = _person_language()
        self.cache = _cache()
        self.bindings = MagicMock()
        self.bindings.get_by_channel_id = AsyncMock(return_value=_binding())
        self.users = MagicMock()
        self.users.get_by_id = AsyncMock(return_value=_row(self.person))
        self.store = MagicMock()
        self.store.get_pending = AsyncMock(return_value=pending)
        self.conversations = _conversations(own)
        self.sender = MagicMock()
        self.sender.send_text = AsyncMock()
        self.sender.send_message = AsyncMock()
        self.sender.remove_keyboard = AsyncMock(return_value=True)
        self.handler = MagicMock()
        self.handler.handle = AsyncMock()

    async def press(self, pressed: ChannelInboundMessage | None = None) -> None:
        with (
            patch(_SESSION, _session),
            patch(_BINDINGS, return_value=self.bindings),
            patch(_USERS, return_value=self.users),
            patch(
                "src.infrastructure.cache.redis.get_redis_session",
                new=AsyncMock(return_value=self.cache),
            ),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                new=AsyncMock(return_value=MagicMock()),
            ),
            patch("src.domains.agents.utils.hitl_store.HITLStore", return_value=self.store),
            patch(_CONVERSATIONS, return_value=self.conversations),
            patch(_SENDER, return_value=self.sender),
            patch(_HANDLER, return_value=self.handler),
        ):
            await _handle_hitl_callback(pressed or _callback())

    def told(self, key: str) -> None:
        """The one answer the person got, whichever of the sender's doors it took."""
        said = [call.args for call in self.sender.send_text.await_args_list] + [
            (call.args[0], call.args[1].text) for call in self.sender.send_message.await_args_list
        ]
        assert said == [("12345", get_bot_message(key, self.person))]


async def test_a_button_finds_the_question_where_the_engine_saved_it() -> None:
    """The engine saves a pending question through the CACHE database; the
    button read it through the SESSION database it claims turns on, so every
    press was told « expired » (review 12). Two keyspaces of one in-memory server,
    the real store."""
    from src.core.constants import REDIS_CACHE_DB, REDIS_SESSION_DB
    from src.domains.agents.utils.hitl_store import HITLStore
    from tests.helpers.redis_databases import RedisServer

    server = RedisServer()
    engine_cache, door_session = server.client(REDIS_CACHE_DB), server.client(REDIS_SESSION_DB)
    await HITLStore(redis_client=engine_cache, ttl_seconds=60).save_interrupt(
        str(_OWN_CONVERSATION),
        {"action_requests": [], "run_id": "run-1", "message_id": _QUESTION_ID},
    )
    world = _ButtonWorld(pending=None)

    with (
        patch(_SESSION, _session),
        patch(_BINDINGS, return_value=world.bindings),
        patch(_USERS, return_value=world.users),
        patch(_CONVERSATIONS, return_value=world.conversations),
        patch(_SENDER, return_value=world.sender),
        patch(_HANDLER, return_value=world.handler),
        patch(
            "src.infrastructure.cache.redis.get_redis_session",
            new=AsyncMock(return_value=door_session),
        ),
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=engine_cache),
        ),
    ):
        await _handle_hitl_callback(_callback())

    world.handler.handle.assert_awaited_once()
    resumed = world.handler.handle.await_args.kwargs["pending_hitl"]
    assert resumed["run_id"] == "run-1"


def _expired(logs: Sequence[Mapping[str, Any]]) -> list[tuple[object, object]]:
    return [
        (entry["owner_match"], entry["conversation_id"])
        for entry in logs
        if entry["event"] == "telegram_hitl_callback_expired"
    ]


async def test_an_expired_question_is_told_never_dropped() -> None:
    from structlog.testing import capture_logs

    world = _ButtonWorld(pending=None)

    with capture_logs() as logs:
        await world.press()

    world.handler.handle.assert_not_awaited()
    world.told("hitl_expired")
    assert _expired(logs) == [(True, str(_OWN_CONVERSATION))]


async def test_a_conversation_that_cannot_be_read_is_a_failure_never_an_expiry() -> None:
    """The cached lookup answered None on a failed read too: a button pressed
    while the database was away was told its question had expired. The read
    itself fails here — ``_own_conversation_id`` runs, only its query is faked."""
    world = _ButtonWorld(pending=_PENDING)
    world.conversations.get_active_for_user = AsyncMock(
        side_effect=OperationalError("SELECT", {}, ConnectionError("db down"))
    )

    await world.press()

    world.handler.handle.assert_not_awaited()
    world.told("error")


async def test_a_button_for_another_conversation_is_never_resumed() -> None:
    """The callback data is whatever the client sends back: a question of any
    conversation but the person's own reads as one that no longer waits."""
    from structlog.testing import capture_logs

    world = _ButtonWorld(pending=_PENDING, own=uuid4())

    with capture_logs() as logs:
        await world.press()

    world.store.get_pending.assert_not_awaited()
    world.handler.handle.assert_not_awaited()
    world.told("hitl_expired")
    # A foreign id is whatever the client sent back: never logged.
    assert _expired(logs) == [(False, None)]


async def test_a_press_resumes_its_question_with_the_card_s_decision() -> None:
    """The chat card's own gesture (review 14): the label pressed, in the
    person's language, is archived as their message, and the question resumes
    on the structured decision — applied without a model — never on the label
    classified as words (nine presses in twelve reached the classifier)."""
    world = _ButtonWorld(pending=_PENDING)

    await world.press(_callback("approve"))

    kwargs = world.handler.handle.await_args.kwargs
    assert kwargs["message"].text == get_button_label("approve", world.person)
    assert kwargs["user_language"] == world.person
    assert kwargs["hitl_decision"] == {"message_id": _QUESTION_ID, "action": "approve"}
    assert kwargs["pending_hitl"] == _PENDING


async def test_a_press_takes_the_keyboard_off_and_leaves_the_question_readable() -> None:
    """The question's text was replaced by « label ✓ » BEFORE any decision —
    the draft the person approved disappeared from the chat. Only the keyboard
    goes, so the same question cannot be pressed twice; the resumed turn's
    answer says what the decision did."""
    world = _ButtonWorld(pending=_PENDING)

    await world.press(_callback("approve", message_id="77"))

    world.sender.remove_keyboard.assert_awaited_once_with("12345", "77")
    assert [call[0] for call in world.sender.mock_calls] == ["remove_keyboard"]
    world.handler.handle.assert_awaited_once()


@pytest.mark.parametrize(
    ("pressed", "pending"),
    [
        (_callback(question=f"hitl_{_OWN_CONVERSATION}_interrupt-0"), _PENDING),
        (
            ChannelInboundMessage(
                channel_type=ChannelType.TELEGRAM,
                channel_user_id="12345",
                callback_data=f"hitl:approve:{_OWN_CONVERSATION}",
                message_id="77",
            ),
            _PENDING,
        ),
        (_callback(), {key: value for key, value in _PENDING.items() if key != "message_id"}),
    ],
    ids=["an_earlier_question", "a_button_without_its_question", "a_question_saved_without_id"],
)
async def test_a_button_answers_only_the_question_now_waiting(
    pressed: ChannelInboundMessage, pending: dict[str, Any]
) -> None:
    """A keyboard stays in the chat after its question: pressed under the
    NEXT question of the same conversation, it would have answered that one.
    Only a press whose fingerprint is the pending question's resumes it."""
    world = _ButtonWorld(pending=pending)

    await world.press(pressed)

    world.handler.handle.assert_not_awaited()
    world.told("hitl_expired")


async def test_an_expired_press_takes_its_keyboard_off() -> None:
    world = _ButtonWorld(pending=None)

    await world.press(_callback(message_id="77"))

    world.sender.remove_keyboard.assert_awaited_once_with("12345", "77")
    world.told("hitl_expired")


async def test_a_resumption_that_fails_is_answered_and_its_turn_released() -> None:
    from src.infrastructure.locks.redis_claim import RELEASE_SCRIPT

    world = _ButtonWorld(pending=_PENDING)
    world.handler.handle = AsyncMock(side_effect=RuntimeError("graph down"))

    await world.press()

    world.told("error")
    assert world.cache.eval.await_args.args[0] == RELEASE_SCRIPT


def _claim_events(logs: Sequence[Mapping[str, Any]]) -> list[tuple[object, ...]]:
    """Every claim event either door logged: (event, level, exc_info, claim_loss)."""
    return [
        (entry["event"], entry["log_level"], entry.get("exc_info"), entry.get("claim_loss"))
        for entry in logs
        if entry["event"].endswith(("_lock_failed", "_locked", "_claim_lost"))
    ]


async def test_a_resumed_turn_whose_claim_was_lost_is_answered_and_counted() -> None:
    from structlog.testing import capture_logs

    from src.infrastructure.locks.redis_claim import ClaimLost

    world = _ButtonWorld(pending=_PENDING)
    world.handler.handle = AsyncMock(side_effect=ClaimLost("k", "hold_exhausted"))
    before = _rejected("claim_lost")

    with capture_logs() as logs:
        await world.press()

    world.told("error")
    assert _rejected("claim_lost") == before + 1
    # Under the BUTTON door's own name: one implementation, each door its events.
    assert _claim_events(logs) == [
        ("telegram_hitl_callback_claim_lost", "warning", None, "hold_exhausted")
    ]


@pytest.mark.parametrize(
    ("cache", "reason", "logged"),
    [
        (
            _cache(claim_held=True),
            "locked",
            ("telegram_hitl_callback_locked", "info", None, None),
        ),
        (
            _cache(down=True),
            "lock_failed",
            ("telegram_hitl_callback_lock_failed", "error", True, None),
        ),
    ],
    ids=["turn_running", "cache_down"],
)
async def test_a_button_s_claim_refusals_are_counted(
    cache: MagicMock, reason: str, logged: tuple[object, ...]
) -> None:
    from structlog.testing import capture_logs

    world = _ButtonWorld(pending=_PENDING)
    world.cache = cache
    before = _rejected(reason)

    with capture_logs() as logs:
        await world.press()

    world.handler.handle.assert_not_awaited()
    assert _rejected(reason) == before + 1
    assert _claim_events(logs) == [logged]


async def test_an_invalid_callback_is_logged_by_its_length_alone() -> None:
    """Whatever the client sent back — an action no keyboard draws included —
    is logged at WARNING by its length, never its content, and nothing is read,
    answered or resumed for it. Every collaborator is faked, the database too."""
    from structlog.testing import capture_logs

    data = f"hitl:delete_everything:{_OWN_CONVERSATION}"
    world = _ButtonWorld(pending=_PENDING)

    with capture_logs() as logs:
        await world.press(
            ChannelInboundMessage(
                channel_type=ChannelType.TELEGRAM, channel_user_id="12345", callback_data=data
            )
        )

    world.bindings.get_by_channel_id.assert_not_awaited()
    world.store.get_pending.assert_not_awaited()
    world.sender.send_text.assert_not_awaited()
    world.sender.send_message.assert_not_awaited()
    world.handler.handle.assert_not_awaited()
    (invalid,) = [entry for entry in logs if entry["event"] == "telegram_hitl_callback_invalid"]
    assert invalid["log_level"] == "warning"
    assert invalid["callback_data_length"] == len(data)
    assert "callback_data" not in invalid


async def test_a_code_nobody_could_verify_is_answered() -> None:
    """The code store failing is answered, in the declared language."""
    declared = _declared_language()
    sender = MagicMock()
    sender.send_text = AsyncMock()
    service_cls = MagicMock()
    service_cls.verify_otp = AsyncMock(side_effect=ConnectionError("cache down"))
    service_cls.return_value.create_binding = AsyncMock()

    with (
        patch(_SENDER, return_value=sender),
        patch("src.domains.channels.router.ChannelService", service_cls),
        language_scope(declared),
    ):
        await _handle_otp_verification("123456", "999", "telegram", {})

    service_cls.return_value.create_binding.assert_not_awaited()
    sender.send_text.assert_awaited_once_with("999", get_bot_message("error", declared))


async def test_a_link_whose_commit_fails_is_never_a_success() -> None:
    """The session commits at its exit: a commit that fails after the insert is
    answered « error », never « linked »."""
    person = _person_language()
    sender = MagicMock()
    sender.send_text = AsyncMock()
    users = MagicMock()
    users.get_by_id = AsyncMock(return_value=_row(person))
    service_cls = MagicMock()
    service_cls.verify_otp = AsyncMock(return_value={"user_id": str(uuid4())})
    service_cls.return_value.create_binding = AsyncMock()

    @asynccontextmanager
    async def _commit_fails() -> AsyncIterator[MagicMock]:
        yield MagicMock()
        raise OperationalError("COMMIT", {}, Exception("down"))

    with (
        patch(_SENDER, return_value=sender),
        patch("src.domains.channels.router.ChannelService", service_cls),
        patch(_SESSION, _commit_fails),
        patch(_USERS, return_value=users),
    ):
        await _handle_otp_verification("123456", "999", "telegram", {})

    service_cls.return_value.create_binding.assert_awaited_once()
    sender.send_text.assert_awaited_once_with("999", get_bot_message("error", person))
