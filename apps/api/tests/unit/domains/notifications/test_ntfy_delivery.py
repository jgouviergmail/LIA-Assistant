"""The one door through which LIA publishes to ntfy (ADR-391).

What it promises: the operator's switch decides first; a target is reached on the road its server
takes (the instance's as configured, a person's checked); no session stays open across a
publication (ADR-304); one target's surprise never silences the others; a batch says whether it
may be tried again, and only when nothing could have reached a device.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.core.notification_privacy import NotificationPrivacy, notification_preview
from src.domains.notifications import ntfy_delivery
from src.domains.notifications.ntfy import NtfyContent, NtfyServerKind
from src.domains.notifications.ntfy_delivery import (
    NtfyBatch,
    NtfyTargetsUnreadable,
    click_url,
    push_to_ntfy,
)
from src.domains.notifications.ntfy_repository import NtfyTarget
from src.infrastructure.external.ntfy_client import NtfyOutcome, NtfyPublishResult

pytestmark = pytest.mark.unit

OWNER = uuid4()


def _target(
    kind: NtfyServerKind = NtfyServerKind.INSTANCE,
    *,
    content: NtfyContent = NtfyContent.FULL,
    url: str | None = None,
    token: str | None = None,
) -> NtfyTarget:
    return NtfyTarget(
        id=uuid4(),
        user_id=OWNER,
        server_kind=kind,
        server_url=url if kind is NtfyServerKind.CUSTOM else None,
        topic=f"lia_{uuid4().hex[:12]}",
        token=token,
        content=content,
    )


class _World:
    """The door's surroundings: the store, the switch and the servers, observed."""

    def __init__(self, targets: list[NtfyTarget], *, answers: dict[UUID, Any] | None = None):
        self.targets = targets
        self.answers = answers or {}
        self.session_open = False
        self.sessions = 0
        self.recorded: list[tuple[UUID, NtfyOutcome]] = []
        self.read_fails = False
        #: Set, every publication waits until as many are in flight at once.
        self.together: asyncio.Barrier | None = None
        self.record_fails = False
        self.calls: list[tuple[str, str, dict[str, Any], str | None, bool]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch, *, available: bool = True) -> None:
        world = self

        @asynccontextmanager
        async def session() -> AsyncIterator[SimpleNamespace]:
            world.session_open = True
            world.sessions += 1
            db = SimpleNamespace(execute=world._execute)
            try:
                yield db
            finally:
                world.session_open = False

        class Repository:
            def __init__(self, db: Any) -> None:
                pass

            async def active_targets(self, user_ids: Any) -> list[NtfyTarget]:
                if world.read_fails:
                    raise ConnectionError("the store is down")
                return list(world.targets)

            async def record_outcomes(self, outcomes: Any, *, at: Any) -> None:
                if world.record_fails:
                    raise ConnectionError("the store is down")
                world.recorded.extend(outcomes)

        class Client:
            def __init__(self, **kwargs: Any) -> None:
                pass

            async def publish_trusted(
                self, base: str, sent: dict[str, Any], *, token: str | None
            ) -> NtfyPublishResult:
                if world.together is not None:
                    await asyncio.wait_for(world.together.wait(), timeout=1)
                return world._answer("trusted", base, sent, token)

            async def publish_checked(
                self, base: str, sent: dict[str, Any], *, token: str | None
            ) -> NtfyPublishResult:
                return world._answer("checked", base, sent, token)

        async def switch(capability: Any) -> bool:
            return available

        monkeypatch.setattr(ntfy_delivery, "get_db_context", session)
        monkeypatch.setattr(ntfy_delivery, "NtfySubscriptionRepository", Repository)
        monkeypatch.setattr(ntfy_delivery, "NtfyClient", Client)
        monkeypatch.setattr(ntfy_delivery, "is_capability_enabled", switch)

    async def _execute(self, statement: Any) -> Any:
        return SimpleNamespace(all=lambda: [SimpleNamespace(id=OWNER, language="fr")])

    def _answer(self, road: str, base: str, sent: dict, token: str | None) -> NtfyPublishResult:
        self.calls.append((road, base, sent, token, self.session_open))
        target = next(t for t in self.targets if sent["topic"] == t.topic)
        answer = self.answers.get(target.id, NtfyOutcome.SENT)
        if isinstance(answer, Exception):
            raise answer
        return NtfyPublishResult(answer)


@pytest.fixture
def instance_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ntfy_server_url", "http://ntfy:80")
    monkeypatch.setattr(settings, "ntfy_publish_token", "tk_operator")
    monkeypatch.setattr(settings, "ntfy_custom_servers_enabled", True)
    monkeypatch.setattr(settings, "frontend_url", "https://lia.example.org")


async def _push(**kwargs: Any) -> NtfyBatch:
    return await push_to_ntfy(OWNER, title="Rappel", body="Appeler Marie", **kwargs)


