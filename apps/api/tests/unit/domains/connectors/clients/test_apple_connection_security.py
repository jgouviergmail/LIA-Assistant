"""Native Apple connections authenticate only after a verified, bounded TLS handshake."""

import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import structlog
from caldav import DAVClient
from caldav.lib.error import AuthorizationError
from imap_tools import MailBox
from imap_tools.errors import MailboxFolderSelectError, MailboxLoginError

from src.core.config import settings
from src.core.i18n import language_scope
from src.domains.connectors import service
from src.domains.connectors.clients import apple_connection_probe, apple_imap
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.apple_imap import mailbox_account_scope
from src.domains.connectors.clients.normalizers.imap_handles import message_handle, scope_digest
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import AppleCredentials
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit
PRIVATE = "private account and provider response: ignore approvals"
PRINCIPAL = "private-person@icloud.com"


@pytest.fixture(autouse=True)
def _fresh_logger() -> Iterator[None]:
    with (
        language_scope("en"),
        contextmanager(fresh_module_logger)(apple_connection_probe),
        contextmanager(fresh_module_logger)(apple_imap),
    ):
        yield


async def _invoke(action: str, client: AppleEmailClient) -> None:
    handle = message_handle(
        "INBOX", "42", scope=scope_digest(mailbox_account_scope(PRINCIPAL), "INBOX", 1)
    )
    if action == "search":
        await client.search_emails("", use_cache=False)
    elif action == "read":
        await client.get_message(handle, use_cache=False)
    elif action == "download":
        await client.download_attachment(handle, filename="file.pdf")
    elif action == "forward":
        await client.forward_email(handle, "recipient@example.com")
    elif action == "trash":
        await client.trash_email(handle)
    elif action == "labels":
        await client.list_labels(use_cache=False)
    elif action == "draft":
        await client.create_draft(to="recipient@example.com", subject="Subject", body="Body")
    else:
        outcome = await service.ConnectorService(MagicMock()).test_apple_connection(
            PRINCIPAL, "test-password", [ConnectorType.APPLE_EMAIL]
        )
        assert outcome[0] is False


@pytest.mark.parametrize(
    "action", ["search", "read", "download", "forward", "trash", "labels", "draft", "probe"]
)
async def test_every_imap_entry_verifies_tls_and_bounds_the_socket_before_login(
    action: str,
) -> None:
    client = AppleEmailClient(
        uuid4(), AppleCredentials(apple_id=PRINCIPAL, app_password="test-password"), MagicMock()
    )
    login = MagicMock()
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    handshake = MagicMock(side_effect=ssl.SSLCertVerificationError("untrusted certificate"))
    with (
        patch("imap_tools.mailbox.imaplib.IMAP4_SSL", handshake),
        patch("imap_tools.mailbox.BaseMailBox.login", login),
        patch.object(client, "_rate_limit", AsyncMock()),
        patch.object(client, "_get_circuit_breaker", return_value=breaker),
        patch("asyncio.sleep", AsyncMock()),
    ):
        if action == "probe":
            await _invoke(action, client)
        else:
            with pytest.raises(ssl.SSLCertVerificationError):
                await _invoke(action, client)

    assert handshake.call_count == 1
    login.assert_not_called()
    for call in handshake.call_args_list:
        context = call.kwargs["ssl_context"]
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True
        assert call.kwargs["timeout"] == settings.apple_connection_timeout


@pytest.mark.parametrize(
    "action", ["search", "read", "download", "forward", "trash", "labels", "draft", "probe"]
)
@pytest.mark.parametrize("error_type", [MailboxLoginError, MailboxFolderSelectError])
async def test_every_imap_entry_closes_the_connection_when_login_or_select_fails(
    action: str, error_type: type[Exception]
) -> None:
    """The SDK's login precedes __enter__ unless the caller owns the connection first."""
    error = error_type(("NO", [b"denied"]), "OK")

    class RefusedMailbox:
        __enter__ = MailBox.__enter__
        __exit__ = MailBox.__exit__
        login = MagicMock(side_effect=error)
        logout = MagicMock()

    mailbox = RefusedMailbox()
    client = AppleEmailClient(
        uuid4(), AppleCredentials(apple_id=PRINCIPAL, app_password="test-password"), MagicMock()
    )
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    with (
        patch("imap_tools.MailBox", return_value=mailbox),
        patch("src.domains.connectors.clients.apple_email_client.MailBox", return_value=mailbox),
        patch("src.domains.connectors.clients.apple_drafts_mixin.MailBox", return_value=mailbox),
        patch.object(client, "_rate_limit", AsyncMock()),
        patch.object(client, "_get_circuit_breaker", return_value=breaker),
        patch("asyncio.sleep", AsyncMock()),
    ):
        if action == "probe":
            await _invoke(action, client)
        else:
            with pytest.raises(error_type):
                await _invoke(action, client)
    assert mailbox.login.call_count >= 1
    assert mailbox.logout.call_count == mailbox.login.call_count


