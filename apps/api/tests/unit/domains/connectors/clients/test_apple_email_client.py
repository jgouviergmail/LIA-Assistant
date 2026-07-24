"""Unit tests for AppleEmailClient (IMAP/SMTP provider for the ``email`` category).

The module shipped with no direct coverage while implementing the same
``EmailClientProtocol`` as ``GoogleGmailClient`` and ``MicrosoftOutlookClient``.
These tests pin the behaviours a provider swap must preserve:

1. **Cache freshness** — ``GoogleGmailClient`` stores ``cached_at`` INSIDE the
   cached payload and returns it on a hit; the Apple cache stored nothing, so
   ``calculate_cache_age_seconds`` could never report the age of Apple data.
2. **Reply/forward composition** — subject prefixing, threading headers,
   reply-all recipient sets and quoted bodies are the recurring asymmetry
   between providers.
3. **Auth-failure classification** — an IMAP/SMTP credential error must raise
   ``AppleAuthenticationError`` so the connector gets marked as ERROR.

Everything network-facing (``MailBox``, ``smtplib.SMTP``) is replaced by a
double; ``asyncio.to_thread`` still runs the real synchronous closure, so the
production code path is exercised end to end.
"""

import json
from email.mime.multipart import MIMEMultipart
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.field_names import FIELD_CACHED_AT
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.base_apple_client import AppleAuthenticationError
from src.domains.connectors.schemas import AppleCredentials

pytestmark = pytest.mark.unit

MODULE = "src.domains.connectors.clients.apple_email_client"


# ============================================================================
# FIXTURES / DOUBLES
# ============================================================================


@pytest.fixture
def credentials() -> AppleCredentials:
    return AppleCredentials(apple_id="jane@icloud.com", app_password="abcd-efgh-ijkl-mnop")


@pytest.fixture
def client(credentials: AppleCredentials) -> AppleEmailClient:
    return AppleEmailClient(
        user_id=uuid4(),
        credentials=credentials,
        connector_service=MagicMock(),
    )


def _fake_redis() -> AsyncMock:
    """Redis stand-in backed by an in-memory dict."""
    store: dict[str, str] = {}
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=lambda key: store.get(key))

    async def _set(key: str, value: str, ex: int | None = None) -> None:
        store[key] = value

    redis.set = AsyncMock(side_effect=_set)
    redis.delete = AsyncMock(side_effect=lambda key: store.pop(key, None))
    redis._store = store
    return redis


def _mail_message(
    uid: str = "42",
    subject: str = "Quarterly report",
    from_: str = "bob@example.com",
    to: tuple[str, ...] = ("jane@icloud.com",),
    cc: tuple[str, ...] = (),
    text: str = "Here is the report.",
) -> SimpleNamespace:
    """imap_tools MailMessage stand-in (only the attributes the normalizer reads)."""
    return SimpleNamespace(
        uid=uid,
        subject=subject,
        from_=from_,
        to=list(to),
        cc=list(cc),
        date_str="Mon, 20 Jul 2026 09:00:00 +0000",
        date=None,
        text=text,
        html="",
        flags=(),
        size=len(text),
        attachments=[],
        headers={"message-id": ("<original@example.com>",)},
    )


class _FakeMailBox:
    """MailBox double: ``MailBox(host, port).login(user, password)`` -> context manager."""

    def __init__(self, messages: list[SimpleNamespace] | None = None) -> None:
        self.messages = messages or []
        self.folder = MagicMock()
        self.folder.list = MagicMock(return_value=[SimpleNamespace(name="INBOX")])
        self.fetch_calls: list[tuple] = []
        self.moved: list[tuple] = []

    def __call__(self, *args, **kwargs):  # MailBox(host, port)
        return self

    def login(self, *args, **kwargs):  # .login(user, password)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def fetch(self, criteria=None, limit=None, mark_seen=False, reverse=False):
        self.fetch_calls.append((criteria, limit, mark_seen, reverse))
        return list(self.messages[:limit] if limit else self.messages)

    def move(self, uids, folder):
        self.moved.append((tuple(uids), folder))


