"""Admin incident notifications — superusers only, cooldown-guarded, i18n ×6.

The cooldown is an atomic ``SET NX EX`` (never SET NX + separate EXPIRE —
distributed-primitive rule), keyed by correlation key so a flapping alert
cannot storm the admins' phones.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
import structlog

from src.core.i18n_diagnostics import get_incident_notification
from src.domains.diagnostics import notifications as notif_module
from tests.helpers.notifications import (
    ScriptedChannels,
    ScriptedDispatcher,
    scripted_dispatcher,
    sse_only,
)


def _session() -> SimpleNamespace:
    """The caller's session as the real dispatcher uses it: it commits the archive."""
    return SimpleNamespace(commit=AsyncMock())


class _UnreachableAdmin(ScriptedDispatcher):
    """One admin's archive keeps nothing; every other admin's channels answer as scripted."""

    def __init__(self, unreachable: UUID, channels: ScriptedChannels, **flags: bool) -> None:
        super().__init__(channels, **flags)
        self.unreachable = unreachable

    async def _archive_message(
        self, user: Any, content: str, metadata: Mapping[str, object], db: object
    ) -> dict[str, object]:
        if user.id == self.unreachable:
            return {"archived": False, "conversation_id": None, "message_id": None}
        return await super()._archive_message(user, content, metadata, db)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"dispatched": [], "marked": []}

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)  # NX acquired
    state["redis"] = redis

    async def fake_get_redis() -> Any:
        return redis

    admin = MagicMock()
    admin.id = uuid4()
    admin.language = "fr"
    state["admins"] = [admin]

    async def fake_superusers(db: Any) -> list[Any]:
        return list(state["admins"])

    # The REAL dispatcher over scripted channels (audit AC-003): an admin counts
    # as notified on what a dispatch actually answers, never on a stub's word.
    channels = ScriptedChannels()
    state["channels"] = channels
    state["dispatched"] = channels.sent

    class _Repo:
        def __init__(self, db: Any) -> None: ...

        async def mark_notified(self, incident_id: Any) -> None:
            state["marked"].append(incident_id)

    # Each admin's dispatch runs on a session of its own (recorded here).
    sessions: list[SimpleNamespace] = []
    state["sessions"] = sessions

    @asynccontextmanager
    async def fake_db_context() -> AsyncIterator[SimpleNamespace]:
        session = _session()
        sessions.append(session)
        yield session

    monkeypatch.setattr(notif_module, "get_db_context", fake_db_context)
    monkeypatch.setattr(notif_module, "get_redis_cache", fake_get_redis)
    monkeypatch.setattr(notif_module, "_active_superusers", fake_superusers)
    monkeypatch.setattr(notif_module, "NotificationDispatcher", scripted_dispatcher(channels))
    monkeypatch.setattr(notif_module, "DiagnosticsRepository", _Repo)
    state["admin"] = admin
    return state


