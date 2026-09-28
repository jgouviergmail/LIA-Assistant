"""What each e-mail SAYS, decoded from the message the relay receives (ADR-323).

Before 2026-09-25 the verification and password-reset e-mails reached German,
Spanish, Italian and Chinese accounts in English (their catalogs lacked the
entries), the connector and new-registration e-mails were French for everyone,
the greeting and the ``label: value`` lines were English grammar in six
languages, and the name a person typed at registration was inserted raw into
the HTML sent to the administrator. The neighbouring module only checks that a
message left; this one reads it.
"""

from __future__ import annotations

import email
from collections.abc import Iterator
from email.header import decode_header, make_header
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.constants import (
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS,
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
)
from src.core.i18n import language_scope
from src.core.i18n_types import LANGUAGE_NAMES
from src.infrastructure.email.email_service import EmailService

pytestmark = pytest.mark.unit

NBSP = "\u00a0"


@pytest.fixture
def relay() -> Iterator[MagicMock]:
    """The SMTP relay the service talks to; ``sendmail`` holds the message."""
    with patch("src.infrastructure.email.email_service.smtplib.SMTP") as smtp:
        server = MagicMock()
        server.__enter__ = Mock(return_value=server)
        server.__exit__ = Mock(return_value=False)
        smtp.return_value = server
        yield server


@pytest.fixture
def service() -> Iterator[EmailService]:
    with patch("src.infrastructure.email.email_service.settings") as settings:
        settings.smtp_host = "smtp.example.com"
        settings.smtp_port = 587
        settings.smtp_user = ""
        settings.smtp_password = ""
        settings.smtp_from = "noreply@example.com"
        settings.frontend_url = "https://app.example.com"
        yield EmailService()


def _sent(relay: MagicMock) -> tuple[str, str, str]:
    """(subject, plain text, HTML) of the one message the relay received."""
    message = email.message_from_string(relay.sendmail.call_args.args[2])
    subject = str(make_header(decode_header(message["Subject"])))
    parts: dict[str, str] = {}
    for part in message.walk():
        if part.is_multipart():
            continue
        payload = part.get_payload(decode=True)
        assert isinstance(payload, bytes)
        parts[part.get_content_type()] = payload.decode(part.get_content_charset() or "utf-8")
    return subject, parts["text/plain"], parts["text/html"]


# --- the reader's language ---------------------------------------------------


@pytest.mark.asyncio
async def test_verification_email_is_german_for_a_german_account(
    service: EmailService, relay: MagicMock
) -> None:
    await service.send_email_verification(
        "ana@example.com", "Ana", "https://app.example.com/verify?t=x", user_language="de"
    )
    subject, text, html_part = _sent(relay)
    assert subject == "Bestätige die E-Mail-Adresse deines LIA-Kontos"
    assert "Meine E-Mail-Adresse bestätigen" in html_part
    assert "Bestätigungslink: https://app.example.com/verify?t=x" in text


@pytest.mark.asyncio
async def test_password_reset_email_is_chinese_for_a_chinese_account(
    service: EmailService, relay: MagicMock
) -> None:
    await service.send_password_reset(
        "ana@example.com", "Ana", "https://app.example.com/reset?t=x", user_language="zh"
    )
    subject, text, _html = _sent(relay)
    assert subject == "重置你的 LIA 密码"
    assert "重置链接：https://app.example.com/reset?t=x" in text


@pytest.mark.asyncio
async def test_connector_email_follows_the_reader_not_french(
    service: EmailService, relay: MagicMock
) -> None:
    await service.send_connector_disabled_notification(
        "ana@example.com", "Ana", "Gmail", "Maintenance", user_language="en"
    )
    subject, text, _html = _sent(relay)
    assert subject == "Connector Gmail disabled"
    assert "Reason: Maintenance" in text


