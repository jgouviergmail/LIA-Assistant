"""Explicit browser targets carry an inseparable, strictly typed revision."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.api.schemas import ChatRequest

pytestmark = pytest.mark.unit


def payload() -> dict[str, object]:
    """The legacy request has no selected target and still means Main."""
    return {"message": "Hello", "user_id": str(uuid4()), "session_id": "browser-session"}


def test_explicit_selection_is_preserved_for_the_run_entry_point() -> None:
    identity = uuid4()
    request = ChatRequest.model_validate(
        {**payload(), "conversation_id": str(identity), "conversation_revision": 7}
    )
    assert getattr(request, "conversation_id", None) == identity
    assert getattr(request, "conversation_revision", None) == 7


@pytest.mark.parametrize(
    "selection",
    [
        {"conversation_id": str(uuid4())},
        {"conversation_revision": 0},
        {"conversation_id": str(uuid4()), "conversation_revision": -1},
        {"conversation_id": str(uuid4()), "conversation_revision": True},
        {"conversation_id": str(uuid4()), "conversation_revision": "2"},
        {"conversation_id": str(uuid4()), "conversation_revision": 1.5},
    ],
)
def test_incomplete_or_coerced_selection_is_refused(selection: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({**payload(), **selection})


def test_absent_selection_retains_legacy_primary_semantics() -> None:
    request = ChatRequest.model_validate(payload())
    assert getattr(request, "conversation_id", None) is None
    assert getattr(request, "conversation_revision", None) is None