@pytest.mark.unit
class TestNotifyAdmins:
    async def test_nominal_notifies_each_superuser_in_their_language(
        self, wired: dict[str, Any]
    ) -> None:
        incident_id = uuid4()
        sent = await notif_module.notify_admins_of_incident(
            incident_id=incident_id,
            correlation_key="RedisDown",
            severity="critical",
            title="Redis is down",
            db=_session(),
        )
        assert sent == 1
        (dispatched,) = wired["dispatched"]
        expected_title, expected_body = get_incident_notification(
            "fr", severity="critical", title="Redis is down"
        )
        assert dispatched.title == expected_title
        assert dispatched.content == expected_body
        assert dispatched.target_id == str(incident_id)
        assert wired["marked"] == [incident_id]

    async def test_cooldown_active_skips_everything(self, wired: dict[str, Any]) -> None:
        wired["redis"].set = AsyncMock(return_value=None)  # NX not acquired
        sent = await notif_module.notify_admins_of_incident(
            incident_id=uuid4(),
            correlation_key="RedisDown",
            severity="critical",
            title="t",
            db=_session(),
        )
        assert sent == 0
        assert wired["dispatched"] == []

    async def test_cooldown_key_is_atomic_nx_with_ttl(self, wired: dict[str, Any]) -> None:
        await notif_module.notify_admins_of_incident(
            incident_id=uuid4(),
            correlation_key="RedisDown",
            severity="critical",
            title="t",
            db=_session(),
        )
        _, kwargs = wired["redis"].set.await_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") is not None

    async def test_redis_down_still_notifies_fail_open(self, wired: dict[str, Any]) -> None:
        """Losing the cooldown store must not silence critical notifications."""
        wired["redis"].set = AsyncMock(side_effect=ConnectionError("redis down"))
        sent = await notif_module.notify_admins_of_incident(
            incident_id=uuid4(),
            correlation_key="RedisDown",
            severity="critical",
            title="t",
            db=_session(),
        )
        assert sent == 1

    async def test_each_admin_is_notified_on_a_session_of_its_own(
        self, wired: dict[str, Any]
    ) -> None:
        """One admin's archive failing in the database aborts the transaction it ran
        on: shared, that was every later admin's and the caller's (25P02, measured
        on PostgreSQL) — « one admin's broken channel must not starve the others »."""
        wired["admins"].append(MagicMock(id=uuid4(), language="en"))
        caller = _session()

        sent = await notif_module.notify_admins_of_incident(
            incident_id=uuid4(),
            correlation_key="RedisDown",
            severity="critical",
            title="t",
            db=caller,
        )

        assert sent == 2
        caller.commit.assert_not_awaited()  # the caller's transaction stays the caller's
        assert len(wired["sessions"]) == 2
        assert all(session.commit.await_count == 1 for session in wired["sessions"])

    async def test_an_admin_nothing_durable_reached_is_not_counted(
        self, wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An SSE event alone reached an open tab or nobody: no ``notified_at`` (AC-003)."""
        channels = sse_only()
        monkeypatch.setattr(notif_module, "NotificationDispatcher", scripted_dispatcher(channels))

        with structlog.testing.capture_logs() as captured:
            sent = await notif_module.notify_admins_of_incident(
                incident_id=uuid4(),
                correlation_key="RedisDown",
                severity="critical",
                title="t",
                db=_session(),
            )

        assert sent == 0
        assert wired["marked"] == []
        assert len(channels.sent) == 1  # it was attempted, and reached nobody durably
        (event,) = [e for e in captured if e["event"] == "diagnostics_notify_not_delivered"]
        assert event["log_level"] == "warning"
        assert "exc_info" not in event  # an expected outcome, not a crash

    async def test_one_unreachable_admin_never_hides_the_one_who_was_told(
        self, wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        unreachable = MagicMock(id=uuid4(), language="de")
        wired["admins"].append(unreachable)
        channels = ScriptedChannels()
        monkeypatch.setattr(
            notif_module,
            "NotificationDispatcher",
            lambda **flags: _UnreachableAdmin(unreachable.id, channels, **flags),
        )
        incident_id = uuid4()

        sent = await notif_module.notify_admins_of_incident(
            incident_id=incident_id,
            correlation_key="RedisDown",
            severity="critical",
            title="t",
            db=_session(),
        )

        assert sent == 1
        assert wired["marked"] == [incident_id]
        assert [n.user_id for n in channels.sent] == [wired["admin"].id, unreachable.id]


@pytest.mark.unit
class TestI18nCoverage:
    def test_all_six_backend_languages_have_both_strings(self) -> None:
        from src.core.i18n_diagnostics import INCIDENT_NOTIFICATION_STRINGS

        assert set(INCIDENT_NOTIFICATION_STRINGS) == {"en", "fr", "de", "es", "it", "zh-CN"}
        for language, entries in INCIDENT_NOTIFICATION_STRINGS.items():
            assert entries["title"], language
            assert "{title}" in entries["body"], language

    def test_variant_codes_route_through_the_chokepoint(self) -> None:
        title_zh, _ = get_incident_notification("zh", severity="critical", title="x")
        title_zh_cn, _ = get_incident_notification("zh-CN", severity="critical", title="x")
        assert title_zh == title_zh_cn
        title_fr_fr, _ = get_incident_notification("fr-FR", severity="critical", title="x")
        title_fr, _ = get_incident_notification("fr", severity="critical", title="x")
        assert title_fr_fr == title_fr
