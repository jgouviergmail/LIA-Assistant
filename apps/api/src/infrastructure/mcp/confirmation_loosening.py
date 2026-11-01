"""From the chat, LIA makes itself ask more before an MCP tool, never less (spec 2026-10-30 D7).

The assistant may only write « always » — the account's strategy, a server's
confirmation, a tool's choice — and a change of who drives a server is judged by the
computation that alerts the person on the settings page: whatever would stop LIA
asking before an act is refused, at proposal and again at the write, against the state
the write replaces. The person makes such a change on the settings page, which lists
what LIA would stop asking about. Reason: an instruction injected into content the
assistant reads must never switch a confirmation off.

Neutral ground: the personal-server writers raise the refusal, the application layer
maps its code, and neither imports the other.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

CONFIRMATION_LOOSENING = "CONFIRMATION_LOOSENING"


class ConfirmationLooseningRefused(Exception):
    """A change from the chat that would make LIA ask less; nothing was written.

    A refusal of policy, not a malformed value: no handler of « invalid input » may
    swallow it. The proposal and the execution of a card map its code; a refused
    amendment cancels the card with its sentence as the reason. That sentence is what
    the model reads, so it can send the person to the page.
    """

    code = CONFIRMATION_LOOSENING

    def __init__(self) -> None:
        self.model_message = (
            "Refused, nothing was changed: from the chat, LIA can only make itself ask "
            "more before using an MCP tool, and this change could make it ask less. The "
            "person can make it in Settings > MCP Servers, which lists exactly what LIA "
            "would stop asking about."
        )
        super().__init__(self.model_message)


class AccountStrategyJudge(Protocol):
    """Refuses a change of the account's strategy that would make LIA ask less."""

    async def __call__(self, db: AsyncSession, owner_id: UUID, candidate: bool | None) -> None: ...
