"""What a routine's confirmation card says about its MCP pre-approval (spec 2026-10-29 D9).

The agent may change, run or switch on a routine whose form pre-approved MCP
servers — it can never write that pre-approval (``scheduled_actions`` keeps it out
of every schema the agent builds). The card of such a command therefore NAMES the
servers the routine confirms for itself, so the person approves knowing it; the
names are resolved when the command is prepared (``scheduled_actions.mcp_preapproval``),
the keys themselves are covered by the routine's snapshot, so a pre-approval
changed after the card makes the command stale.
"""

from __future__ import annotations

from src.domains.agents.drafts.card_spec import PreviewLine, Row


def preapproval_rows(names: tuple[str, ...], labels: dict[str, str]) -> list[PreviewLine]:
    """The card row naming the servers a routine confirms for itself, or none.

    Args:
        names: The pre-approved servers' display names.
        labels: The card's labels in the reader's language.

    Returns:
        One row when the routine pre-approves a server, else nothing.
    """
    if not names:
        return []
    return [
        Row(
            label=labels["application_routine_mcp_preapproval"],
            value=", ".join(names),
            key="details",
        )
    ]
