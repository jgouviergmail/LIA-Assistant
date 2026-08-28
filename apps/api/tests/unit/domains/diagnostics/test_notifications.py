"""Admin incident notifications — superusers only, cooldown-guarded, i18n ×6.

The cooldown is an atomic ``SET NX EX`` (never SET NX + separate EXPIRE —
distributed-primitive rule), keyed by correlation key so a flapping alert
cannot storm the admins' phones.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.i18n_diagnostics import get_incident_notification
from src.domains.diagnostics import notifications as notif_module


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

    async def fake_superusers(db: Any) -> list[Any]:
        return [admin]

    class _Dispatcher:
        def __init__(self, **_: Any) -> None: ...

        async def dispatch(self, **kwargs: Any) -> Any:
            state["dispatched"].append(kwargs)
            return MagicMock(success=True)

    class _Repo:
        def __init__(self, db: Any) -> None: ...

        async def mark_notified(self, incident_id: Any) -> None:
            state["marked"].append(incident_id)

    monkeypatch.setattr(notif_module, "get_redis_cache", fake_get_redis)
    monkeypatch.setattr(notif_module, "_active_superusers", fake_superusers)
    monkeypatch.setattr(notif_module, "NotificationDispatcher", _Dispatcher)
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
            db=MagicMock(),
        )
        assert sent == 1
        kwargs = wired["dispatched"][0]
        expected_title, expected_body = get_incident_notification(
            "fr", severity="critical", title="Redis is down"
        )
        assert kwargs["title"] == expected_title
        assert kwargs["content"] == expected_body
        assert kwargs["target_id"] == str(incident_id)
        assert wired["marked"] == [incident_id]

    async def test_cooldown_active_skips_everything(self, wired: dict[str, Any]) -> None:
        wired["redis"].set = AsyncMock(return_value=None)  # NX not acquired
        sent = await notif_module.notify_admins_of_incident(
            incident_id=uuid4(),
            correlation_key="RedisDown",
            severity="critical",
            title="t",
            db=MagicMock(),
        )
        assert sent == 0
        assert wired["dispatched"] == []

    async def test_cooldown_key_is_atomic_nx_with_ttl(self, wired: dict[str, Any]) -> None:
        await notif_module.notify_admins_of_incident(
            incident_id=uuid4(),
            correlation_key="RedisDown",
            severity="critical",
            title="t",
            db=MagicMock(),
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
            db=MagicMock(),
        )
        assert sent == 1


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
