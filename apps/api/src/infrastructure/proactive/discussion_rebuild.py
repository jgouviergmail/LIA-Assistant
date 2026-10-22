"""Wake a context-only worker after its owner-fenced request has committed."""

from uuid import UUID

from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.proactive.discussion_runner import run_for_owner


def kick_context_rebuild(owner: UUID, epoch: int) -> None:
    """Start the owner-fenced rebuild in the background, after its request committed."""
    safe_fire_and_forget(
        run_for_owner(owner, rebuild_epoch=epoch),
        name="discussion_context_rebuild",
    )
