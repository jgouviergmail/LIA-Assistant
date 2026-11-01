"""The account's MCP confirmation strategy — the column of ``users`` it lives in.

A declarative mixin like ``TurnPreferencesColumns``: what the person's MCP servers
inherit when they never chose (spec 2026-10-30 D2). NULL means never chosen — the
account follows ``MCP_HITL_REQUIRED``, the instance default — so no deployment
changes behaviour when the column appears. Read where a run builds the person's MCP
manifests (``UserMCPServerRepository.account_confirmation``) and resolved by
``infrastructure/mcp/confirmation.py``; written through the generic profile update.
Migration ``b82c5483adcf``.
"""

from __future__ import annotations

from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column


class MCPConfirmationColumns:
    """Mapped column of the account's MCP confirmation strategy (a declarative mixin)."""

    mcp_hitl_required: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment=(
            "MCP confirmation strategy: true = always ask, false = follow the servers' "
            "declarations; NULL = instance default (MCP_HITL_REQUIRED)."
        ),
    )


__all__ = ["MCPConfirmationColumns"]
