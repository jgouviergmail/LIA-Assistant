"""Browser page, cookies and recovery metadata belong to one runtime generation."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class BrowserScope:
    """Explicit account and root runtime; child agents reuse their parent's scope."""

    owner_id: UUID
    runtime_id: UUID

    @property
    def key(self) -> str:
        """Unambiguous field in the bounded, instance-wide browser registry."""
        return f"{self.owner_id}:{self.runtime_id}"

    @property
    def legacy_key(self) -> str | None:
        """Only the unchanged historical Main may inherit account-scoped recovery."""
        return str(self.owner_id) if self.runtime_id == self.owner_id else None
