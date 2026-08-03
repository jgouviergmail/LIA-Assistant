"""The per-source switches, over HTTP.

Two contracts matter here and they are distinct:

- **availability** (``available_sources``) — what this account is connected to;
- **permission** (``disabled_sources``) — what the reader refuses to be
  interrupted from.

A source can be available and refused, or unavailable and permitted. Conflating
them is the defect this feature removes, so the payload carries both, plus the
vocabulary itself (``all_sources``) — a bound the backend enforces must be
readable by whoever produces the value (ADR-184).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.domains.heartbeat.router import get_heartbeat_settings, update_heartbeat_settings
from src.domains.heartbeat.schemas import HeartbeatSettingsUpdate
from src.domains.heartbeat.source_policy import HEARTBEAT_SOURCE_ORDER

pytestmark = pytest.mark.unit


def _user(disabled: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        language="fr",
        heartbeat_enabled=True,
        heartbeat_min_per_day=1,
        heartbeat_max_per_day=4,
        heartbeat_push_enabled=True,
        heartbeat_notify_start_hour=8,
        heartbeat_notify_end_hour=22,
        heartbeat_disabled_sources=disabled,
    )


def _patch_availability() -> object:
    return patch(
        "src.domains.heartbeat.router._compute_available_sources",
        new=AsyncMock(return_value=["calendar", "emails"]),
    )


class TestReading:
    async def test_publishes_the_whole_vocabulary_and_the_refusals(self) -> None:
        with _patch_availability():
            response = await get_heartbeat_settings(user=_user(["emails"]), db=AsyncMock())

        # The vocabulary is published so the UI never re-declares it.
        assert response.all_sources == list(HEARTBEAT_SOURCE_ORDER)
        assert response.disabled_sources == ["emails"]

    async def test_an_untouched_account_refuses_nothing(self) -> None:
        with _patch_availability():
            response = await get_heartbeat_settings(user=_user(None), db=AsyncMock())

        assert response.disabled_sources == []

    async def test_availability_and_permission_stay_separate(self) -> None:
        """`emails` is connected AND refused — both facts must survive."""
        with _patch_availability():
            response = await get_heartbeat_settings(user=_user(["emails"]), db=AsyncMock())

        assert "emails" in response.available_sources
        assert "emails" in response.disabled_sources


class TestWriting:
    async def test_stores_the_canonical_refusal_list(self) -> None:
        user = _user(None)
        db = AsyncMock()

        with _patch_availability():
            response = await update_heartbeat_settings(
                data=HeartbeatSettingsUpdate(heartbeat_disabled_sources=["weather", "weather"]),
                user=user,
                db=db,
            )

        # De-duplicated and sorted: two equivalent requests, one row state.
        assert user.heartbeat_disabled_sources == ["weather"]
        assert response.disabled_sources == ["weather"]
        db.commit.assert_awaited()

    async def test_re_enabling_everything_is_an_empty_list_not_null(self) -> None:
        """Distinguishes "I turned them all back on" from "never asked"."""
        user = _user(["emails", "weather"])

        with _patch_availability():
            await update_heartbeat_settings(
                data=HeartbeatSettingsUpdate(heartbeat_disabled_sources=[]),
                user=user,
                db=AsyncMock(),
            )

        assert user.heartbeat_disabled_sources == []

    async def test_an_unknown_source_is_refused_with_422_and_stored_nowhere(self) -> None:
        """A typo must never become a preference nobody can see or undo."""
        user = _user(None)
        db = AsyncMock()

        with _patch_availability(), pytest.raises(HTTPException) as excinfo:
            await update_heartbeat_settings(
                data=HeartbeatSettingsUpdate(heartbeat_disabled_sources=["emials"]),
                user=user,
                db=db,
            )

        assert excinfo.value.status_code == 422
        assert user.heartbeat_disabled_sources is None
        db.commit.assert_not_awaited()

    async def test_leaving_the_field_out_does_not_clear_the_refusals(self) -> None:
        """PATCH is partial: an unrelated update must not silently re-enable."""
        user = _user(["journals"])

        with _patch_availability():
            await update_heartbeat_settings(
                data=HeartbeatSettingsUpdate(heartbeat_enabled=False),
                user=user,
                db=AsyncMock(),
            )

        assert user.heartbeat_disabled_sources == ["journals"]


class TestDependencyPublication:
    """The panel cannot warn about a constraint it was never told (ADR-184)."""

    async def test_the_settings_response_publishes_the_dependency(self) -> None:
        with _patch_availability():
            response = await get_heartbeat_settings(user=_user(), db=AsyncMock())

        assert response.source_dependencies == {"departure": ["calendar"]}

    async def test_the_published_dependency_names_only_toggleable_sources(self) -> None:
        # A requirement pointing at something absent from `all_sources` could
        # not be satisfied from this panel — the reader would be told to enable
        # a switch that is not there.
        with _patch_availability():
            response = await get_heartbeat_settings(user=_user(), db=AsyncMock())

        toggleable = set(response.all_sources)
        for source, requires in response.source_dependencies.items():
            assert source in toggleable, source
            assert set(requires) <= toggleable, requires