# ============================================================================
# CACHE FRESHNESS CONTRACT (parity with GoogleGmailClient)
# ============================================================================


class TestMessageCacheFreshness:
    """``cached_at`` must carry the cache WRITE time, like the Gmail client."""

    async def test_search_caches_each_message_with_a_write_timestamp(
        self, client: AppleEmailClient
    ) -> None:
        redis = _fake_redis()
        mailbox = _FakeMailBox([_mail_message(uid="42")])

        with (
            patch(f"{MODULE}.MailBox", mailbox),
            patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)),
        ):
            result = await client._search_emails_impl("in:inbox", 10, None, True)

        assert result["messages"] == [{"id": "42"}]
        assert result["from_cache"] is False
        assert result[FIELD_CACHED_AT] is None

        cached = json.loads(redis._store[f"apple_email:{client.user_id}:msg:42"])
        assert cached[FIELD_CACHED_AT], "the cached payload must record when it was written"

    async def test_cache_hit_reports_the_write_timestamp(self, client: AppleEmailClient) -> None:
        """Regression: a cache hit reported ``from_cache`` without any age."""
        redis = _fake_redis()
        written_at = "2020-01-01T00:00:00+00:00"
        redis._store[f"apple_email:{client.user_id}:msg:42"] = json.dumps(
            {"id": "42", "subject": "Quarterly report", FIELD_CACHED_AT: written_at}
        )

        with patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)):
            result = await client._get_message_impl("42", "full", None, True)

        assert result["from_cache"] is True
        assert result[FIELD_CACHED_AT] == written_at

    async def test_legacy_cache_entry_without_timestamp_stays_readable(
        self, client: AppleEmailClient
    ) -> None:
        redis = _fake_redis()
        redis._store[f"apple_email:{client.user_id}:msg:42"] = json.dumps(
            {"id": "42", "subject": "Quarterly report"}
        )

        with patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)):
            result = await client._get_message_impl("42", "full", None, True)

        assert result["from_cache"] is True
        assert result[FIELD_CACHED_AT] is None

    async def test_cache_miss_fetches_from_imap_and_stores_the_timestamp(
        self, client: AppleEmailClient
    ) -> None:
        redis = _fake_redis()
        mailbox = _FakeMailBox([_mail_message(uid="42")])

        with (
            patch(f"{MODULE}.MailBox", mailbox),
            patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)),
        ):
            result = await client._get_message_impl("42", "full", None, True)

        assert result["from_cache"] is False
        assert result[FIELD_CACHED_AT] is None

        cached = json.loads(redis._store[f"apple_email:{client.user_id}:msg:42"])
        assert cached[FIELD_CACHED_AT]

    async def test_use_cache_false_bypasses_the_cache(self, client: AppleEmailClient) -> None:
        redis = _fake_redis()
        redis._store[f"apple_email:{client.user_id}:msg:42"] = json.dumps({"id": "42"})
        mailbox = _FakeMailBox([_mail_message(uid="42", subject="Fresh")])

        with (
            patch(f"{MODULE}.MailBox", mailbox),
            patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)),
        ):
            result = await client._get_message_impl("42", "full", None, False)

        assert result["from_cache"] is False
        assert result["subject"] == "Fresh"

    async def test_message_missing_in_every_folder_raises(self, client: AppleEmailClient) -> None:
        redis = _fake_redis()
        mailbox = _FakeMailBox([])

        with (
            patch(f"{MODULE}.MailBox", mailbox),
            patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)),
            pytest.raises(ValueError, match="not found"),
        ):
            await client._get_message_impl("999", "full", None, True)


# ============================================================================
# SEARCH SEMANTICS
# ============================================================================


