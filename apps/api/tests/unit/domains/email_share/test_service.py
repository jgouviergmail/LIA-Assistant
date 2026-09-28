"""Sending a file or an answer by e-mail — the decisions (ADR-321).

Which road a send takes, whom it may reach, what it refuses and how each
provider failure reaches the person. The database half (which files are the
person's live generated files) is proven on PostgreSQL in the integration
suite; here every seam is replaced and the DECISIONS are pinned.
"""

from __future__ import annotations

import smtplib
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import AuthenticationError, ConnectorAPIError, ExternalServiceError
from src.domains.connectors.active_client import ClientUnavailable
from src.domains.connectors.clients.base_apple_client import AppleAuthenticationError
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.models import ConnectorType
from src.domains.email_share import errors, service
from src.domains.email_share.schemas import EmailShareRequest
from src.infrastructure.email.outgoing import OutgoingAttachment, max_file_bytes

pytestmark = pytest.mark.unit


def _user(*, verified: bool = True, email: str = "me@example.com") -> Any:
    return SimpleNamespace(id=uuid4(), email=email, is_verified=verified)


def _request(**overrides: Any) -> EmailShareRequest:
    payload: dict[str, Any] = {
        "recipients": ["bob@example.com"],
        "subject": "Le compte rendu",
        "message": "Voici.",
        "attachment": {"kind": "markdown", "filename": "lia-2026-09-25-10-00", "text": "# Hi"},
    }
    payload.update(overrides)
    return EmailShareRequest.model_validate(payload)


def _code(exc: pytest.ExceptionInfo[Any]) -> str:
    return exc.value.detail["code"]


@pytest.fixture
def connectors() -> Any:
    """The connector reads the route takes, all replaced."""
    unit = MagicMock()

    @asynccontextmanager
    async def _unit_of_work() -> Any:
        yield unit

    with (
        patch.object(service, "DetachedConnectorService") as detached,
        patch.object(service, "resolve_active_connector", AsyncMock(return_value=None)) as active,
        patch.object(service, "find_error_connector_type", AsyncMock(return_value=None)) as broken,
    ):
        detached.return_value.unit_of_work = _unit_of_work
        yield SimpleNamespace(active=active, broken=broken)


class TestTheRoad:
    async def test_a_connected_mailbox_is_the_road_with_its_own_ceiling(
        self, connectors: Any
    ) -> None:
        connectors.active.return_value = ConnectorType.GOOGLE_GMAIL

        route = await service.resolve_route(_user())

        assert route.kind == "mailbox"
        assert route.max_file_bytes == GoogleGmailClient.OUTGOING_FILE_MAX_BYTES
        assert route.own_address is None

    async def test_without_a_mailbox_the_relay_writes_to_the_verified_address(
        self, connectors: Any
    ) -> None:
        route = await service.resolve_route(_user())

        assert route.kind == "relay"
        assert route.own_address == "me@example.com"
        assert route.max_file_bytes == max_file_bytes(settings.email_share_relay_max_message_bytes)

    async def test_an_unverified_address_is_no_road_at_all(self, connectors: Any) -> None:
        # ADR-314: an account opened with someone else's address would turn the
        # relay into a relay aimed at that someone.
        route = await service.resolve_route(_user(verified=False))

        assert route.kind == "unavailable"
        assert route.own_address is None

    async def test_a_broken_mailbox_is_said_while_the_relay_serves(self, connectors: Any) -> None:
        connectors.broken.return_value = "google_gmail"

        route = await service.resolve_route(_user())

        assert (route.kind, route.needs_reconnect) == ("relay", True)


class TestWhoMayBeReached:
    async def test_a_mailbox_send_needs_a_recipient(self) -> None:
        route = service.ShareRoute.mailbox(ConnectorType.GOOGLE_GMAIL, max_file_bytes=10**6)

        with pytest.raises(Exception) as refused:
            await service.prepare_share(MagicMock(), _user(), _request(recipients=[]), route)

        assert _code(refused) == errors.NO_RECIPIENT

    async def test_the_relay_refuses_anyone_but_the_account_itself(self) -> None:
        route = service.ShareRoute.relay("me@example.com", max_file_bytes=10**6)

        with pytest.raises(Exception) as refused:
            await service.prepare_share(MagicMock(), _user(), _request(), route)

        assert _code(refused) == errors.RECIPIENTS_LOCKED

    async def test_the_relay_accepts_its_own_address_however_it_is_cased(self) -> None:
        route = service.ShareRoute.relay("me@example.com", max_file_bytes=10**6)

        prepared = await service.prepare_share(
            MagicMock(), _user(), _request(recipients=["Me@Example.com"]), route
        )

        assert prepared.recipients == ["me@example.com"]

    async def test_no_road_refuses_before_reading_anything(self) -> None:
        with pytest.raises(Exception) as refused:
            await service.prepare_share(
                MagicMock(), _user(verified=False), _request(), service.ShareRoute.unavailable()
            )

        assert _code(refused) == errors.UNAVAILABLE

    async def test_a_recipient_named_twice_receives_it_once(self) -> None:
        route = service.ShareRoute.mailbox(ConnectorType.GOOGLE_GMAIL, max_file_bytes=10**6)

        prepared = await service.prepare_share(
            MagicMock(),
            _user(),
            _request(recipients=["bob@example.com", "BOB@example.com", "eve@example.com"]),
            route,
        )

        assert prepared.recipients == ["bob@example.com", "eve@example.com"]


