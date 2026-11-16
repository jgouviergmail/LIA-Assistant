"""What LIA sends to an ntfy server (ADR-391): a topic, words, a link — nothing else.

ntfy delivers to every app subscribed to a TOPIC, and the topic is the only secret: whoever
knows it reads what is published to it. So LIA draws the topics it owns from a strong random
source, refuses what ntfy itself would refuse before any request, and sends a person's words
only when the person chose to (minimal content by default, owner decision 2026-11-16) — and
never more than the push shows for a notification kept in LIA.
"""

from __future__ import annotations

import re

import pytest

from src.core.constants import (
    NTFY_MESSAGE_MAX_BYTES,
    NTFY_TITLE_MAX_BYTES,
    NTFY_TOPIC_PREFIX,
    NTFY_TOPIC_RANDOM_CHARS,
)
from src.core.notification_privacy import NotificationPrivacy, notification_preview
from src.domains.notifications.ntfy import (
    NtfyContent,
    new_topic,
    publication,
    server_url_refusal,
    subscribe_link,
    token_refusal,
    topic_refusal,
)
from src.domains.notifications.ntfy_errors import (
    SERVER_URL_INVALID,
    SERVER_URL_NOT_HTTPS,
    SERVER_URL_REFUSED,
    TOKEN_INVALID,
    TOPIC_INVALID,
)

pytestmark = pytest.mark.unit

CLICK = "https://lia.example.org/dashboard/chat"


class TestTopics:
    def test_a_topic_lia_draws_carries_its_prefix_and_an_unguessable_suffix(self) -> None:
        drawn = {new_topic() for _ in range(50)}

        assert len(drawn) == 50
        for topic in drawn:
            assert re.fullmatch(
                rf"{re.escape(NTFY_TOPIC_PREFIX)}[A-Za-z0-9]{{{NTFY_TOPIC_RANDOM_CHARS}}}", topic
            )
            assert topic_refusal(topic) is None

    @pytest.mark.parametrize("topic", ["alerts", "lia_X-y_9", "a" * 64])
    def test_a_topic_ntfy_accepts_is_accepted(self, topic: str) -> None:
        assert topic_refusal(topic) is None

    @pytest.mark.parametrize("topic", ["", "a" * 65, "with space", "accentué", "a/b", "a?b"])
    def test_a_topic_ntfy_refuses_is_refused_before_any_request(self, topic: str) -> None:
        assert topic_refusal(topic) == TOPIC_INVALID


class TestTokens:
    def test_an_access_token_in_ntfy_s_shape_is_accepted(self) -> None:
        assert token_refusal("tk_" + "a1B2c3" * 4 + "d4E5f") is None

    @pytest.mark.parametrize(
        "token",
        ["", "tk_short", "tk_" + "a" * 30, "xx_" + "a" * 29, "tk_" + "a" * 28 + "!", "Bearer tk_x"],
    )
    def test_anything_else_is_refused(self, token: str) -> None:
        assert token_refusal(token) == TOKEN_INVALID


class TestCustomServers:
    @pytest.mark.parametrize(
        "url", ["https://ntfy.sh", "https://ntfy.example.org/", "https://example.org/ntfy"]
    )
    def test_a_public_https_server_is_accepted(self, url: str) -> None:
        assert server_url_refusal(url) is None

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "ntfy.sh",
            "http://ntfy.sh",
            "ftp://ntfy.sh",
            "https://user:secret@ntfy.sh",
            "https://ntfy.sh/?topic=x",
            "https://ntfy.sh/#x",
            "https://127.0.0.1",
            "https://10.0.0.5",
            "https://localhost",
        ],
    )
    def test_anything_else_is_refused_before_any_request(self, url: str) -> None:
        """A person's server is reached on the public network, over TLS, with no
        credential in its address: the operator's own server is the only private one."""
        assert server_url_refusal(url) in {
            SERVER_URL_NOT_HTTPS,
            SERVER_URL_INVALID,
            SERVER_URL_REFUSED,
        }

    @pytest.mark.parametrize(
        "url",
        [
            "https://[::1",
            "https://ntfy.sh:99999",
            "https://ntfy.sh:0",
            "https://ntfy.sh:port",
            "https://exa mple.org",
            "https://ntfy.sh\n.evil.test",
        ],
    )
    def test_an_address_no_url_can_be_read_from_is_refused_not_raised(self, url: str) -> None:
        """What a person types is refused with a code the form shows, never a server error."""
        assert server_url_refusal(url) == SERVER_URL_INVALID


