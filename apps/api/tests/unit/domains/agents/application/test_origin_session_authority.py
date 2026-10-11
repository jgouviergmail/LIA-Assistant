"""Transport-only session facts are live authority, never a remembered approval."""

import dataclasses
from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError
from src.domains.agents.context.runtime_context_builder import build_runtime_context

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("fault", ["missing", "foreign_owner", "different_session"])
async def test_session_binding_rechecks_current_owner_and_original_transport(fault: str) -> None:
    module = import_module("src.core.application_origin")
    actor = uuid4()
    facts = module.ApplicationSessionFacts(
        user_id=uuid4() if fault == "foreign_owner" else actor,
        binding_id="b" * 64 if fault == "different_session" else "a" * 64,
        display_id="a" * 12,
        step_up_at=datetime.now(UTC),
    )
    lookup = AsyncMock(return_value=None if fault == "missing" else facts)
    origin = module.ApplicationOrigin(user_id=actor, binding_id="a" * 64, read_current=lookup)
    with pytest.raises(AuthorizationError):
        await origin.require_session(actor, expected_binding="a" * 64)
    lookup.assert_awaited_once()


@pytest.mark.parametrize("age", [None, -1, 301, "naive"])
async def test_step_up_requires_current_aware_nonfuture_proof(age: int | str | None) -> None:
    module = import_module("src.core.application_origin")
    actor, now = uuid4(), datetime.now(UTC)
    timestamp = (
        None
        if age is None
        else now.replace(tzinfo=None) if age == "naive" else now - timedelta(seconds=age)
    )
    facts = module.ApplicationSessionFacts(
        user_id=actor, binding_id="a" * 64, display_id="a" * 12, step_up_at=timestamp
    )
    origin = module.ApplicationOrigin(
        user_id=actor, binding_id="a" * 64, read_current=AsyncMock(return_value=facts)
    )
    with pytest.raises(AuthorizationError):
        await origin.require_session(
            actor, expected_binding="a" * 64, recent_step_up=True, now=now, window_seconds=300
        )


async def test_authority_is_reloaded_and_revocation_wins_after_a_valid_call() -> None:
    module = import_module("src.core.application_origin")
    actor, now = uuid4(), datetime.now(UTC)
    facts = module.ApplicationSessionFacts(
        user_id=actor, binding_id="a" * 64, display_id="a" * 12, step_up_at=now
    )
    lookup = AsyncMock(side_effect=[facts, None])
    origin = module.ApplicationOrigin(user_id=actor, binding_id="a" * 64, read_current=lookup)
    assert (
        await origin.require_session(
            actor, expected_binding="a" * 64, recent_step_up=True, now=now, window_seconds=300
        )
        == facts
    )
    with pytest.raises(AuthorizationError):
        await origin.require_session(actor, expected_binding="a" * 64)
    assert lookup.await_count == 2


@pytest.mark.parametrize("fault", ["foreign_actor", "different_binding"])
async def test_wrong_actor_or_command_binding_never_reads_a_session(fault: str) -> None:
    module = import_module("src.core.application_origin")
    actor = uuid4()
    lookup = AsyncMock()
    origin = module.ApplicationOrigin(user_id=actor, binding_id="a" * 64, read_current=lookup)
    with pytest.raises(AuthorizationError):
        await origin.require_session(
            uuid4() if fault == "foreign_actor" else actor,
            expected_binding="b" * 64 if fault == "different_binding" else "a" * 64,
        )
    lookup.assert_not_awaited()


@pytest.mark.parametrize("automated", [False, True])
def test_builder_injects_the_live_origin_only_on_human_runs(automated: bool) -> None:
    module = import_module("src.core.application_origin")
    actor = uuid4()
    origin = module.ApplicationOrigin(user_id=actor, binding_id="a" * 64, read_current=AsyncMock())
    context = build_runtime_context(
        state={"messages": []},
        user_id=actor,
        conversation_id=uuid4(),
        application_origin=origin,
        is_automated_source=automated,
    )
    assert context.application_origin is (None if automated else origin)
    assert "read_current" not in repr(context) and "binding_id" not in repr(context)
    with pytest.raises(dataclasses.FrozenInstanceError):
        origin.binding_id = "b" * 64
