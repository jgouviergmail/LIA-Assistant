"""Native call history requests cannot invent an owner or an unbounded read."""

from importlib import import_module

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": True},
        {"limit": 51},
        {"limit": 0},
        {"cursor": "raw-credential"},
        {"user_id": "someone"},
    ],
)
def test_history_read_refuses_unbounded_or_foreign_context(payload: dict[str, object]) -> None:
    module = import_module("src.domains.telephony.history_schemas")
    with pytest.raises(ValidationError):
        module.PhoneHistoryRead.model_validate(payload)


def test_history_projection_does_not_label_observed_runs_as_complete_invoice() -> None:
    module = import_module("src.domains.telephony.history_schemas")
    result = module.PhoneHistoryProjection(calls=[], total=0)
    assert result.usage_scope == "recorded_platform_runs"
    assert result.next_cursor is None
