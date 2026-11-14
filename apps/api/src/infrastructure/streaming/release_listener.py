"""What the release of an account sets in motion, without depending on who listens.

The release is written by ``run_admission`` (infrastructure); what follows it — a
message that waited leaving as the person's turn (ADR-384) — needs the agent
service, which itself imports ``run_admission``. So the dependency is inverted:
this module holds the seam, the departure module INSTALLS itself into it at
import, and the boot refuses to start when nothing did, because a seam left
empty would keep every waiting message waiting in silence.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol
from uuid import UUID

from src.core.conversation_execution import RunEnd
from src.core.run_authority import run_authority_scope
from src.infrastructure.async_utils import safe_fire_and_forget


class ReleaseListener(Protocol):
    """Told once an account's graph slot has been released and committed."""

    def __call__(self, owner_id: UUID, end: RunEnd) -> Awaitable[None]:
        """React to one release.

        Args:
            owner_id: The released account.
            end: How the releasing run ended.
        """


_listener: ReleaseListener | None = None


def install_release_listener(listener: ReleaseListener) -> None:
    """Install the one listener, called by its owner's module at import.

    Args:
        listener: What runs after each release.
    """
    global _listener  # noqa: PLW0603 — one seam, installed once, by its owner
    _listener = listener


def release_listener_installed() -> bool:
    """Whether the boot found the listener installed (checked at startup)."""
    return _listener is not None


def announce_release(owner_id: UUID, end: RunEnd) -> None:
    """Hand one committed release to the listener, outside the run that ended.

    The listener starts new work for the account, so it inherits no graph
    authority and does not extend the finalizer of the run that released it.

    Args:
        owner_id: The released account.
        end: How the releasing run ended.
    """
    listener = _listener
    if listener is None:
        return
    with run_authority_scope(None):
        safe_fire_and_forget(
            _call(listener, owner_id, end),
            name="account_release_listener",
            independent_of_graph=True,
        )


async def _call(listener: ReleaseListener, owner_id: UUID, end: RunEnd) -> None:
    """Await the listener's own coroutine inside the background task."""
    await listener(owner_id, end)