class TestSearchEmails:
    """Query translation, volumetry cap and folder targeting."""

    async def test_applies_the_global_volumetry_cap(self, client: AppleEmailClient) -> None:
        from src.domains.connectors.clients.base_google_client import apply_max_items_limit

        redis = _fake_redis()
        mailbox = _FakeMailBox([])

        with (
            patch(f"{MODULE}.MailBox", mailbox),
            patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)),
        ):
            await client._search_emails_impl("in:inbox", 10_000, None, True)

        _criteria, limit, _mark_seen, reverse = mailbox.fetch_calls[0]
        assert limit == apply_max_items_limit(10_000)
        assert reverse is True, "most recent first, like the Gmail list endpoint"

    async def test_folder_scoped_query_switches_folder(self, client: AppleEmailClient) -> None:
        redis = _fake_redis()
        mailbox = _FakeMailBox([])

        with (
            patch(f"{MODULE}.MailBox", mailbox),
            patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)),
        ):
            await client._search_emails_impl("in:sent", 5, None, True)

        assert mailbox.folder.set.called, "a non-INBOX query must select the target folder"

    async def test_returns_ids_only_like_the_gmail_list_endpoint(
        self, client: AppleEmailClient
    ) -> None:
        redis = _fake_redis()
        mailbox = _FakeMailBox([_mail_message(uid="1"), _mail_message(uid="2")])

        with (
            patch(f"{MODULE}.MailBox", mailbox),
            patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)),
        ):
            result = await client._search_emails_impl("in:inbox", 10, None, True)

        assert result["messages"] == [{"id": "1"}, {"id": "2"}]
        assert result["resultSizeEstimate"] == 2

    async def test_imap_auth_failure_is_classified(self, client: AppleEmailClient) -> None:
        redis = _fake_redis()
        mailbox = _FakeMailBox([])
        mailbox.fetch = MagicMock(side_effect=RuntimeError("LOGIN failed: bad password"))

        with (
            patch(f"{MODULE}.MailBox", mailbox),
            patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)),
            pytest.raises(AppleAuthenticationError),
        ):
            await client._search_emails_impl("in:inbox", 10, None, True)


# ============================================================================
# COMPOSITION: SEND / REPLY / FORWARD
# ============================================================================


class TestSendEmail:
    """SMTP envelope composition."""

    async def test_send_uses_all_recipient_headers(self, client: AppleEmailClient) -> None:
        sent: dict = {}

        async def _capture(recipients, msg):
            sent["recipients"] = recipients
            sent["msg"] = msg

        with patch.object(client, "_smtp_send", AsyncMock(side_effect=_capture)):
            result = await client._send_email_impl(
                to="bob@example.com",
                subject="Hello",
                body="Body text",
                cc="carol@example.com",
                bcc="dave@example.com",
                is_html=False,
            )

        assert result["labelIds"] == ["Sent"]
        assert set(sent["recipients"]) == {
            "bob@example.com",
            "carol@example.com",
            "dave@example.com",
        }
        assert sent["msg"]["Subject"] == "Hello"
        assert sent["msg"]["Bcc"] is None, "Bcc must not leak into the message headers"

    async def test_smtp_auth_failure_is_classified(self, client: AppleEmailClient) -> None:
        import smtplib

        smtp = MagicMock()
        smtp.__enter__ = MagicMock(return_value=smtp)
        smtp.__exit__ = MagicMock(return_value=False)
        smtp.login = MagicMock(
            side_effect=smtplib.SMTPAuthenticationError(535, b"5.7.8 auth failed")
        )

        with (
            patch("smtplib.SMTP", MagicMock(return_value=smtp)),
            pytest.raises(AppleAuthenticationError),
        ):
            await client._smtp_send(["bob@example.com"], MIMEMultipart())