@pytest.mark.asyncio
async def test_the_persons_language_wins_over_the_declared_one(
    service: EmailService, relay: MagicMock
) -> None:
    """An admin acting in Italian on a German account: the e-mail is German.
    The language is required, so no e-mail can fall back to the acting admin's."""
    with language_scope("it"):
        await service.send_user_activated_notification("ana@example.com", "Ana", "de")
    subject, _text, _html = _sent(relay)
    assert subject == "Dein LIA-Konto wurde reaktiviert"


@pytest.mark.asyncio
async def test_an_empty_stored_language_is_the_instance_default_not_the_declared(
    service: EmailService, relay: MagicMock
) -> None:
    """A person whose language is empty reads the instance default — never the
    language the acting administrator happens to declare (ADR-323). The default
    is pinned off French, so a French literal fallback cannot pass."""
    from src.core.config import settings
    from src.core.i18n import _

    with patch.object(settings, "default_language", "es"), language_scope("de"):
        await service.send_user_activated_notification("ana@example.com", "Ana", "")
    subject, _text, _html = _sent(relay)

    assert subject == _("Your LIA account has been reactivated", "es")
    assert subject != _("Your LIA account has been reactivated", "de")


@pytest.mark.asyncio
async def test_a_reason_nobody_gave_is_no_line(service: EmailService, relay: MagicMock) -> None:
    """It used to read « Reason: Non spécifiée » (deactivation) and « Raison : Raison
    non spécifiée » (connector), French for every reader."""
    await service.send_user_deactivated_notification("ana@example.com", "Ana", None, "en")
    _subject, text, html_part = _sent(relay)
    assert "Reason" not in text and "Reason" not in html_part
    assert _single_blank_lines(text)

    relay.sendmail.reset_mock()
    await service.send_connector_disabled_notification(
        "ana@example.com", "Ana", "Gmail", None, user_language="en"
    )
    _subject, text, html_part = _sent(relay)
    assert "Reason" not in text and "Reason" not in html_part
    assert _single_blank_lines(text)


@pytest.mark.asyncio
async def test_a_given_reason_is_its_own_paragraph(service: EmailService, relay: MagicMock) -> None:
    await service.send_user_deactivated_notification("ana@example.com", "Ana", "Abuse", "en")
    _subject, text, _html = _sent(relay)
    lines = [line.strip() for line in text.split("\n")]
    at = lines.index("Reason: Abuse")
    assert lines[at - 1] == "" and lines[at + 1] == ""
    assert _single_blank_lines(text)


def _single_blank_lines(text: str) -> bool:
    """No two blank lines in a row between paragraphs (whitespace-only lines count)."""
    lines = [line.strip() for line in text.strip().split("\n")]
    return all(lines[i] or lines[i + 1] for i in range(len(lines) - 1))


@pytest.mark.asyncio
async def test_the_connector_label_is_escaped_in_the_html(
    service: EmailService, relay: MagicMock
) -> None:
    await service.send_connector_disabled_notification(
        "ana@example.com", "Ana", "<b>Mail</b>", "Maintenance", user_language="en"
    )
    subject, text, html_part = _sent(relay)
    assert "<strong>&lt;b&gt;Mail&lt;/b&gt;</strong>" in html_part
    # Plain text and subject are not markup: they keep the label.
    assert subject == "Connector <b>Mail</b> disabled"


@pytest.mark.asyncio
async def test_admin_notification_speaks_the_admins_language(
    service: EmailService, relay: MagicMock
) -> None:
    await service.send_new_registration_admin_notification(
        "admin@example.com", "ana@example.com", "Ana", "google", admin_language="es"
    )
    subject, text, _html = _sent(relay)
    assert subject == "[LIA] Nuevo usuario pendiente de activación: ana@example.com"
    assert "Nombre: Ana" in text
    assert "Método: google" in text


