"""Google push notification parsing (lot H, 2026-08).

Phase 1 channels notify with ``X-Goog-*`` headers and an empty body; phase 2
(Gmail) notifies through a Pub/Sub push envelope with a base64 JSON payload.
Both parsers are defensive: a malformed notification degrades to ``None``
(ignored), never a crash — the webhook endpoint answers 200 regardless.
"""

from __future__ import annotations

import base64
import json

import pytest

from src.domains.push_channels.notifications import (
    ChannelNotification,
    GmailPushEvent,
    parse_channel_headers,
    parse_pubsub_body,
)

pytestmark = pytest.mark.unit


class TestChannelHeaders:
    def test_full_headers_parse(self) -> None:
        notif = parse_channel_headers(
            {
                "x-goog-channel-id": "chan-123",
                "x-goog-channel-token": "secret-token",
                "x-goog-resource-id": "res-9",
                "x-goog-resource-state": "exists",
                "x-goog-message-number": "42",
            }
        )
        assert notif == ChannelNotification(
            channel_id="chan-123",
            token="secret-token",
            resource_id="res-9",
            resource_state="exists",
            message_number=42,
        )

    def test_header_names_are_case_insensitive(self) -> None:
        notif = parse_channel_headers(
            {
                "X-Goog-Channel-ID": "chan-123",
                "X-Goog-Channel-Token": "tok",
                "X-Goog-Resource-ID": "res",
                "X-Goog-Resource-State": "sync",
                "X-Goog-Message-Number": "1",
            }
        )
        assert notif is not None
        assert notif.resource_state == "sync"

    def test_missing_channel_id_is_ignored(self) -> None:
        assert parse_channel_headers({"x-goog-resource-state": "exists"}) is None

    def test_missing_token_defaults_to_empty_string(self) -> None:
        # A channel notification without a token still resolves (the service
        # rejects it against the stored secret — empty never matches).
        notif = parse_channel_headers(
            {
                "x-goog-channel-id": "chan-123",
                "x-goog-resource-id": "res",
                "x-goog-resource-state": "exists",
            }
        )
        assert notif is not None
        assert notif.token == ""

    def test_non_numeric_message_number_degrades_to_zero(self) -> None:
        notif = parse_channel_headers(
            {
                "x-goog-channel-id": "chan-123",
                "x-goog-resource-id": "res",
                "x-goog-resource-state": "exists",
                "x-goog-message-number": "abc",
            }
        )
        assert notif is not None
        assert notif.message_number == 0


class TestPubSubBody:
    @staticmethod
    def _envelope(payload: dict) -> dict:
        data = base64.b64encode(json.dumps(payload).encode()).decode()
        return {"message": {"data": data, "messageId": "m1"}, "subscription": "s"}

    def test_valid_envelope_parses(self) -> None:
        body = self._envelope({"emailAddress": "user@gmail.com", "historyId": 12345})
        event = parse_pubsub_body(body)
        assert event == GmailPushEvent(email_address="user@gmail.com", history_id=12345)

    def test_history_id_as_string_is_coerced(self) -> None:
        body = self._envelope({"emailAddress": "user@gmail.com", "historyId": "678"})
        event = parse_pubsub_body(body)
        assert event is not None
        assert event.history_id == 678

    def test_malformed_base64_is_ignored(self) -> None:
        assert parse_pubsub_body({"message": {"data": "!!!not-b64!!!"}}) is None

    def test_missing_message_is_ignored(self) -> None:
        assert parse_pubsub_body({"subscription": "s"}) is None

    def test_missing_email_is_ignored(self) -> None:
        assert parse_pubsub_body(self._envelope({"historyId": 5})) is None
