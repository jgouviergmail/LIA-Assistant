"""Explicit authority established by an ingestion credential, never a session."""

from dataclasses import dataclass
from uuid import UUID


class IngestionScopeDenied(PermissionError):
    """The authenticated credential does not grant the requested operation."""


@dataclass(frozen=True, slots=True)
class IngestionPrincipal:
    user_id: UUID
    token_id: UUID
    source_id: UUID | None
    scopes: frozenset[str]

    def require_scope(self, scope: str) -> None:
        if scope not in self.scopes:
            raise IngestionScopeDenied("ingestion_scope_denied")