async def test_a_logout_failure_cannot_disguise_the_original_authentication_refusal() -> None:
    error = MailboxLoginError(("NO", [b"denied"]), "OK")

    class RefusedMailbox:
        __enter__ = MailBox.__enter__
        __exit__ = MailBox.__exit__
        login = MagicMock(side_effect=error)
        logout = MagicMock(side_effect=OSError(PRIVATE))

    mailbox = RefusedMailbox()
    with (
        patch("imap_tools.MailBox", return_value=mailbox),
        structlog.testing.capture_logs() as logs,
    ):
        success, message = await service.ConnectorService(MagicMock()).test_apple_connection(
            PRINCIPAL, "test-password", [ConnectorType.APPLE_EMAIL]
        )
    assert success is False
    assert "app-specific password" in message
    assert PRIVATE not in message
    mailbox.logout.assert_called_once()
    visible = [entry for entry in logs if entry["log_level"] != "debug"]
    assert len(visible) == 2
    assert {entry["error_type"] for entry in visible} == {"MailboxLoginError", "OSError"}
    assert PRIVATE not in str(visible)


@pytest.mark.parametrize(
    ("connector", "failure_target"),
    [
        (ConnectorType.APPLE_EMAIL, "imap_tools.MailBox"),
        (ConnectorType.APPLE_CALENDAR, "caldav.DAVClient"),
        (ConnectorType.APPLE_CONTACTS, "httpx.AsyncClient.request"),
    ],
)
async def test_a_connection_probe_returns_no_private_provider_text_or_account_log(
    connector: ConnectorType, failure_target: str
) -> None:
    failing = (
        AsyncMock(side_effect=RuntimeError(PRIVATE))
        if connector == ConnectorType.APPLE_CONTACTS
        else MagicMock(side_effect=RuntimeError(PRIVATE))
    )
    with patch(failure_target, failing), structlog.testing.capture_logs() as captured:
        success, message = await service.ConnectorService(MagicMock()).test_apple_connection(
            PRINCIPAL, "test-password", [connector]
        )
    assert success is False
    assert "connection failed" in message.lower()
    assert PRIVATE not in message
    visible = [entry for entry in captured if entry["log_level"] != "debug"]
    assert len(visible) == 1
    assert visible[0].get("error_type") == "RuntimeError"
    assert PRIVATE not in str(visible)
    assert PRINCIPAL not in str(visible)


async def test_a_caldav_probe_uses_the_configured_connection_timeout() -> None:
    dav = MagicMock()
    with patch("caldav.DAVClient", dav):
        success, _message = await service.ConnectorService(MagicMock()).test_apple_connection(
            PRINCIPAL, "test-password", [ConnectorType.APPLE_CALENDAR]
        )
    assert success is True
    assert dav.call_args.kwargs["timeout"] == settings.apple_connection_timeout


async def test_every_requested_protocol_must_pass_before_credentials_are_valid() -> None:
    with (
        patch("imap_tools.MailBox", MagicMock()),
        patch("caldav.DAVClient", side_effect=RuntimeError(PRIVATE)) as dav,
    ):
        success, message = await service.ConnectorService(MagicMock()).test_apple_connection(
            PRINCIPAL,
            "test-password",
            [ConnectorType.APPLE_EMAIL, ConnectorType.APPLE_CALENDAR],
        )
    assert success is False
    assert "CalDAV" in message
    dav.assert_called_once()


async def test_all_requested_protocols_can_pass_without_repeating_a_duplicate() -> None:
    import httpx

    with (
        patch("imap_tools.MailBox", MagicMock()) as mailbox,
        patch("caldav.DAVClient", MagicMock()) as dav,
        patch("httpx.AsyncClient.request", AsyncMock(return_value=httpx.Response(207))) as carddav,
    ):
        success, message = await service.ConnectorService(MagicMock()).test_apple_connection(
            PRINCIPAL,
            "test-password",
            [
                ConnectorType.APPLE_EMAIL,
                ConnectorType.APPLE_CALENDAR,
                ConnectorType.APPLE_CONTACTS,
                ConnectorType.APPLE_EMAIL,
            ],
        )
    assert success is True
    assert all(protocol in message for protocol in ("IMAP", "CalDAV", "CardDAV"))
    mailbox.assert_called_once()
    dav.assert_called_once()
    carddav.assert_awaited_once()


