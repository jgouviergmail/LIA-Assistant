"""TemplateRef (ADR-259): the two template identities, parsed strictly and printed back."""

from __future__ import annotations

import uuid

import pytest

from src.domains.meetings.template_ref import TemplateRef

pytestmark = pytest.mark.unit


def test_a_builtin_reference_round_trips() -> None:
    ref = TemplateRef.parse("builtin:default_minutes")
    assert ref.kind == "builtin" and ref.key == "default_minutes" and ref.id is None
    assert str(ref) == "builtin:default_minutes"
    assert ref == TemplateRef.builtin("default_minutes")


def test_a_user_reference_round_trips() -> None:
    template_id = uuid.uuid4()
    ref = TemplateRef.parse(f"user:{template_id}")
    assert ref.kind == "user" and ref.id == template_id and ref.key is None
    assert str(ref) == f"user:{template_id}"
    assert ref == TemplateRef.user(template_id)


@pytest.mark.parametrize(
    "value",
    ["builtin:", "user:", "user:not-a-uuid", "x:y", "default_minutes", "", "builtin:Bad Key"],
)
def test_any_other_shape_is_refused(value: str) -> None:
    with pytest.raises(ValueError):
        TemplateRef.parse(value)


def test_references_are_hashable_values() -> None:
    a = TemplateRef.parse("builtin:bant_analysis")
    b = TemplateRef.parse("builtin:bant_analysis")
    assert {a, b} == {a}
