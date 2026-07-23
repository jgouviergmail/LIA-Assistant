"""Unit tests for device sessions (security program D2, Lot 4).

Covers bounded client metadata extraction (A3), session payload v4
round-trips, the fleet operations (list / revoke-by-display-id /
revoke-others), coarse last-seen touching, the A4 attestation resolver,
and the notification decision matrix.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.client_metadata import (
    UNKNOWN_FAMILY,
    extract_client_meta,
    parse_user_agent,
    truncate_ip,
)
from src.domains.auth.login_notification import (
    notify_new_login_if_unknown,
    resolve_attestation,
)
from src.infrastructure.cache.session_store import SessionStore, UserSession
from src.infrastructure.database.registry import import_all_models

import_all_models()


@pytest.mark.unit
class TestClientMetadata:
    """A3-bounded extraction: families + truncated IPs only."""

    @pytest.mark.parametrize(
        ("user_agent", "browser", "os_family"),
        [
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                "chrome",
                "windows",
            ),
            (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/604.1",
                "safari",
                "ios",
            ),
            (
                "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
                "firefox",
                "linux",
            ),
            (
                "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/126.0 "
                "Safari/537.36 Edg/126.0",
                "edge",
                "windows",
            ),
            (None, UNKNOWN_FAMILY, UNKNOWN_FAMILY),
            ("weird-bot/1.0", UNKNOWN_FAMILY, UNKNOWN_FAMILY),
        ],
    )
    def test_parse_user_agent(self, user_agent: str | None, browser: str, os_family: str) -> None:
        """Coarse families, unknown fallback — never the raw UA."""
        assert parse_user_agent(user_agent) == (browser, os_family)

    def test_truncate_ipv4(self) -> None:
        """IPv4 keeps the /24 only."""
        assert truncate_ip("192.168.1.42") == "192.168.1.x"

    def test_truncate_ipv6(self) -> None:
        """IPv6 keeps the first three hextets only."""
        assert truncate_ip("2001:db8:85a3::8a2e:370:7334").startswith("2001:0db8:85a3:")

    def test_truncate_invalid(self) -> None:
        """Garbage input collapses to unknown, never stored raw."""
        assert truncate_ip("not-an-ip") == UNKNOWN_FAMILY
        assert truncate_ip(None) == UNKNOWN_FAMILY

    def test_extract_bundles_meta(self) -> None:
        """The extraction chokepoint returns only the bounded triple."""
        meta = extract_client_meta("Mozilla/5.0 (Windows) Chrome/126", "10.0.0.7")
        assert (meta.ua_family, meta.os_family, meta.ip_trunc) == (
            "chrome",
            "windows",
            "10.0.0.x",
        )


@pytest.mark.unit
class TestSessionPayloadV4:
    """v4 fields round-trip; legacy payloads default; display id is opaque."""

    def test_roundtrip_preserves_v4_fields(self) -> None:
        """to_dict → from_dict keeps device metadata + attestation id."""
        session = UserSession(
            session_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            ua_family="chrome",
            os_family="windows",
            ip_trunc="10.0.0.x",
            last_seen_at=datetime.now(UTC),
            fcm_token_id="tok-row-1",
        )
        restored = UserSession.from_dict(session.session_id, session.to_dict())
        assert restored.ua_family == "chrome"
        assert restored.ip_trunc == "10.0.0.x"
        assert restored.last_seen_at == session.last_seen_at
        assert restored.fcm_token_id == "tok-row-1"

    def test_legacy_payload_defaults(self) -> None:
        """Pre-v4 payloads validate with None metadata (unknown device)."""
        restored = UserSession.from_dict(
            "sid",
            {
                "user_id": str(uuid.uuid4()),
                "remember_me": False,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        assert restored.ua_family is None
        assert restored.last_seen_at is None
        assert restored.fcm_token_id is None

    def test_display_id_is_not_the_session_id(self) -> None:
        """The UI identifier must never expose the raw cookie value."""
        session = UserSession(session_id="secret-session", user_id="u")
        assert session.display_id != "secret-session"
        assert len(session.display_id) == 16
        assert "secret" not in session.display_id


def _stored_session(user_id: str, **over: object) -> UserSession:
    defaults: dict[str, object] = {
        "session_id": str(uuid.uuid4()),
        "user_id": user_id,
        "auth_methods": ["password"],
    }
    defaults.update(over)
    return UserSession(**defaults)  # type: ignore[arg-type]


def _fleet_redis(sessions: list[UserSession]) -> AsyncMock:
    """Redis mock backing SMEMBERS + pipelined GET + delete."""
    payloads = {s.session_id: json.dumps(s.to_dict()) for s in sessions}
    redis = AsyncMock()
    redis.smembers = AsyncMock(return_value=set(payloads.keys()))

    pipeline = MagicMock()
    pipeline_keys: list[str] = []
    pipeline.get = MagicMock(side_effect=lambda key: pipeline_keys.append(key.split(":", 1)[1]))
    pipeline.delete = MagicMock()
    pipeline.execute = AsyncMock(side_effect=lambda: [payloads.get(k) for k in pipeline_keys])
    redis.pipeline = MagicMock(return_value=pipeline)
    redis.get = AsyncMock(side_effect=lambda key: payloads.get(key.split(":", 1)[1]))
    redis.delete = AsyncMock(return_value=1)
    redis.srem = AsyncMock()
    redis.set = AsyncMock()
    return redis


@pytest.mark.unit
class TestFleetOperations:
    """list / revoke-by-display-id / revoke-others / coarse touch."""

    async def test_list_returns_sessions_newest_first(self) -> None:
        """Live sessions come back parsed and sorted."""
        user_id = str(uuid.uuid4())
        older = _stored_session(user_id, created_at=datetime.now(UTC) - timedelta(hours=2))
        newer = _stored_session(user_id, created_at=datetime.now(UTC))
        store = SessionStore(_fleet_redis([older, newer]))

        sessions = await store.list_user_sessions(user_id)

        assert [s.session_id for s in sessions] == [newer.session_id, older.session_id]

    async def test_delete_by_display_id_targets_the_right_session(self) -> None:
        """Revocation by opaque id deletes exactly the matching session."""
        user_id = str(uuid.uuid4())
        target = _stored_session(user_id)
        other = _stored_session(user_id)
        redis = _fleet_redis([target, other])
        store = SessionStore(redis)

        deleted = await store.delete_session_by_display_id(user_id, target.display_id)

        assert deleted is True
        redis.delete.assert_any_await(f"session:{target.session_id}")

    async def test_delete_by_unknown_display_id_is_false(self) -> None:
        """An unknown display id deletes nothing."""
        user_id = str(uuid.uuid4())
        store = SessionStore(_fleet_redis([_stored_session(user_id)]))

        assert await store.delete_session_by_display_id(user_id, "ffffffffffffffff") is False

    async def test_revoke_others_keeps_current(self) -> None:
        """Revoke-others deletes everything except the caller's session."""
        user_id = str(uuid.uuid4())
        current = _stored_session(user_id)
        other_a = _stored_session(user_id)
        other_b = _stored_session(user_id)
        redis = _fleet_redis([current, other_a, other_b])
        store = SessionStore(redis)

        revoked = await store.delete_other_user_sessions(user_id, current.session_id)

        assert revoked == 2
        deleted_keys = {call.args[0] for call in redis.delete.await_args_list}
        assert f"session:{current.session_id}" not in deleted_keys

    async def test_touch_last_seen_is_coarse(self) -> None:
        """A recent last_seen_at is NOT rewritten (bounded write load)."""
        session = _stored_session(str(uuid.uuid4()), last_seen_at=datetime.now(UTC))
        redis = _fleet_redis([session])
        store = SessionStore(redis)

        await store.touch_last_seen(session.session_id)

        redis.set.assert_not_awaited()

    async def test_touch_last_seen_refreshes_stale(self) -> None:
        """A stale last_seen_at is rewritten with keepttl."""
        session = _stored_session(
            str(uuid.uuid4()),
            last_seen_at=datetime.now(UTC) - timedelta(hours=1),
        )
        redis = _fleet_redis([session])
        store = SessionStore(redis)

        await store.touch_last_seen(session.session_id)

        assert redis.set.await_args.kwargs["keepttl"] is True