@pytest.mark.parametrize("language", tuple(LANGUAGE_NAMES))
@pytest.mark.asyncio
async def test_no_english_leaks_into_another_languages_email(
    language: str, service: EmailService, relay: MagicMock
) -> None:
    """The subject and a sentence of the body come from the reader's catalog, never
    the English msgid (the catalog guard holds every entry, one by one)."""
    await service.send_pending_activation_notification("ana@example.com", "Ana", language)
    subject, text, _html = _sent(relay)
    if language == "en":
        assert subject == "Your LIA account is pending activation"
    else:
        assert "Your LIA account" not in subject
        assert "Thank you for your patience" not in text


# --- the language's grammar --------------------------------------------------


@pytest.mark.parametrize(
    ("language", "greeting"),
    [
        ("fr", "Bonjour Ana,"),
        ("en", "Hello Ana,"),
        ("es", "Hola, Ana:"),
        ("de", "Hallo Ana,"),
        ("it", "Ciao Ana,"),
        ("zh-CN", "Ana，你好！"),
    ],
)
@pytest.mark.asyncio
async def test_greeting_is_the_languages_own(
    language: str, greeting: str, service: EmailService, relay: MagicMock
) -> None:
    await service.send_user_activated_notification("ana@example.com", "Ana", language)
    _subject, text, html = _sent(relay)
    assert greeting in text
    assert f"<p>{greeting}</p>" in html


@pytest.mark.parametrize(
    ("language", "line"),
    [
        ("fr", f"Raison{NBSP}: Inactivité"),
        ("en", "Reason: Inactivité"),
        ("zh-CN", "原因：Inactivité"),
    ],
)
@pytest.mark.asyncio
async def test_label_punctuation_travels_with_the_language(
    language: str, line: str, service: EmailService, relay: MagicMock
) -> None:
    await service.send_user_deactivated_notification(
        "ana@example.com", "Ana", "Inactivité", language
    )
    _subject, text, _html = _sent(relay)
    assert line in text


# --- what a person typed -----------------------------------------------------


@pytest.mark.asyncio
async def test_a_registered_name_cannot_write_html_into_the_admins_email(
    service: EmailService, relay: MagicMock
) -> None:
    name = '<a href="https://evil.example">Activate now</a>'
    await service.send_new_registration_admin_notification(
        "admin@example.com", "ana@example.com", name, "email", admin_language="en"
    )
    _subject, text, html = _sent(relay)
    assert 'href="https://evil.example"' not in html
    assert "&lt;a href=&quot;https://evil.example&quot;&gt;" in html
    # The plain-text part is not markup: it keeps what was typed.
    assert f"Name: {name}" in text


@pytest.mark.asyncio
async def test_a_reason_cannot_write_html_into_the_users_email(
    service: EmailService, relay: MagicMock
) -> None:
    await service.send_user_deactivated_notification(
        "ana@example.com", "<b>Ana</b>", "<script>x()</script>", "en"
    )
    _subject, _text, html = _sent(relay)
    assert "<script>" not in html and "<b>Ana</b>" not in html
    assert "&lt;script&gt;x()&lt;/script&gt;" in html


# --- what the sentences claim ------------------------------------------------


@pytest.mark.asyncio
async def test_link_lifetimes_stated_are_the_lifetimes_enforced(
    service: EmailService, relay: MagicMock
) -> None:
    """The e-mails state the token lifetimes in prose, in six languages: a new
    lifetime in ``core/constants.py`` must come with new sentences."""
    await service.send_email_verification("a@example.com", "A", "https://x", "en")
    _subject, text, _html = _sent(relay)
    assert f"expires in {EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours" in text

    relay.sendmail.reset_mock()
    await service.send_password_reset("a@example.com", "A", "https://x", "en")
    _subject, text, _html = _sent(relay)
    assert PASSWORD_RESET_TOKEN_EXPIRE_HOURS == 1, "the reset e-mail says « 1 hour »"
    assert "expires in 1 hour" in text
