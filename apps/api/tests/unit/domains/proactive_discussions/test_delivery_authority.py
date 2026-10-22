"""A queued opening cannot trigger external reads or survive provider selection changes."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.read_budget import ReadCallLimit
from src.domains.proactive_discussions.context_store.preparation import proof_of
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.infrastructure.proactive import discussion_delivery_authority as module
from tests.unit.domains.proactive_discussions.test_context_loop import FACT

pytestmark = pytest.mark.unit


def test_delivery_cannot_open_even_a_single_provider_request():
    owner = uuid4()
    with pytest.raises(ReadCallLimit):
        module.NoExternalCalls(owner=owner, limit=1).claim(owner)


@pytest.mark.asyncio
async def test_changed_selected_provider_refuses_cached_connector_evidence(monkeypatch):
    now = datetime.now(UTC)
    fact = FACT.model_copy(
        update={"observed_at": now, "source_account": "google_calendar:fictional:scope:container"}
    )
    proof = proof_of(fact, {fact.reference: fact}, now=now)

    @asynccontextmanager
    async def context():
        yield object()

    monkeypatch.setattr(module, "get_db_context", context)
    monkeypatch.setattr(
        module.DiscussionRepository,
        "get_policy",
        AsyncMock(return_value=DiscussionPolicy(enabled=True, sources=(fact.source,))),
    )
    monkeypatch.setattr(module, "is_selected_discussion_connector", AsyncMock(return_value=False))
    scope = AsyncMock(side_effect=AssertionError("retired provider scope must not be opened"))
    monkeypatch.setattr(module, "read_connector_scope", scope)
    assert not await module.delivery_sources_permitted(
        uuid4(), uuid4(), [proof.model_dump(mode="json")]
    )
    scope.assert_not_awaited()