class TestTheAnswerAsAFile:
    async def test_an_answer_travels_as_the_md_file_download_writes(self) -> None:
        route = service.ShareRoute.mailbox(ConnectorType.GOOGLE_GMAIL, max_file_bytes=10**6)

        prepared = await service.prepare_share(MagicMock(), _user(), _request(), route)

        attachment = await prepared.source.read()
        assert attachment == OutgoingAttachment(
            filename="lia-2026-09-25-10-00.md",
            mime_type="text/markdown",
            data=b"# Hi",
            charset="utf-8",
        )

    async def test_a_file_larger_than_the_road_is_refused_with_the_ceiling(self) -> None:
        route = service.ShareRoute.mailbox(ConnectorType.MICROSOFT_OUTLOOK, max_file_bytes=3)

        with pytest.raises(Exception) as refused:
            await service.prepare_share(MagicMock(), _user(), _request(), route)

        assert refused.value.status_code == 413
        assert refused.value.detail == {"code": errors.TOO_LARGE, "max_bytes": 3}


class TestTheStoredFile:
    async def test_a_file_swept_since_the_check_is_gone_and_nothing_leaves(
        self, tmp_path: Path
    ) -> None:
        prepared = service.PreparedShare(
            route=service.ShareRoute.relay("me@example.com", max_file_bytes=10**6),
            recipients=["me@example.com"],
            subject="Sujet",
            message=None,
            source=service.StoredFile(
                path=tmp_path / "missing.png", filename="x.png", mime_type="image/png", size=3
            ),
        )
        relay = MagicMock(send_email=AsyncMock(return_value=True))

        with (
            patch.object(service, "get_email_service", return_value=relay),
            pytest.raises(Exception) as refused,
        ):
            await service.deliver_share(uuid4(), prepared)

        assert _code(refused) == errors.FILE_GONE
        relay.send_email.assert_not_awaited()

    async def test_its_bytes_are_read_under_its_name(self, tmp_path: Path) -> None:
        stored = tmp_path / "f.png"
        stored.write_bytes(b"\x89PNG")

        attachment = await service.StoredFile(
            path=stored, filename="Plan.png", mime_type="image/png", size=4
        ).read()

        assert attachment == OutgoingAttachment("Plan.png", "image/png", b"\x89PNG")


def _prepared(route: service.ShareRoute, recipients: list[str]) -> service.PreparedShare:
    return service.PreparedShare(
        route=route,
        recipients=recipients,
        subject="Sujet",
        message=None,
        source=service.InlineFile(OutgoingAttachment("a.md", "text/markdown", b"x", "utf-8")),
    )


@asynccontextmanager
async def _opened(client: Any) -> Any:
    yield SimpleNamespace(client=client, connector_type=ConnectorType.GOOGLE_GMAIL)


class TestDeliveryThroughTheMailbox:
    _ROUTE = service.ShareRoute.mailbox(ConnectorType.GOOGLE_GMAIL, max_file_bytes=10**6)

    async def test_the_mailbox_sends_the_words_and_the_file(self) -> None:
        client = MagicMock(send_email=AsyncMock(return_value={"id": "m"}))

        with patch.object(service, "open_active_client", lambda *_a, **_k: _opened(client)):
            result = await service.deliver_share(
                uuid4(), _prepared(self._ROUTE, ["bob@example.com", "eve@example.com"])
            )

        kwargs = client.send_email.await_args.kwargs
        assert kwargs["to"] == "bob@example.com, eve@example.com"
        assert kwargs["subject"] == "Sujet"
        assert kwargs["body"] == ""  # nothing is written in the person's place
        assert [a.filename for a in kwargs["attachments"]] == ["a.md"]
        assert (result.route, result.recipients) == ("mailbox", 2)

    @pytest.mark.parametrize(
        ("failure", "code"),
        [
            (AuthenticationError(detail="x"), errors.RECONNECT),
            (AppleAuthenticationError(ConnectorType.APPLE_EMAIL, "x"), errors.RECONNECT),
            (ConnectorAPIError("google_gmail", 400, "bad"), errors.REFUSED),
            (smtplib.SMTPDataError(552, b"too big"), errors.REFUSED),
            (ExternalServiceError("google_gmail", "down"), errors.FAILED),
            (TimeoutError(), errors.FAILED),
        ],
    )
    async def test_each_failure_reaches_the_person_as_what_it_is(
        self, failure: Exception, code: str
    ) -> None:
        client = MagicMock(send_email=AsyncMock(side_effect=failure))

        with (
            patch.object(service, "open_active_client", lambda *_a, **_k: _opened(client)),
            pytest.raises(Exception) as refused,
        ):
            await service.deliver_share(uuid4(), _prepared(self._ROUTE, ["bob@example.com"]))

        assert _code(refused) == code

    async def test_a_mailbox_gone_since_the_check_is_no_road(self) -> None:
        @asynccontextmanager
        async def _gone(*_a: Any, **_k: Any) -> Any:
            yield ClientUnavailable.NO_CONNECTOR

        with (
            patch.object(service, "open_active_client", _gone),
            pytest.raises(Exception) as refused,
        ):
            await service.deliver_share(uuid4(), _prepared(self._ROUTE, ["bob@example.com"]))

        assert _code(refused) == errors.UNAVAILABLE


