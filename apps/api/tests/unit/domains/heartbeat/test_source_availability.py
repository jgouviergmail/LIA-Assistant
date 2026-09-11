"""Every source the panel can switch has an availability probe — 13 of 13.

The probe used to know eight sources; the frontend computed
« unavailable = every source − the connected ones », so Habitudes, Workboard,
Engagements, Anniversaires and Heure de départ read « Non connecté » on every
account — measured 2026-09-11 on an account with an active learned profile.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.heartbeat import source_availability
from src.domains.heartbeat.source_availability import (
    SOURCE_AVAILABILITY_PROBES,
    assert_availability_probes_complete,
    compute_available_sources,
)
from src.domains.heartbeat.source_policy import HEARTBEAT_SOURCE_KEYS

pytestmark = pytest.mark.unit

_MODULE = "src.domains.heartbeat.source_availability"


class TestCompleteness:
    def test_every_published_source_has_a_probe_and_nothing_else(self) -> None:
        assert set(SOURCE_AVAILABILITY_PROBES) == set(HEARTBEAT_SOURCE_KEYS)
        assert_availability_probes_complete()

    def test_the_assert_refuses_a_missing_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        trimmed = dict(SOURCE_AVAILABILITY_PROBES)
        trimmed.pop("habits")
        monkeypatch.setattr(source_availability, "SOURCE_AVAILABILITY_PROBES", trimmed)
        with pytest.raises(RuntimeError, match="habits"):
            assert_availability_probes_complete()

    def test_the_assert_refuses_a_probe_for_no_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        extended = dict(SOURCE_AVAILABILITY_PROBES)
        extended["ghost"] = SOURCE_AVAILABILITY_PROBES["habits"]
        monkeypatch.setattr(source_availability, "SOURCE_AVAILABILITY_PROBES", extended)
        with pytest.raises(RuntimeError, match="ghost"):
            assert_availability_probes_complete()


def _user(**overrides: Any) -> Any:
    base = {
        "id": uuid.uuid4(),
        "interests_enabled": False,
        "memory_enabled": False,
        "journals_enabled": False,
        "health_metrics_agents_enabled": False,
        "habits_enabled": True,
        "home_location_encrypted": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _settings(**overrides: Any) -> Any:
    base = {
        "journals_enabled": False,
        "health_metrics_enabled": False,
        "habits_enabled": True,
        "open_loops_enabled": True,
        "workboard_enabled": True,
        "heartbeat_departure_enabled": True,
        "google_api_key": "k",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _no_connectors() -> Any:
    repo = MagicMock()
    repo.get_by_user_and_type = AsyncMock(return_value=None)
    return repo


class TestTheFiveSourcesThatWereNeverAvailable:
    async def test_a_learned_profile_makes_habits_available(self) -> None:
        with (
            patch(f"{_MODULE}.ConnectorRepository", return_value=_no_connectors()),
            patch(f"{_MODULE}.settings", _settings()),
            patch(f"{_MODULE}._has_habit_profile", AsyncMock(return_value=True)),
        ):
            available = await compute_available_sources(_user(), MagicMock())
        assert "habits" in available

    async def test_habits_needs_the_switch_and_a_profile(self) -> None:
        with (
            patch(f"{_MODULE}.ConnectorRepository", return_value=_no_connectors()),
            patch(f"{_MODULE}.settings", _settings()),
            patch(f"{_MODULE}._has_habit_profile", AsyncMock(return_value=False)),
        ):
            assert "habits" not in await compute_available_sources(_user(), MagicMock())
        with (
            patch(f"{_MODULE}.ConnectorRepository", return_value=_no_connectors()),
            patch(f"{_MODULE}.settings", _settings()),
            patch(f"{_MODULE}._has_habit_profile", AsyncMock(return_value=True)),
        ):
            assert "habits" not in await compute_available_sources(
                _user(habits_enabled=False), MagicMock()
            )

    async def test_workboard_and_open_loops_follow_their_deployment_flags(self) -> None:
        with (
            patch(f"{_MODULE}.ConnectorRepository", return_value=_no_connectors()),
            patch(f"{_MODULE}.settings", _settings()),
            patch(f"{_MODULE}._has_habit_profile", AsyncMock(return_value=False)),
        ):
            available = await compute_available_sources(_user(), MagicMock())
        assert {"workboard", "open_loops"} <= set(available)
        with (
            patch(f"{_MODULE}.ConnectorRepository", return_value=_no_connectors()),
            patch(
                f"{_MODULE}.settings", _settings(workboard_enabled=False, open_loops_enabled=False)
            ),
            patch(f"{_MODULE}._has_habit_profile", AsyncMock(return_value=False)),
        ):
            available = await compute_available_sources(_user(), MagicMock())
        assert not {"workboard", "open_loops"} & set(available)

    async def test_birthdays_needs_the_contacts_connector(self) -> None:
        from src.domains.connectors.models import ConnectorType

        repo = MagicMock()

        async def _get(user_id: Any, ct: Any) -> Any:
            if ct == ConnectorType.GOOGLE_CONTACTS:
                return SimpleNamespace(status=SimpleNamespace(value="active"))
            return None

        repo.get_by_user_and_type = _get
        with (
            patch(f"{_MODULE}.ConnectorRepository", return_value=repo),
            patch(f"{_MODULE}.settings", _settings()),
            patch(f"{_MODULE}._has_habit_profile", AsyncMock(return_value=False)),
        ):
            available = await compute_available_sources(_user(), MagicMock())
        assert "birthdays" in available and "calendar" not in available

    async def test_departure_needs_the_flag_the_key_and_a_calendar(self) -> None:
        from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES

        calendar_type = next(iter(CONNECTOR_FUNCTIONAL_CATEGORIES["calendar"]))
        repo = MagicMock()

        async def _get(user_id: Any, ct: Any) -> Any:
            if ct == calendar_type:
                return SimpleNamespace(status=SimpleNamespace(value="active"))
            return None

        repo.get_by_user_and_type = _get
        with (
            patch(f"{_MODULE}.ConnectorRepository", return_value=repo),
            patch(f"{_MODULE}.settings", _settings()),
            patch(f"{_MODULE}._has_habit_profile", AsyncMock(return_value=False)),
        ):
            available = await compute_available_sources(_user(), MagicMock())
        assert {"calendar", "departure"} <= set(available)
        with (
            patch(f"{_MODULE}.ConnectorRepository", return_value=repo),
            patch(f"{_MODULE}.settings", _settings(google_api_key="")),
            patch(f"{_MODULE}._has_habit_profile", AsyncMock(return_value=False)),
        ):
            assert "departure" not in await compute_available_sources(_user(), MagicMock())

    async def test_the_order_is_the_published_display_order(self) -> None:
        from src.domains.heartbeat.source_policy import HEARTBEAT_SOURCE_ORDER

        with (
            patch(f"{_MODULE}.ConnectorRepository", return_value=_no_connectors()),
            patch(f"{_MODULE}.settings", _settings(journals_enabled=True)),
            patch(f"{_MODULE}._has_habit_profile", AsyncMock(return_value=True)),
        ):
            available = await compute_available_sources(
                _user(memory_enabled=True, journals_enabled=True), MagicMock()
            )
        assert available == [s for s in HEARTBEAT_SOURCE_ORDER if s in available]
