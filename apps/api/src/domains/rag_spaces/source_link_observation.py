"""Immutable, server-created metadata between provider inspection and SQL source linking."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from src.domains.rag_spaces.models import RAGDriveSource


@dataclass(frozen=True, slots=True)
class DriveLinkRoot:
    folder_id: str
    folder_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceLinkObservation:
    kind: Literal["drive", "mail"]
    space_id: UUID
    user_id: UUID
    provider_id: str
    name: str
    roots: tuple[DriveLinkRoot, ...] = ()

    def require_scope(
        self, kind: str, space_id: UUID, user_id: UUID, provider_id: str, name: str
    ) -> None:
        if (self.kind, self.space_id, self.user_id, self.provider_id, self.name) != (
            kind,
            space_id,
            user_id,
            provider_id,
            name,
        ):
            raise ValueError("Source observation does not match the requested write")


def linked_drive_roots(sources: list[RAGDriveSource]) -> tuple[DriveLinkRoot, ...]:
    return tuple(
        sorted(
            (DriveLinkRoot(source.folder_id, tuple(source.folder_ids or ())) for source in sources),
            key=lambda root: (root.folder_id, root.folder_ids),
        )
    )


def observed_source_name(
    metadata: Mapping[str, object], provider_id: str, fallback: str | None = None
) -> str:
    """Native inspection requires an actual name; existing GUI callers retain their fallback."""
    if metadata.get("id", provider_id) != provider_id:
        raise ValueError("Provider returned a different source identity")
    name = metadata.get("name") or fallback
    if not isinstance(name, str) or not name or len(name) > 500:
        raise ValueError("Provider source name missing or too large")
    return name