class TestReplyEmail:
    """Reply subject, threading headers, reply-all recipients and quoting."""

    ORIGINAL = {
        "body": "Original body",
        "payload": {
            "headers": [
                {"name": "From", "value": "bob@example.com"},
                {"name": "To", "value": "jane@icloud.com, carol@example.com"},
                {"name": "Cc", "value": "dave@example.com"},
                {"name": "Subject", "value": "Quarterly report"},
                {"name": "Date", "value": "Mon, 20 Jul 2026 09:00:00 +0000"},
                {"name": "Message-ID", "value": "<original@example.com>"},
            ]
        },
    }

    async def _reply(self, client: AppleEmailClient, **kwargs) -> dict:
        captured: dict = {}

        async def _capture(recipients, msg):
            captured["recipients"] = recipients
            captured["msg"] = msg

        with (
            patch.object(client, "get_message", AsyncMock(return_value=self.ORIGINAL)),
            patch.object(client, "_smtp_send", AsyncMock(side_effect=_capture)),
        ):
            captured["result"] = await client._reply_email_impl(**kwargs)
        return captured

    async def test_prefixes_subject_once(self, client: AppleEmailClient) -> None:
        captured = await self._reply(
            client, message_id="42", body="Thanks", reply_all=False, is_html=False
        )
        assert captured["msg"]["Subject"] == "Re: Quarterly report"

    async def test_existing_re_prefix_is_not_duplicated(self, client: AppleEmailClient) -> None:
        original = {
            **self.ORIGINAL,
            "payload": {"headers": [{"name": "Subject", "value": "Re: X"}]},
        }
        captured: dict = {}

        async def _capture(recipients, msg):
            captured["msg"] = msg

        with (
            patch.object(client, "get_message", AsyncMock(return_value=original)),
            patch.object(client, "_smtp_send", AsyncMock(side_effect=_capture)),
        ):
            await client._reply_email_impl("42", "Thanks", False, False)

        assert captured["msg"]["Subject"] == "Re: X"

    async def test_sets_threading_headers_from_the_original_message_id(
        self, client: AppleEmailClient
    ) -> None:
        captured = await self._reply(
            client, message_id="42", body="Thanks", reply_all=False, is_html=False
        )
        assert captured["msg"]["In-Reply-To"] == "<original@example.com>"
        assert captured["msg"]["References"] == "<original@example.com>"

    async def test_simple_reply_targets_only_the_original_sender(
        self, client: AppleEmailClient
    ) -> None:
        captured = await self._reply(
            client, message_id="42", body="Thanks", reply_all=False, is_html=False
        )
        assert captured["msg"]["To"] == "bob@example.com"
        assert captured["msg"]["Cc"] is None
        assert captured["recipients"] == ["bob@example.com"]

    async def test_reply_all_keeps_other_recipients_and_excludes_self(
        self, client: AppleEmailClient
    ) -> None:
        captured = await self._reply(
            client, message_id="42", body="Thanks", reply_all=True, is_html=False
        )
        cc = captured["msg"]["Cc"]
        assert "carol@example.com" in cc
        assert "dave@example.com" in cc
        assert "jane@icloud.com" not in cc, "the sender must never be cc'ed on their own reply"

    async def test_explicit_recipient_overrides_the_original_sender(
        self, client: AppleEmailClient
    ) -> None:
        captured = await self._reply(
            client,
            message_id="42",
            body="Thanks",
            reply_all=False,
            is_html=False,
            to="erin@example.com",
        )
        assert captured["msg"]["To"] == "erin@example.com"

    async def test_plain_text_reply_quotes_the_original_body(
        self, client: AppleEmailClient
    ) -> None:
        captured = await self._reply(
            client, message_id="42", body="Thanks", reply_all=False, is_html=False
        )
        payload = captured["msg"].get_payload()[0].get_payload(decode=True).decode("utf-8")
        assert "Thanks" in payload
        assert "> Original body" in payload

    async def test_html_reply_does_not_inject_plain_text_quoting(
        self, client: AppleEmailClient
    ) -> None:
        captured = await self._reply(
            client, message_id="42", body="<p>Thanks</p>", reply_all=False, is_html=True
        )
        part = captured["msg"].get_payload()[0]
        assert part.get_content_subtype() == "html"
        assert "> Original body" not in part.get_payload(decode=True).decode("utf-8")


