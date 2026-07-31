"""Reading someone's calendar means reading the one THEY chose.

Defect reported 2026-07-30, after the peer routing and the data plumbing were
both fixed: the assistant answered that Jérôme G had no timed slot tomorrow,
while he had a 10:00 appointment. The read was hardcoded to ``primary`` /
``@default`` and ignored ``default_calendar_name`` — the preference every other
read path in the codebase honours (``briefing/fetchers.py``, ``calendar_tools``,
``tasks_tools``). A user whose real agenda lives in a named calendar was
therefore reported free while being busy: the most dangerous shape of wrong
answer, because it is actionable and confident.

The resolution belongs to the calendar's OWNER, never to the caller. These
helpers take the owner id explicitly for exactly that reason — the peer path
runs under the ASKING user's runtime, so anything reading "the current user"
would resolve the wrong person's preference and look correct in every
single-user test.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.preferences.owner_defaults import (
    resolve_owner_calendar_id,
    resolve_owner_task_list_id,
)

OWNER = uuid4()


def _connector(preferences_encrypted: str | None = "enc") -> MagicMock:
    connector = MagicMock()
    connector.preferences_encrypted = preferences_encrypted
    return connector


def _repo(connector: MagicMock | None) -> MagicMock:
    repo = MagicMock()
    repo.get_by_user_and_type = AsyncMock(return_value=connector)
    return repo


def _connector_type() -> MagicMock:
    connector_type = MagicMock()
    connector_type.value = "google_calendar"
    return connector_type


# Distinguishes "caller did not care" from "caller means there is NO connector"
# — conflating the two made this harness silently exercise the wrong branch.
_UNSET = object()


async def _resolve_calendar(
    *,
    connector: MagicMock | None | object = _UNSET,
    preference: str | None = "Famille",
    resolved: str = "cal_famille_id",
    resolver_side_effect: Exception | None = None,
):
    repo = _repo(_connector() if connector is _UNSET else connector)
    resolver = AsyncMock(return_value=resolved)
    if resolver_side_effect is not None:
        resolver.side_effect = resolver_side_effect

    with (
        patch(
            "src.domains.connectors.preferences.owner_defaults.ConnectorRepository",
            return_value=repo,
        ),
        patch(
            "src.domains.connectors.preferences.owner_defaults."
            "ConnectorPreferencesService.get_preference_value",
            return_value=preference,
        ),
        patch(
            "src.domains.connectors.preferences.owner_defaults.resolve_calendar_name",
            resolver,
        ),
    ):
        calendar_id = await resolve_owner_calendar_id(
            db=MagicMock(), client=MagicMock(), owner_id=OWNER, connector_type=_connector_type()
        )
    return calendar_id, repo, resolver


# =========================================================================
# The reported defect
# =========================================================================


@pytest.mark.asyncio
async def test_named_default_calendar_is_used_instead_of_primary():
    """THE defect: the 10:00 appointment lived in "Famille", not in primary."""
    calendar_id, _, _ = await _resolve_calendar()

    assert calendar_id == "cal_famille_id"


@pytest.mark.asyncio
async def test_preference_is_read_for_the_OWNER_not_the_caller():
    """A peer read runs under the ASKING user's runtime — the owner must win.

    Nothing else in a single-user test would catch this: both ids exist and
    both lookups succeed. Only the argument proves whose calendar was read.
    """
    _, repo, _ = await _resolve_calendar()

    assert repo.get_by_user_and_type.await_args.args[0] == OWNER


@pytest.mark.asyncio
async def test_named_default_task_list_is_used_instead_of_at_default():
    """Same defect, same fix, on the shared-tasks path."""
    repo = _repo(_connector())
    resolver = AsyncMock(return_value="list_perso_id")

    with (
        patch(
            "src.domains.connectors.preferences.owner_defaults.ConnectorRepository",
            return_value=repo,
        ),
        patch(
            "src.domains.connectors.preferences.owner_defaults."
            "ConnectorPreferencesService.get_preference_value",
            return_value="Perso",
        ),
        patch(
            "src.domains.connectors.preferences.owner_defaults.resolve_task_list_name",
            resolver,
        ),
    ):
        task_list_id = await resolve_owner_task_list_id(
            db=MagicMock(), client=MagicMock(), owner_id=OWNER, connector_type=_connector_type()
        )

    assert task_list_id == "list_perso_id"
    assert repo.get_by_user_and_type.await_args.args[0] == OWNER


# =========================================================================
# Degradation — a preference lookup must never cost the read
# =========================================================================


@pytest.mark.asyncio
async def test_no_connector_falls_back_to_primary():
    calendar_id, _, resolver = await _resolve_calendar(connector=None)

    assert calendar_id == "primary"
    resolver.assert_not_awaited()


@pytest.mark.asyncio
async def test_connector_without_preferences_falls_back_to_primary():
    calendar_id, _, resolver = await _resolve_calendar(connector=_connector(None))

    assert calendar_id == "primary"
    resolver.assert_not_awaited()


@pytest.mark.asyncio
async def test_unset_preference_falls_back_to_primary():
    """Most users never name a calendar — that path must stay free."""
    calendar_id, _, resolver = await _resolve_calendar(preference=None)

    assert calendar_id == "primary"
    resolver.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolution_failure_falls_back_instead_of_raising():
    """A broken preference must degrade to `primary`, never lose the answer."""
    calendar_id, _, _ = await _resolve_calendar(resolver_side_effect=ValueError("boom"))

    assert calendar_id == "primary"


@pytest.mark.asyncio
async def test_an_infrastructure_failure_propagates_rather_than_reading_the_wrong_calendar():
    """A database failure must NOT be dressed up as "the user has no preference".

    Falling back would serve `primary` while looking successful — answering
    confidently from the WRONG calendar, which is the defect this module
    exists to close. Losing the operation loudly is the better trade, so the
    caught set is narrow on purpose and everything else escapes.
    """
    repo = MagicMock()
    repo.get_by_user_and_type = AsyncMock(side_effect=RuntimeError("pool exhausted"))

    with (
        patch(
            "src.domains.connectors.preferences.owner_defaults.ConnectorRepository",
            return_value=repo,
        ),
        pytest.raises(RuntimeError),
    ):
        await resolve_owner_calendar_id(
            db=MagicMock(), client=MagicMock(), owner_id=OWNER, connector_type=_connector_type()
        )


@pytest.mark.parametrize("boom", [ValueError, KeyError, AttributeError, TypeError])
@pytest.mark.asyncio
async def test_every_preference_shaped_failure_is_absorbed(boom):
    """The four shapes a malformed preference takes, exactly as the ten call
    sites this helper replaces already handled them — no behaviour change."""
    calendar_id, _, _ = await _resolve_calendar(resolver_side_effect=boom("bad"))

    assert calendar_id == "primary"
