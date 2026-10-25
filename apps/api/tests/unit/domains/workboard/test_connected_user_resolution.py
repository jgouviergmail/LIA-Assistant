"""« Give this ticket to Marie » — the holder a name designates among connections.

What must hold:
- the full name, and a first name designating ONE connection, resolve to
  that account (the chat's path is a draft the person confirms, holder named);
- a name several connections carry is refused as ambiguous, never guessed;
- a name matching nobody connected is « not connected ».
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import ValidationError
from src.domains.workboard.constants import WorkboardError
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.unit

OWNER = uuid4()
MARIE = uuid4()
MARIE_LIN = uuid4()
PAUL = uuid4()


def _service(*people: tuple[object, str]) -> WorkboardService:
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=list(people))))
    return WorkboardService(db)


def _connections(*peer_ids: object):
    return patch(
        "src.domains.peers.repository.PeersRepository",
        return_value=SimpleNamespace(
            list_accepted_for_user=AsyncMock(
                return_value=[
                    SimpleNamespace(user_a_id=OWNER, user_b_id=peer_id) for peer_id in peer_ids
                ]
            )
        ),
    )


@pytest.fixture(autouse=True)
def _peers_on():
    with patch.object(WorkboardService, "_peers_enabled", staticmethod(lambda: True)):
        yield


async def test_a_full_name_resolves() -> None:
    service = _service((MARIE, "Marie Dupont"), (PAUL, "Paul Martin"))
    with _connections(MARIE, PAUL):
        assert await service.resolve_connected_user_id(OWNER, "marie dupont") == MARIE


async def test_a_first_name_designating_one_connection_resolves() -> None:
    service = _service((MARIE, "Marie Dupont"), (PAUL, "Paul Martin"))
    with _connections(MARIE, PAUL):
        assert await service.resolve_connected_user_id(OWNER, "Paul") == PAUL


async def test_a_first_name_two_connections_carry_is_ambiguous() -> None:
    service = _service((MARIE, "Marie Dupont"), (MARIE_LIN, "Marie Lin"))
    with _connections(MARIE, MARIE_LIN), pytest.raises(ValidationError) as refused:
        await service.resolve_connected_user_id(OWNER, "Marie")
    assert WorkboardError.AMBIGUOUS_REFERENCE.value in str(refused.value.detail)


async def test_a_name_matching_nobody_connected_is_not_connected() -> None:
    service = _service((MARIE, "Marie Dupont"))
    with _connections(MARIE), pytest.raises(ValidationError) as refused:
        await service.resolve_connected_user_id(OWNER, "Zoé")
    assert WorkboardError.ASSIGNEE_NOT_CONNECTED.value in str(refused.value.detail)
