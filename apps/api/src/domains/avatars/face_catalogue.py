"""Public presets are a reviewed snapshot, not an invented /faces catalogue."""

import json
from pathlib import Path

from src.domains.avatars.schemas import AvatarFace

PUBLIC_FACES = tuple(
    AvatarFace.model_validate({**item, "source": "preset"})
    for item in json.loads(
        Path(__file__).with_name("public_faces.json").read_text(encoding="utf-8")
    )["faces"]
)


def merge_faces(private: list[AvatarFace]) -> list[AvatarFace]:
    presets = {face.id: face for face in PUBLIC_FACES}
    owned = {
        face.id: face.model_copy(
            update={
                "preview_image_url": face.preview_image_url
                or (presets[face.id].preview_image_url if face.id in presets else None)
            }
        )
        for face in private
    }
    return list(owned.values()) + [face for face in PUBLIC_FACES if face.id not in owned]