class _Recorder:
    """The action register as the seam sees it: what was claimed, how it settled."""

    def __init__(self) -> None:
        self.claimed: list[tuple[Any, str, dict[str, str]]] = []
        self.settled: list[bool] = []

    async def claim(self, *, user_id: Any, capability: str, arguments: dict[str, str]) -> Any:
        self.claimed.append((user_id, capability, arguments))
        return "ticket"

    async def settle(self, ticket: Any, *, succeeded: bool) -> None:
        self.settled.append(succeeded)


@pytest.fixture
def register() -> Any:
    """A register installed in the seam for the test; the previous one put back."""
    from src.domains.shared import action_sink

    previous = action_sink._recorder
    recorder = _Recorder()
    action_sink.install_action_recorder(recorder)
    yield recorder
    action_sink._recorder = previous


class TestTheSendIsAnAction:
    """ADR-263: the person's send is claimed before it leaves, settled from the provider."""

    _MAILBOX = service.ShareRoute.mailbox(ConnectorType.GOOGLE_GMAIL, max_file_bytes=10**6)
    _RELAY = service.ShareRoute.relay("me@example.com", max_file_bytes=10**6)

    async def test_a_sent_message_is_recorded_with_how_many_it_was_written_to(
        self, register: _Recorder
    ) -> None:
        client = MagicMock(send_email=AsyncMock(return_value={"id": "m"}))
        user_id = uuid4()

        with patch.object(service, "open_active_client", lambda *_a, **_k: _opened(client)):
            await service.deliver_share(
                user_id, _prepared(self._MAILBOX, ["bob@example.com", "eve@example.com"])
            )

        assert register.claimed == [(user_id, "email_share", {"count": "2"})]
        assert register.settled == [True]

    async def test_a_send_the_provider_refused_settles_as_a_failure(
        self, register: _Recorder
    ) -> None:
        relay = MagicMock(send_email=AsyncMock(return_value=False))

        with (
            patch.object(service, "get_email_service", return_value=relay),
            pytest.raises(Exception),
        ):
            await service.deliver_share(uuid4(), _prepared(self._RELAY, ["me@example.com"]))

        assert register.settled == [False]

    async def test_a_file_gone_before_anything_left_is_no_act(
        self, register: _Recorder, tmp_path: Path
    ) -> None:
        prepared = replace(
            _prepared(self._RELAY, ["me@example.com"]),
            source=service.StoredFile(
                path=tmp_path / "missing.png", filename="x.png", mime_type="image/png", size=3
            ),
        )

        with pytest.raises(Exception):
            await service.deliver_share(uuid4(), prepared)

        assert register.claimed == []


class TestDeliveryThroughTheRelay:
    _ROUTE = service.ShareRoute.relay("me@example.com", max_file_bytes=10**6)

    async def test_the_relay_writes_to_the_account_and_escapes_the_words(self) -> None:
        relay = MagicMock(send_email=AsyncMock(return_value=True))
        prepared = replace(_prepared(self._ROUTE, ["me@example.com"]), message="<b>hi</b>")

        with patch.object(service, "get_email_service", return_value=relay):
            result = await service.deliver_share(uuid4(), prepared)

        to_email, subject, html_body, text_body = relay.send_email.await_args.args
        assert (to_email, subject, text_body) == ("me@example.com", "Sujet", "<b>hi</b>")
        assert "&lt;b&gt;hi&lt;/b&gt;" in html_body
        assert [a.filename for a in relay.send_email.await_args.kwargs["attachments"]] == ["a.md"]
        assert result.route == "relay"

    async def test_a_relay_that_did_not_take_it_says_so(self) -> None:
        relay = MagicMock(send_email=AsyncMock(return_value=False))

        with (
            patch.object(service, "get_email_service", return_value=relay),
            pytest.raises(Exception) as refused,
        ):
            await service.deliver_share(uuid4(), _prepared(self._ROUTE, ["me@example.com"]))

        assert _code(refused) == errors.FAILED
