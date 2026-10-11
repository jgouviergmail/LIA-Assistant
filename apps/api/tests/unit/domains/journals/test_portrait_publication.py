"""Omitted synthesis is not completion; zero-effect maintenance keeps approved prose."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.journals.consolidation_lifecycle import ConsolidationSnapshot
from src.domains.journals.consolidation_output import MaintenanceAction, MaintenanceOutput
from src.domains.journals.consolidation_settlement import _publish_portrait
from src.domains.journals.portrait_sources import PortraitSourceBundle

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def _publish(*, pending=False, current=True, actions=None, claims=None, applied_count=0):
    stamp = datetime.now(UTC)
    source_state = {"_rendering": {"portrait_policy": "synthetic-current"}}
    snapshot = ConsolidationSnapshot(uuid4(), 8, 3, stamp, source_state)
    previous = {
        "journal_revision": 8,
        "source_state": source_state,
        "portrait_pending": pending,
        "claims": ["synthetic existing accepted claim"],
    }
    user = SimpleNamespace(
        id=uuid4(),
        journal_portrait_full=None if pending else "Existing approved natural prose.",
        journal_portrait_brief=None if pending else "Existing approved natural prose.",
        journal_portrait_compiled_at=None if pending else stamp,
        journal_portrait_sources=previous,
    )
    output = MaintenanceOutput(actions=actions or [], portrait_claims=claims, valid=True)
    service = SimpleNamespace(get_all_active=AsyncMock(return_value=[]))
    await _publish_portrait(
        user,
        service,
        output,
        PortraitSourceBundle({}, {}),
        snapshot,
        8,
        current,
        previous,
        None,
        applied_count,
    )
    return user, previous, service


async def test_omitted_compilation_does_not_consume_existing_pending_synthesis():
    user, _, service = await _publish(pending=True)
    assert user.journal_portrait_sources["portrait_pending"] is True
    service.get_all_active.assert_not_awaited()


async def test_zero_effect_update_preserves_current_approved_portrait():
    action = MaintenanceAction(
        action="update", entry_id=str(uuid4()), title="Already current title"
    )
    user, previous, service = await _publish(actions=[action])
    assert user.journal_portrait_full == "Existing approved natural prose."
    assert user.journal_portrait_brief == "Existing approved natural prose."
    assert user.journal_portrait_compiled_at is not None
    assert user.journal_portrait_sources == previous
    service.get_all_active.assert_not_awaited()


async def test_omitted_compilation_keeps_policy_or_source_refresh_pending():
    user, _, service = await _publish(current=False)
    assert user.journal_portrait_full is None and user.journal_portrait_brief is None
    assert user.journal_portrait_compiled_at is None
    assert user.journal_portrait_sources["portrait_pending"] is True
    service.get_all_active.assert_not_awaited()


@pytest.mark.parametrize("applied_count", [0, 1])
async def test_explicit_empty_compilation_consumes_follow_up_only_without_new_mutation(
    applied_count,
):
    user, _, service = await _publish(pending=True, claims=[], applied_count=applied_count)
    assert user.journal_portrait_sources["portrait_pending"] is bool(applied_count)
    assert user.journal_portrait_full is None and user.journal_portrait_brief is None
    assert user.journal_portrait_compiled_at is not None
    assert user.journal_portrait_sources["claims"] == []
    service.get_all_active.assert_awaited_once_with(user.id)
