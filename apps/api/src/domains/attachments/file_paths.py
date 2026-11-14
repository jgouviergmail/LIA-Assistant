"""One account-bound path check for file publication, inspection and removal."""

from pathlib import Path
from uuid import UUID

from src.core.config import settings


def owned_asset_path(actor_id: UUID, filename: str) -> Path:
    """Resolve only a plain filename immediately within the intended account directory.

    Call off-loop: resolving a path and checking links are filesystem operations.
    Configured storage roots may be mounted; account/file links may not redirect it.
    """
    root = Path(settings.attachments_storage_path).resolve()
    account = root / str(actor_id)
    path = account / filename
    if (
        not filename
        or Path(filename).name != filename
        or any(character in filename for character in ("\\", "/", ":", "\x00"))
    ):
        raise ValueError("Invalid stored file name")
    if (
        account.is_symlink()
        or path.is_symlink()
        or account.resolve() != account
        or path.resolve().parent != account
    ):
        raise ValueError("Invalid owned file location")
    return path


def owned_relative_path(owner_id: UUID, relative: str) -> Path:
    """Reject a corrupt cross-account/traversal path before any file effect."""
    parts = relative.split("/")
    if len(parts) != 2 or parts[0] != str(owner_id):
        raise ValueError("Invalid account-relative file location")
    return owned_asset_path(owner_id, parts[1])