class TestForwardEmail:
    """Forward header block, attachment propagation and subject prefixing."""

    def _mailbox_with_attachment(self) -> _FakeMailBox:
        message = _mail_message(uid="42")
        message.attachments = [
            SimpleNamespace(filename="report.pdf", content_type="application/pdf", payload=b"%PDF")
        ]
        return _FakeMailBox([message])

    async def test_forward_prefixes_subject_and_includes_original_headers(
        self, client: AppleEmailClient
    ) -> None:
        captured: dict = {}

        async def _capture(recipients, msg):
            captured["recipients"] = recipients
            captured["msg"] = msg

        with (
            patch(f"{MODULE}.MailBox", self._mailbox_with_attachment()),
            patch.object(client, "_smtp_send", AsyncMock(side_effect=_capture)),
        ):
            result = await client._forward_email_impl(
                "42", "erin@example.com", None, None, False, True
            )

        assert captured["msg"]["Subject"] == "Fwd: Quarterly report"
        body = captured["msg"].get_payload()[0].get_payload(decode=True).decode("utf-8")
        assert "Forwarded message" in body
        assert "bob@example.com" in body
        assert result["attachments_forwarded"] == 1
        assert result["attachment_names"] == ["report.pdf"]

    async def test_include_attachments_false_drops_them(self, client: AppleEmailClient) -> None:
        with (
            patch(f"{MODULE}.MailBox", self._mailbox_with_attachment()),
            patch.object(client, "_smtp_send", AsyncMock()),
        ):
            result = await client._forward_email_impl(
                "42", "erin@example.com", None, None, False, False
            )

        assert result["attachments_forwarded"] == 0
        assert result["attachment_names"] == []

    async def test_missing_message_raises(self, client: AppleEmailClient) -> None:
        with (
            patch(f"{MODULE}.MailBox", _FakeMailBox([])),
            patch.object(client, "_smtp_send", AsyncMock()),
            pytest.raises(ValueError, match="not found"),
        ):
            await client._forward_email_impl("999", "erin@example.com", None, None, False, True)


# ============================================================================
# TRASH & LABELS
# ============================================================================


class TestTrashEmail:
    """Trashing must locate the per-folder UID and drop the cached copy."""

    async def test_moves_message_to_trash_and_invalidates_cache(
        self, client: AppleEmailClient
    ) -> None:
        redis = _fake_redis()
        redis._store[f"apple_email:{client.user_id}:msg:42"] = json.dumps({"id": "42"})
        mailbox = _FakeMailBox([_mail_message(uid="42")])

        with (
            patch(f"{MODULE}.MailBox", mailbox),
            patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)),
        ):
            result = await client._trash_email_impl("42")

        assert result["labelIds"] == ["Trash"]
        assert mailbox.moved == [(("42",), "Trash")]
        assert f"apple_email:{client.user_id}:msg:42" not in redis._store

    async def test_message_absent_from_every_folder_raises(self, client: AppleEmailClient) -> None:
        redis = _fake_redis()

        with (
            patch(f"{MODULE}.MailBox", _FakeMailBox([])),
            patch(f"{MODULE}.get_redis_session", AsyncMock(return_value=redis)),
            pytest.raises(ValueError, match="not found"),
        ):
            await client._trash_email_impl("999")


class TestListLabels:
    """IMAP folders are exposed as the label mapping the tools consume."""

    async def test_returns_identity_mapping_of_folder_names(self, client: AppleEmailClient) -> None:
        mailbox = _FakeMailBox([])
        mailbox.folder.list = MagicMock(
            return_value=[SimpleNamespace(name="INBOX"), SimpleNamespace(name="Sent Messages")]
        )

        with patch(f"{MODULE}.MailBox", mailbox):
            labels = await client._list_labels_impl(use_cache=True)

        assert labels == {"INBOX": "INBOX", "Sent Messages": "Sent Messages"}
