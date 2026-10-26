"""World presence cleanup port; users must not import a domain that reads users."""

from collections.abc import Awaitable, Callable
from uuid import UUID

WorldCleanup = Callable[[UUID], Awaitable[None]]
_cleanup: WorldCleanup | None = None


def install_world_cleanup(cleanup: WorldCleanup) -> None:
    """The always-imported world router installs its lifecycle owner once."""
    global _cleanup  # noqa: PLW0603 — one lifecycle seam, installed by its owner
    _cleanup = cleanup


async def cleanup_world_presence(user_id: UUID) -> None:
    """No world module is loaded in narrow account-only scripts or unit tests."""
    if _cleanup is not None:
        await _cleanup(user_id)
