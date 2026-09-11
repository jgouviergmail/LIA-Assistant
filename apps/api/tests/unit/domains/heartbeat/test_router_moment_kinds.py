"""The per-kind switches, over HTTP (ADR-281, lot 2).

Same three contracts as the source switches beside them, and they are distinct:

- **the vocabulary** (``all_moment_kinds``) — published so the panel never
  re-declares a list it does not enforce;
- **the refusal** (``moment_kinds_disabled``) — what the person turns off;
- **the requirements** (``moment_kind_dependencies``) — what a kind needs to
  produce anything, so the panel can say « requires Calendar » instead of
  offering a live control that yields nothing (ADR-184).

They ride on the heartbeat settings route on purpose: a second router for three
fields would be a second authority on the same panel.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.heartbeat.router import get_heartbeat_settings, update_heartbeat_settings
from src.domains.heartbeat.schemas import HeartbeatSettingsUpdate
from src.domains.moments.models import MomentKind
from src.domains.moments.preferences import MOMENT_KIND_ORDER

pytestmark = pytest.mark.unit

FOLLOWUP = MomentKind.EVENT_FOLLOWUP.value


def _user(kinds_disabled: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        language="fr",
        heartbeat_enabled=True,
        heartbeat_min_per_day=1,
        heartbeat_max_per_day=4,
        heartbeat_push_enabled=True,
        heartbeat_notify_start_hour=8,
        heartbeat_notify_end_hour=22,
        heartbeat_disabled_sources=None,
        moment_kinds_disabled=kinds_disabled,
    )


def _patch_availability(sources: list[str] | None = None) -> object:
    return patch(
        "src.domains.heartbeat.router.compute_available_sources",
        new=AsyncMock(return_value=sources if sources is not None else ["calendar", "emails"]),
    )


class TestReading:
    async def test_the_vocabulary_is_published_not_re_declared(self) -> None:
        with _patch_availability():
            response = await get_heartbeat_settings(user=_user(), db=AsyncMock())

        assert response.all_moment_kinds == list(MOMENT_KIND_ORDER)

    async def test_an_untouched_account_refuses_nothing(self) -> None:
        with _patch_availability():
            response = await get_heartbeat_settings(user=_user(None), db=AsyncMock())

        assert response.moment_kinds_disabled == []

    async def test_a_refusal_is_published(self) -> None:
        with _patch_availability():
            response = await get_heartbeat_settings(user=_user([FOLLOWUP]), db=AsyncMock())

        assert response.moment_kinds_disabled == [FOLLOWUP]

    async def test_a_kind_with_its_requirement_met_says_nothing(self) -> None:
        with _patch_availability(["calendar"]):
            response = await get_heartbeat_settings(user=_user(), db=AsyncMock())

        assert response.moment_kind_dependencies == {}

    async def test_a_kind_without_its_connector_says_what_it_waits_for(self) -> None:
        """Otherwise the panel offers a switch that can never produce anything."""
        with _patch_availability([]):
            response = await get_heartbeat_settings(user=_user(), db=AsyncMock())

        assert response.moment_kind_dependencies == {FOLLOWUP: ["calendar"]}


class TestWriting:
    async def test_the_refusal_set_is_replaced_in_full(self) -> None:
        """A partial diff would make two clients disagree about the set."""
        user = _user([FOLLOWUP])
        db = AsyncMock()

        with _patch_availability():
            response = await update_heartbeat_settings(
                data=HeartbeatSettingsUpdate(moment_kinds_disabled=[]),
                user=user,
                db=db,
            )

        assert response.moment_kinds_disabled == []
        assert user.moment_kinds_disabled == []

    async def test_a_kind_nobody_declared_is_dropped_rather_than_stored(self) -> None:
        """A renamed vocabulary must not block a save, nor silence a kind that
        no switch could ever lift again."""
        user = _user()

        with _patch_availability():
            await update_heartbeat_settings(
                data=HeartbeatSettingsUpdate(moment_kinds_disabled=["ghost_kind", FOLLOWUP]),
                user=user,
                db=AsyncMock(),
            )

        assert user.moment_kinds_disabled == [FOLLOWUP]

    async def test_not_sending_the_field_leaves_it_alone(self) -> None:
        """A partial update must not read « absent » as « refuses nothing »."""
        user = _user([FOLLOWUP])

        with _patch_availability():
            await update_heartbeat_settings(
                data=HeartbeatSettingsUpdate(heartbeat_min_per_day=2),
                user=user,
                db=AsyncMock(),
            )

        assert user.moment_kinds_disabled == [FOLLOWUP]
