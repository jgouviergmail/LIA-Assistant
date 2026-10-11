"""Approved content is canonical, bounded, versioned and checkpoint-safe."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import uuid4

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def content() -> dict[str, object]:
    return {
        "command_id": str(uuid4()),
        "actor_id": str(uuid4()),
        "operation_id": "preferences.update",
        "schema_version": 1,
        "schema_fingerprint": "a" * 64,
        "expected_digest": "b" * 64,
        "intent": {"font_size": 17},
        "before": {"font_size": 16},
        "after": {"font_size": 17},
        "title": "Application preferences",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
    }


def test_native_content_survives_json_checkpoint_round_trip() -> None:
    model = import_module(
        "src.domains.agents.application.draft_models"
    ).ApplicationActionDraftContent
    value = model.model_validate(content())
    assert model.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_fingerprint", "short"),
        ("expected_digest", "changed"),
        ("actor_id", "model-invented-user"),
        ("expires_at", "2026-10-06T12:00:00"),
        ("password", "secret"),
    ],
)
def test_malformed_or_extra_native_content_is_refused(field: str, value: object) -> None:
    model = import_module(
        "src.domains.agents.application.draft_models"
    ).ApplicationActionDraftContent
    with pytest.raises(ValidationError):
        model.model_validate({**content(), field: value})
