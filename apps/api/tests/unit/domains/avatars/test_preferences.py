"""Face metadata survives JSON round-trips without mutating shared trees."""

import json
from uuid import UUID

import pytest

from src.domains.avatars.preferences import read_face_id, with_face_id

pytestmark = pytest.mark.unit


def test_face_changes_preserve_connector_verification_and_do_not_mutate_the_original():
    original = {"functionally_verified": True, "rotated_at": "retained"}
    face = UUID("00000000-0000-4000-8000-000000000001")
    updated = with_face_id(original, face)
    assert updated is not original
    assert original == {"functionally_verified": True, "rotated_at": "retained"}
    assert updated["functionally_verified"] is True
    assert updated["rotated_at"] == "retained"
    assert read_face_id(json.loads(json.dumps(updated))) == face


@pytest.mark.parametrize(
    "value", [None, [], "uuid", {}, {"avatar_face_id": "bad"}, {"avatar_face_id": 123}]
)
def test_damaged_metadata_has_no_face(value):
    assert read_face_id(value) is None
