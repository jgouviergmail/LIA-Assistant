"""One run id per owner call — where every euro of a call lands (lot 8).

A call spends in three places: the live lookups DURING the call (a digest of
the e-mails read aloud, an embedding search over the person's documents), the
synthesis AFTER it, and the relayed turn the chat runs from what was said.
Each used to record under a run id of its own, so the call's total existed
nowhere — and the owner asked for it at the restitution.

They now share ONE deterministic id derived from the call. The per-run
summary the chat meter already reads (``message_token_summary``, unique on
``run_id`` and accumulated by column arithmetic — ADR-263's "no SELECT then
increment") therefore becomes the call's cumulated bill by construction: the
relayed answer's bubble shows it, and so does the calls list. No new column,
no new aggregate: the correlation key is the design.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

#: The relay's session prefix, kept: one family in the logs and the ledger.
PHONE_CALL_RUN_PREFIX: Final = "phone_call_"


def phone_call_run_id(call_id: UUID) -> str:
    """The run id everything a call costs is recorded under.

    Args:
        call_id: The ``phone_calls`` row.

    Returns:
        ``phone_call_<hex>`` — stable for the call's whole life, so a retried
        relay and a late lookup still land on the same summary row.
    """
    return f"{PHONE_CALL_RUN_PREFIX}{call_id.hex}"


__all__ = ["PHONE_CALL_RUN_PREFIX", "phone_call_run_id"]
