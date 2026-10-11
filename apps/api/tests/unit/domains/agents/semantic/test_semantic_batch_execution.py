"""A semantic plan must produce usable batch parameters, not reference literals."""

from copy import deepcopy

import pytest
from pydantic import BaseModel

from src.domains.agents.orchestration.condition_evaluator import ReferenceResolver

pytestmark = pytest.mark.unit


class Recipient(BaseModel):
    email: str
    notes: str


class BatchPayload(BaseModel):
    recipients: list[Recipient]
    matrix: list[list[str]]


def test_contact_results_feed_nested_batch_payload_without_mutating_the_plan() -> None:
    source: dict[str, dict[str, object]] = {
        "lookup": {"contacts": [{"email": "ada@example.test"}, {"email": "grace@example.test"}]}
    }
    authored: dict[str, object] = {
        "recipients": [
            {"email": "$steps.lookup.contacts[0].email", "notes": "N/A"},
            {
                "email": "$steps.lookup.contacts[1].email",
                "notes": "inviter $steps.lookup.contacts[1].email",
            },
        ],
        "matrix": [["$steps.lookup.contacts[0].email"], ["$steps.lookup.contacts[1].email"]],
    }
    original = deepcopy(authored)
    resolved = ReferenceResolver().resolve_args(authored, source)
    payload = BatchPayload.model_validate(resolved)
    assert [recipient.email for recipient in payload.recipients] == [
        "ada@example.test",
        "grace@example.test",
    ]
    assert payload.recipients[0].notes == "N/A"
    assert "grace@example.test" in payload.recipients[1].notes
    assert "$steps" not in payload.recipients[1].notes
    assert payload.matrix == [["ada@example.test"], ["grace@example.test"]]
    assert authored == original


def test_missing_nested_source_fails_before_a_batch_can_be_sent() -> None:
    with pytest.raises(ValueError):
        ReferenceResolver().resolve_args(
            {"recipients": [{"email": "$steps.missing.contacts[0].email"}]}, {}
        )


def test_resolved_external_data_is_not_reinterpreted_as_another_reference() -> None:
    source: dict[str, dict[str, object]] = {
        "lookup": {"body": {"note": "$steps.private.secret"}},
        "private": {"secret": "do not expand external content"},
    }
    resolved = ReferenceResolver().resolve_args({"payload": "$steps.lookup.body"}, source)
    assert resolved == {"payload": {"note": "$steps.private.secret"}}