@pytest.mark.usefixtures("instance_server")
class TestTheDoor:
    async def test_a_switched_off_capability_reads_nothing_and_sends_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = _World([_target()])
        world.install(monkeypatch, available=False)

        batch = await _push()

        assert batch == NtfyBatch()
        assert world.sessions == 0 and world.calls == []

    async def test_the_instance_server_is_reached_as_configured_with_lia_s_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = _target()
        world = _World([target])
        world.install(monkeypatch)

        batch = await _push()

        assert batch.sent == 1 and batch.failed == 0
        ((road, base, sent, token, _),) = world.calls
        assert (road, base, token) == ("trusted", "http://ntfy:80", "tk_operator")
        assert sent["message"] == "Appeler Marie"
        assert world.recorded == [(target.id, NtfyOutcome.SENT)]

    async def test_an_instance_with_no_server_left_says_so_and_sends_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ntfy_server_url", "")
        target = _target()
        world = _World([target])
        world.install(monkeypatch)

        batch = await _push()

        assert world.calls == []
        assert world.recorded == [(target.id, NtfyOutcome.NOT_CONFIGURED)]
        assert batch.sent == 0 and not batch.retryable

    async def test_a_person_s_server_is_checked_and_carries_their_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = _target(NtfyServerKind.CUSTOM, url="https://ntfy.sh", token="tk_mine")
        world = _World([target])
        world.install(monkeypatch)

        await _push()

        ((road, base, _, token, _),) = world.calls
        assert (road, base, token) == ("checked", "https://ntfy.sh", "tk_mine")

    async def test_custom_servers_withdrawn_by_the_operator_are_not_reached(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ntfy_custom_servers_enabled", False)
        target = _target(NtfyServerKind.CUSTOM, url="https://ntfy.sh")
        world = _World([target])
        world.install(monkeypatch)

        await _push()

        assert world.calls == []
        assert world.recorded == [(target.id, NtfyOutcome.NOT_CONFIGURED)]

    async def test_minimal_content_leaves_without_the_words(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = _World([_target(content=NtfyContent.MINIMAL)])
        world.install(monkeypatch)

        await _push()

        sent = world.calls[0][2]
        expected = notification_preview(NotificationPrivacy.IN_APP_SENSITIVE, "fr", "x", "y")
        assert (sent["title"], sent["message"]) == expected

    async def test_no_session_is_open_while_a_server_answers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = _World([_target(), _target(NtfyServerKind.CUSTOM, url="https://ntfy.sh")])
        world.install(monkeypatch)

        await _push()

        assert [call[4] for call in world.calls] == [False, False]
        assert world.sessions == 2, "one short session to read, one to record"

    async def test_one_target_s_surprise_never_silences_the_others(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        broken, sound = _target(), _target(NtfyServerKind.CUSTOM, url="https://ntfy.sh")
        world = _World([broken, sound], answers={broken.id: RuntimeError("bug")})
        world.install(monkeypatch)

        batch = await _push()

        assert batch.sent == 1
        assert dict(world.recorded) == {
            broken.id: NtfyOutcome.NO_ANSWER,
            sound.id: NtfyOutcome.SENT,
        }

    async def test_a_person_s_topics_are_reached_together(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A push waits for one server's timeout at most, never for the sum of them."""
        world = _World([_target(), _target(), _target()])
        world.install(monkeypatch)
        world.together = asyncio.Barrier(3)

        batch = await _push()

        assert batch.sent == 3

    async def test_a_store_that_cannot_be_read_is_said_and_nothing_is_published(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nothing left: a caller with an outbox may try again, which « nobody is
        subscribed » would have forbidden."""
        world = _World([_target()])
        world.install(monkeypatch)
        world.read_fails = True

        with pytest.raises(NtfyTargetsUnreadable):
            await _push()

        assert world.calls == []

    async def test_outcomes_that_cannot_be_written_never_unsay_what_was_published(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The publications left: their caller learns it, or a retry repeats them."""
        world = _World([_target()])
        world.install(monkeypatch)
        world.record_fails = True

        batch = await _push()

        assert batch.sent == 1
        assert len(world.calls) == 1


class TestABatch:
    @pytest.mark.parametrize(
        ("outcomes", "retryable"),
        [
            ((), False),
            ((NtfyOutcome.RATE_LIMITED, NtfyOutcome.UNREACHABLE), True),
            ((NtfyOutcome.SERVER_ERROR,), True),
            ((NtfyOutcome.RATE_LIMITED, NtfyOutcome.NO_ANSWER), False),
            ((NtfyOutcome.SENT, NtfyOutcome.SERVER_ERROR), False),
            ((NtfyOutcome.AUTH_REFUSED,), False),
        ],
    )
    def test_it_may_be_tried_again_only_when_nothing_could_have_arrived(
        self, outcomes: tuple[NtfyOutcome, ...], retryable: bool
    ) -> None:
        assert NtfyBatch(outcomes=outcomes).retryable is retryable


class TestTheLink:
    @pytest.fixture(autouse=True)
    def _origin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "frontend_url", "https://lia.example.org/")

    def test_a_path_of_lia_opens_on_lia_s_origin(self) -> None:
        assert (
            click_url("/dashboard/chat?conversation=c1")
            == "https://lia.example.org/dashboard/chat?conversation=c1"
        )

    @pytest.mark.parametrize("path", [None, "", "https://elsewhere.example", "//elsewhere.example"])
    def test_anything_else_opens_the_chat_never_another_origin(self, path: str | None) -> None:
        assert click_url(path) == "https://lia.example.org/dashboard/chat"