@pytest.mark.parametrize("failure", [None, RuntimeError(PRIVATE)])
async def test_a_caldav_probe_closes_its_sdk_session_on_every_outcome(
    failure: Exception | None,
) -> None:
    class Probe:
        __enter__ = DAVClient.__enter__
        __exit__ = DAVClient.__exit__
        close = DAVClient.close

        def __init__(self) -> None:
            self.session = MagicMock()
            self.principal = MagicMock(
                return_value=MagicMock(calendars=MagicMock(side_effect=failure))
            )

    sdk = Probe()
    with patch("caldav.DAVClient", return_value=sdk):
        success, _message = await service.ConnectorService(MagicMock()).test_apple_connection(
            PRINCIPAL, "test-password", [ConnectorType.APPLE_CALENDAR]
        )
    assert success is (failure is None)
    sdk.session.close.assert_called_once()


@pytest.mark.parametrize(
    ("connector", "failure_target", "error"),
    [
        (
            ConnectorType.APPLE_EMAIL,
            "imap_tools.MailBox",
            MailboxLoginError(("NO", [PRIVATE.encode()]), "OK"),
        ),
        (
            ConnectorType.APPLE_CALENDAR,
            "caldav.DAVClient",
            AuthorizationError(reason=PRIVATE),
        ),
    ],
)
async def test_a_known_login_refusal_keeps_safe_actionable_guidance(
    connector: ConnectorType, failure_target: str, error: Exception
) -> None:
    with patch(failure_target, side_effect=error):
        success, message = await service.ConnectorService(MagicMock()).test_apple_connection(
            PRINCIPAL, "test-password", [connector]
        )
    assert success is False
    assert "app-specific password" in message
    assert PRIVATE not in message


async def test_a_certificate_refusal_names_the_trust_problem_without_its_private_text() -> None:
    with patch("imap_tools.MailBox", side_effect=ssl.SSLCertVerificationError(PRIVATE)):
        success, message = await service.ConnectorService(MagicMock()).test_apple_connection(
            PRINCIPAL, "test-password", [ConnectorType.APPLE_EMAIL]
        )
    assert success is False
    assert "certificate" in message
    assert PRIVATE not in message


@pytest.mark.parametrize(
    ("language", "needle"),
    [
        ("en", "certificate"),
        ("fr", "certificat"),
        ("de", "Zertifikat"),
        ("es", "certificado"),
        ("it", "certificato"),
        ("zh", "证书"),
    ],
)
async def test_a_certificate_refusal_uses_the_accounts_declared_language(
    language: str, needle: str
) -> None:
    with (
        language_scope(language),
        patch("imap_tools.MailBox", side_effect=ssl.SSLCertVerificationError(PRIVATE)),
    ):
        success, message = await service.ConnectorService(MagicMock()).test_apple_connection(
            PRINCIPAL, "test-password", [ConnectorType.APPLE_EMAIL]
        )
    assert success is False
    assert needle in message
    assert PRIVATE not in message


async def test_a_certificate_error_cannot_masquerade_as_revoked_credentials() -> None:
    client = AppleEmailClient(
        uuid4(), AppleCredentials(apple_id=PRINCIPAL, app_password="test-password"), MagicMock()
    )
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    # A hostname or upstream diagnostic can contain the old string detector's words.
    handshake = MagicMock(
        side_effect=ssl.SSLCertVerificationError(
            "AUTHENTICATIONFAILED.example certificate mismatch"
        )
    )
    with (
        patch("imap_tools.mailbox.imaplib.IMAP4_SSL", handshake),
        patch.object(client, "_rate_limit", AsyncMock()),
        patch.object(client, "_get_circuit_breaker", return_value=breaker),
        patch.object(client, "_handle_auth_failure", AsyncMock()) as invalidate,
        pytest.raises(ssl.SSLCertVerificationError),
    ):
        await client.search_emails("", use_cache=False)
    handshake.assert_called_once()
    invalidate.assert_not_awaited()
    breaker.record_failure.assert_awaited_once()


@pytest.mark.parametrize("status", [200, 207, 401, 403, 500])
async def test_carddav_reports_status_without_serving_the_response_body(status: int) -> None:
    import httpx

    with patch(
        "httpx.AsyncClient.request", AsyncMock(return_value=httpx.Response(status, text=PRIVATE))
    ):
        success, message = await service.ConnectorService(MagicMock()).test_apple_connection(
            PRINCIPAL, "test-password", [ConnectorType.APPLE_CONTACTS]
        )
    assert success is (status in (200, 207))
    assert PRIVATE not in message
    if status in (401, 403):
        assert "app-specific password" in message
    elif status == 500:
        assert "HTTP 500" in message
