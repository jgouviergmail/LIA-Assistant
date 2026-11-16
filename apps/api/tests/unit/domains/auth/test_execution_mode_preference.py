"""The execution-mode preference: three choices, and what « auto » does here (ADR-390)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.execution_mode_router import (
    get_execution_mode_preference,
    update_execution_mode_preference,
)
from src.domains.auth.schemas import ExecutionModePreferenceRequest
from src.domains.users.models import User

pytestmark = pytest.mark.unit

_RESOLUTION = "src.domains.auth.execution_mode_router.auto_resolution"


@pytest.mark.parametrize("mode", ["pipeline", "react", "auto"])
async def test_every_choice_is_kept_and_returned(mode: str) -> None:
    user = User(id=uuid4(), execution_mode="pipeline")
    db = MagicMock(spec=AsyncSession)
    db.scalar.return_value = user

    with patch(_RESOLUTION, AsyncMock(return_value="decided")):
        response = await update_execution_mode_preference(
            ExecutionModePreferenceRequest(execution_mode=mode), user, db
        )

    assert user.execution_mode == mode
    assert (response.execution_mode, response.auto_resolution) == (mode, "decided")
    db.commit.assert_awaited_once()


def test_an_unknown_choice_is_refused_at_the_boundary() -> None:
    with pytest.raises(PydanticValidationError):
        ExecutionModePreferenceRequest(execution_mode="loop")  # type: ignore[arg-type]


@pytest.mark.parametrize("resolution", ["decided", "always_react", "always_pipeline"])
async def test_reading_says_what_auto_does_on_this_instance(resolution: str) -> None:
    """The header and the settings show it: never a placebo choice."""
    user = User(id=uuid4(), execution_mode="auto")

    with patch(_RESOLUTION, AsyncMock(return_value=resolution)):
        response = await get_execution_mode_preference(user)

    assert (response.execution_mode, response.auto_resolution) == ("auto", resolution)


async def test_a_stored_value_no_choice_names_reads_as_the_default() -> None:
    user = User(id=uuid4(), execution_mode="garbage")

    with patch(_RESOLUTION, AsyncMock(return_value="decided")):
        response = await get_execution_mode_preference(user)

    assert response.execution_mode == "pipeline"