@pytest.mark.unit
class TestAttestation:
    """A4: FCM-token attestation + notification decision matrix."""

    async def test_no_token_is_unknown(self) -> None:
        """Absent token → unknown device (fail toward notifying)."""
        known, token_id = await resolve_attestation(AsyncMock(), uuid.uuid4(), None)
        assert (known, token_id) == (False, None)

    async def test_foreign_or_inactive_token_is_unknown(self) -> None:
        """A token not registered to this account attests nothing."""
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        known, token_id = await resolve_attestation(db, uuid.uuid4(), "some-token")
        assert (known, token_id) == (False, None)

    async def test_registered_token_attests(self) -> None:
        """A valid active token of the account attests the device."""
        row = MagicMock()
        row.id = uuid.uuid4()
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = row
        db.execute = AsyncMock(return_value=result)

        known, token_id = await resolve_attestation(db, uuid.uuid4(), "tok")
        assert known is True
        assert token_id == str(row.id)

    async def test_known_device_skips_notification(self) -> None:
        """Attested device → no push."""
        user = MagicMock()
        user.login_notifications_enabled = True
        with patch("src.domains.auth.login_notification.FCMNotificationService") as service_cls:
            await notify_new_login_if_unknown(AsyncMock(), user, known=True)
        service_cls.assert_not_called()

    async def test_pref_disabled_skips_notification(self) -> None:
        """Opt-out honored."""
        user = MagicMock()
        user.login_notifications_enabled = False
        with patch("src.domains.auth.login_notification.FCMNotificationService") as service_cls:
            await notify_new_login_if_unknown(AsyncMock(), user, known=False)
        service_cls.assert_not_called()

    async def test_unknown_device_notifies(self) -> None:
        """Unknown device + pref on → localized push to all devices."""
        user = MagicMock()
        user.id = uuid.uuid4()
        user.login_notifications_enabled = True
        user.language = "fr"

        service = MagicMock()
        service.send_to_user = AsyncMock(return_value=MagicMock(success_count=2, failure_count=0))
        with patch(
            "src.domains.auth.login_notification.FCMNotificationService",
            return_value=service,
        ):
            await notify_new_login_if_unknown(AsyncMock(), user, known=False)

        service.send_to_user.assert_awaited_once()
        assert service.send_to_user.await_args.kwargs["user_id"] == user.id

    async def test_push_failure_never_raises(self) -> None:
        """FCM down → login still succeeds (best-effort)."""
        user = MagicMock()
        user.id = uuid.uuid4()
        user.login_notifications_enabled = True
        user.language = "fr"

        with patch(
            "src.domains.auth.login_notification.FCMNotificationService",
            side_effect=Exception("FCM down"),
        ):
            await notify_new_login_if_unknown(AsyncMock(), user, known=False)
