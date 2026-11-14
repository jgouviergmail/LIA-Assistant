"""The shared mutation door hands a move down WHOLE (ADR-276).

``apply_ticket_mutation`` is what both the assistant's preview and its
confirmed execution run. A field of the move it forgot to pass would be
previewed, approved and then silently not applied — the confirmation card
saying one thing and the board doing another.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.workboard.mutation_preview import apply_ticket_mutation
from src.domains.workboard.schemas import MoveRequest, TicketUpdate

pytestmark = pytest.mark.unit


async def _moved_with(move: MoveRequest) -> dict[str, object]:
    """Run one mutation and report what the service's move was asked."""
    with patch("src.domains.workboard.mutation_preview.WorkboardService") as service_cls:
        service = service_cls.return_value
        service.update = AsyncMock()
        service.move = AsyncMock()
        await apply_ticket_mutation(
            AsyncMock(), AsyncMock(), uuid.uuid4(), TicketUpdate(), move=move, notices=[]
        )
        return dict(service.move.await_args.kwargs)


async def test_a_drop_in_another_lane_reaches_the_service_with_its_lane() -> None:
    lane = uuid.uuid4()
    asked = await _moved_with(MoveRequest(status="done", position=0, category_id=lane))
    assert asked == {"category_id": lane, "clear_category": False}


async def test_a_drop_in_the_unfiled_lane_reaches_the_service_as_a_clear() -> None:
    asked = await _moved_with(MoveRequest(status="done", position=0, clear_category=True))
    assert asked == {"category_id": None, "clear_category": True}
