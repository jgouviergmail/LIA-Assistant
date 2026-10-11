"""Catalogue outputs describe actual safe projections and pending confirmation."""

from enum import Enum

import pytest
from pydantic import BaseModel

from src.domains.agents.application.output_contracts import (
    pending_application_output_fields,
    projection_output_fields,
)

pytestmark = pytest.mark.unit


class State(str, Enum):
    READY = "ready"


class Projection(BaseModel):
    status: State
    title: str | None = None
    total: int = 0
    items: list[str]
    data: dict[str, str]


def test_projection_metadata_keeps_enum_types_nullability_and_actual_keys():
    fields = {field.path: field for field in projection_output_fields(Projection)}
    assert set(fields) == set(Projection.model_fields)
    assert {key: field.type for key, field in fields.items()} == {
        "status": "string",
        "title": "string",
        "total": "integer",
        "items": "array",
        "data": "object",
    }
    assert fields["title"].nullable
    assert not fields["status"].nullable


def test_pending_output_never_describes_completed_or_private_execution():
    fields = pending_application_output_fields()
    assert [(field.path, field.type) for field in fields] == [("draft", "object")]
    fields.clear()
    assert pending_application_output_fields()
