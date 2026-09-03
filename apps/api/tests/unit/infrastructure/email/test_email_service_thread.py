"""EmailService: the blocking smtplib exchange never runs on the event loop."""

from __future__ import annotations

import threading

import pytest

from src.infrastructure.email import email_service as module

pytestmark = pytest.mark.unit


class _RecordingSmtp:
    """A stand-in for ``smtplib.SMTP`` that records where and what it was asked to send."""

    seen: dict[str, object] = {}

    def __init__(self, host: str, port: int) -> None:
        _RecordingSmtp.seen["thread"] = threading.current_thread().name
        _RecordingSmtp.seen["host"] = (host, port)

    def __enter__(self) -> _RecordingSmtp:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self) -> None:
        _RecordingSmtp.seen["tls"] = True

    def login(self, user: str, password: str) -> None:
        _RecordingSmtp.seen["login"] = (user, password)

    def sendmail(self, sender: str, to: str, payload: str) -> None:
        _RecordingSmtp.seen["from"] = sender
        _RecordingSmtp.seen["to"] = to
        _RecordingSmtp.seen["payload"] = payload


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> type[_RecordingSmtp]:
    _RecordingSmtp.seen = {}
    monkeypatch.setattr(module.smtplib, "SMTP", _RecordingSmtp)
    monkeypatch.setattr(module.settings, "alertmanager_smtp_smarthost", "relay.test:2525")
    monkeypatch.setattr(module.settings, "application_smtp_from", "lia@example.test")
    monkeypatch.setattr(module.settings, "alertmanager_smtp_auth_username", "")
    monkeypatch.setattr(module.settings, "alertmanager_smtp_auth_password", "")
    return _RecordingSmtp


async def test_send_email_runs_smtp_in_a_worker_thread_with_the_platform_sender(
    smtp: type[_RecordingSmtp],
) -> None:
    ok = await module.EmailService().send_email("me@example.test", "S", "<p>h</p>", "t")

    assert ok is True
    assert smtp.seen["from"] == "lia@example.test"
    assert smtp.seen["to"] == "me@example.test"
    assert smtp.seen["host"] == ("relay.test", 2525)
    # asyncio.to_thread: the exchange happened off the loop's thread.
    assert smtp.seen["thread"] != threading.main_thread().name
    assert "From: lia@example.test" in str(smtp.seen["payload"])
    # No credentials → no TLS, no login (the private-relay contract of 2026-08-06).
    assert "tls" not in smtp.seen and "login" not in smtp.seen


async def test_credentials_turn_on_tls_then_login_in_that_order(
    smtp: type[_RecordingSmtp], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module.settings, "alertmanager_smtp_auth_username", "u")
    monkeypatch.setattr(module.settings, "alertmanager_smtp_auth_password", "p")
    ok = await module.EmailService().send_email("me@example.test", "S", "<p>h</p>")
    assert ok is True
    assert smtp.seen["tls"] is True and smtp.seen["login"] == ("u", "p")


async def test_a_relay_failure_answers_false_never_raises(
    smtp: type[_RecordingSmtp], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(self: object, *args: object) -> None:
        raise ConnectionRefusedError("relay down")

    monkeypatch.setattr(_RecordingSmtp, "sendmail", _boom)
    ok = await module.EmailService().send_email("me@example.test", "S", "<p>h</p>")
    assert ok is False
