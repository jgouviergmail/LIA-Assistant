"""Native source scope is coroutine-local, balanced and absent from legacy work."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    SourceWorkerLease,
    current_source_worker,
    require_source_worker,
    source_worker_scope,
)

pytestmark = pytest.mark.unit


async def test_no_native_scope_opens_no_authority_transaction():
    db = AsyncMock()
    await require_source_worker(db)
    db.scalar.assert_not_awaited()


def test_different_nested_source_cannot_replace_the_owned_scope():
    scope = SourceWorkerLease(
        kind="drive",
        source_id=uuid4(),
        space_id=uuid4(),
        actor_id=uuid4(),
        worker_id="native-owned",
    )
    other = SourceWorkerLease(
        kind="mail",
        source_id=uuid4(),
        space_id=scope.space_id,
        actor_id=scope.actor_id,
        worker_id="native-other",
    )
    with source_worker_scope(scope):
        with pytest.raises(SourceLeaseLost):
            with source_worker_scope(other):
                pytest.fail("A different nested scope was admitted")
        assert current_source_worker() == scope
    assert current_source_worker() is None
