"""Face identity is connector metadata; the global account opt-in is independent."""

from collections.abc import Mapping
from uuid import UUID


def read_face_id(metadata: object) -> UUID | None:
    """A legacy or damaged JSONB value is never a usable face identity."""
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get("avatar_face_id")
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def with_face_id(metadata: Mapping[str, object] | None, face_id: UUID) -> dict[str, object]:
    """Return a new tree, preserving verification and rotation metadata for JSONB."""
    return {**(metadata or {}), "avatar_face_id": str(face_id)}
