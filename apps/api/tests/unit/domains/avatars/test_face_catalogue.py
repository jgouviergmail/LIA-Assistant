"""Account avatars override public labels while retaining a verified static preview."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from src.domains.avatars.face_catalogue import merge_faces
from src.domains.avatars.schemas import AvatarFace

pytestmark = pytest.mark.unit


def test_public_catalogue_includes_the_owners_four_faces_and_static_previews():
    faces = {str(face.id): face for face in merge_faces([])}
    for identity in (
        "804c347a-26c9-4dcf-bb49-13df4bed61e8",
        "b1f6ad8f-ed78-430b-85ef-2ec672728104",
        "dd10cb5a-d31d-4f12-b69f-6db3383c006e",
        "cace3ef7-a4c4-425d-a8cf-a5358eb0c427",
    ):
        assert identity in faces
        assert faces[identity].preview_image_url.startswith("https://mintcdn.com/simli/")


def test_account_label_wins_without_losing_public_preview_or_mutating_input():
    private = AvatarFace(
        id=UUID("cace3ef7-a4c4-425d-a8cf-a5358eb0c427"), name="Impressed Tiger", source="private"
    )
    merged = merge_faces([private])
    selected = next(face for face in merged if face.id == private.id)
    assert selected.name == "Impressed Tiger"
    assert selected.preview_image_url is not None
    assert private.preview_image_url is None
    assert len({face.id for face in merged}) == len(merged)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://localhost/private",
        "https://mintcdn.com.evil.test/simli/img.png",
        "https://key@mintcdn.com/simli/img.png",
    ],
)
def test_preview_cannot_expose_credentials_or_load_an_arbitrary_origin(url):
    with pytest.raises(ValidationError):
        AvatarFace(
            id=UUID("cace3ef7-a4c4-425d-a8cf-a5358eb0c427"),
            name="Face",
            source="private",
            preview_image_url=url,
        )