class TestPublication:
    def test_full_content_carries_the_words_and_the_link(self) -> None:
        sent = publication(
            topic="lia_t",
            title="Rappel",
            body="Appeler Marie avant 18 h",
            click=CLICK,
            content=NtfyContent.FULL,
            language="fr",
            privacy=NotificationPrivacy.NORMAL,
        )

        assert sent == {
            "topic": "lia_t",
            "title": "Rappel",
            "message": "Appeler Marie avant 18 h",
            "click": CLICK,
        }

    @pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
    def test_minimal_content_says_only_that_lia_has_something(self, language: str) -> None:
        sent = publication(
            topic="lia_t",
            title="Rappel",
            body="Appeler Marie avant 18 h",
            click=CLICK,
            content=NtfyContent.MINIMAL,
            language=language,
            privacy=NotificationPrivacy.NORMAL,
        )

        title, notice = notification_preview(
            NotificationPrivacy.IN_APP_SENSITIVE, language, "Rappel", "Appeler Marie"
        )
        assert (sent["title"], sent["message"]) == (title, notice)
        assert "Marie" not in sent["title"] + sent["message"]
        assert sent["click"] == CLICK

    def test_a_notification_kept_in_lia_never_leaves_with_its_words(self) -> None:
        """Full content never shows more than the push does (``notification_preview``)."""
        sent = publication(
            topic="lia_t",
            title="Point personnel",
            body="Ce que tu m'as confié",
            click=CLICK,
            content=NtfyContent.FULL,
            language="fr",
            privacy=NotificationPrivacy.IN_APP_SENSITIVE,
        )

        assert "confié" not in sent["message"]

    def test_long_words_are_cut_on_a_character_within_ntfy_s_limits(self) -> None:
        sent = publication(
            topic="lia_t",
            title="Été " * 600,
            body="é" * (NTFY_MESSAGE_MAX_BYTES * 2),
            click=CLICK,
            content=NtfyContent.FULL,
            language="fr",
            privacy=NotificationPrivacy.NORMAL,
        )

        assert len(sent["message"].encode("utf-8")) <= NTFY_MESSAGE_MAX_BYTES
        assert len(sent["title"].encode("utf-8")) <= NTFY_TITLE_MAX_BYTES
        assert sent["message"].endswith("…") and sent["title"].endswith("…")
        assert "�" not in sent["message"] + sent["title"]

    @pytest.mark.parametrize("letter", ["m", "é", "漢", "🌞"])
    def test_a_message_stays_a_message_on_a_real_server(self, letter: str) -> None:
        """Measured on ntfy 2.37.2: a message of 4 096 bytes or more becomes an attachment —
        refused when attachments are off, a file instead of words when they are on; 4 095 bytes
        pass. A title is refused past 1 024 bytes. Every width of character lands under both."""
        sent = publication(
            topic="lia_t",
            title=letter * 2000,
            body=letter * 5000,
            click=CLICK,
            content=NtfyContent.FULL,
            language="fr",
            privacy=NotificationPrivacy.NORMAL,
        )

        assert len(sent["message"].encode("utf-8")) < 4096
        assert len(sent["title"].encode("utf-8")) <= 1024

    def test_a_notification_with_no_body_never_reads_triggered(self) -> None:
        """ntfy writes « triggered » for an empty message: the title stands in."""
        sent = publication(
            topic="lia_t",
            title="Nouvelle connexion",
            body="   ",
            click=CLICK,
            content=NtfyContent.FULL,
            language="fr",
            privacy=NotificationPrivacy.NORMAL,
        )

        assert sent["message"] == "Nouvelle connexion"


class TestTheLinkThatSubscribesTheApp:
    @pytest.mark.parametrize(
        ("server", "link"),
        [
            ("https://ntfy.sh", "ntfy://ntfy.sh/lia_t?display=LIA"),
            ("https://ntfy.sh/", "ntfy://ntfy.sh/lia_t?display=LIA"),
            ("https://ntfy.example.org:8443", "ntfy://ntfy.example.org:8443/lia_t?display=LIA"),
            # A LAN install answers in clear: the app must not try TLS.
            ("http://192.168.1.10:8090", "ntfy://192.168.1.10:8090/lia_t?display=LIA&secure=false"),
            # An IPv6 host keeps the brackets that separate it from its port.
            ("http://[fd00::50]:2586", "ntfy://[fd00::50]:2586/lia_t?display=LIA&secure=false"),
        ],
    )
    def test_a_server_at_its_root_gets_the_link_the_app_opens(self, server: str, link: str) -> None:
        assert subscribe_link(server, "lia_t") == link

    @pytest.mark.parametrize("server", ["https://example.org/ntfy", "", "ntfy.sh", "ftp://x.org"])
    def test_a_server_the_link_cannot_name_gets_none(self, server: str) -> None:
        """The app reads « ntfy://host/topic » alone: a server under a path is subscribed by hand."""
        assert subscribe_link(server, "lia_t") is None
