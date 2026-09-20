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

from uuid import UUID

# The prefix and the key are minted by the voice-session value (ADR-301): the
# call's run id is ALSO the key every row of a phone session files under, and
# the shared rules read it from there — ``telephony`` imports the value, the
# value imports no carrier.
from src.domains.voice_sessions.session import PHONE_CALL_RUN_PREFIX, phone_session_key


def phone_call_run_id(call_id: UUID) -> str:
    """The run id everything a call costs is recorded under.

    Args:
        call_id: The ``phone_calls`` row.

    Returns:
        ``phone_call_<hex>`` — stable for the call's whole life, so a retried
        relay and a late lookup still land on the same summary row.
    """
    return phone_session_key(call_id)


__all__ = ["PHONE_CALL_RUN_PREFIX", "phone_call_run_id"]
