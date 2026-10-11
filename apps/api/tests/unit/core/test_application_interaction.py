"""A bounded pending interaction is neither completed work nor a returned failure."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def pending() -> dict[str, object]:
    return {
        "success": False,
        "phase": "waiting",
        "committed": False,
        "interaction": {
            "interaction_id": str(uuid4()),
            "kind": "secure",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        },
    }


@pytest.mark.parametrize("shape", ["mapping", "object"])
def test_valid_pending_result_is_explicitly_incomplete(shape: str) -> None:
    module = import_module("src.core.application_interaction")
    value = pending()
    result = value if shape == "mapping" else SimpleNamespace(**value)
    assert module.pending_interaction_of(result) is not None
    from src.core.tool_outcome import explicit_success

    assert not explicit_success(result)


@pytest.mark.parametrize(
    "change",
    [
        {"success": True},
        {"success": None},
        {"phase": "claimed"},
        {"interaction": None},
        {"committed": "false"},
        {"committed": True},
        {"error_code": "EXECUTION_FAILED"},
        {"no_op": True},
        {"interaction": {"interaction_id": "secret", "kind": "secure", "expires_at": "tomorrow"}},
        {
            "interaction": {
                "interaction_id": str(uuid4()),
                "kind": "invented",
                "expires_at": "2026-10-08T10:00:00Z",
            }
        },
        {
            "interaction": {
                "interaction_id": str(uuid4()),
                "kind": "secure",
                "expires_at": "2026-10-08T10:00:00",
            }
        },
    ],
)
def test_malformed_or_completed_result_cannot_become_waiting(change: dict[str, object]) -> None:
    module = import_module("src.core.application_interaction")
    assert module.pending_interaction_of({**pending(), **change}) is None


def test_an_unreadable_property_cannot_break_a_returned_operation() -> None:
    module = import_module("src.core.application_interaction")

    class Broken:
        @property
        def success(self) -> bool:
            raise RuntimeError("unreadable result")

    assert module.pending_interaction_of(Broken()) is None


def test_copied_model_cannot_bypass_interaction_validation() -> None:
    module = import_module("src.core.application_interaction")
    result = pending()
    valid = module.PendingApplicationInteraction.model_validate(result["interaction"])
    result["interaction"] = valid.model_copy(update={"kind": "invented"})
    assert module.pending_interaction_of(result) is None


def test_stored_pending_fact_remains_parseable_after_its_deadline() -> None:
    module = import_module("src.core.application_interaction")
    value = pending()
    value["interaction"] = {
        "interaction_id": str(uuid4()),
        "kind": "device",
        "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    # Expiry is command state, not a reason to rewrite an immutable notarized receipt.
    assert module.pending_interaction_of(value) is not None


def test_device_ack_can_wait_after_a_server_commit_without_claiming_client_completion() -> None:
    module = import_module("src.core.application_interaction")
    value = pending()
    value["committed"] = True
    value["interaction"] = {
        "interaction_id": str(uuid4()),
        "kind": "device",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
    }
    assert module.pending_interaction_of(value) is not None
