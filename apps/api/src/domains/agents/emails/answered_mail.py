"""The mails of a turn the person already answered, as lines of a block of their own (ADR-379).

Each listed mail carries its reply state in its record, and the prompts say what it
settles: the answer tells the mail answered and offers no reply to it. Measured
2026-11-11 in the response node's own chain: to an open question the model still wrote its
OPENING from the requests it read in the mails' own words — « two mails ask for a reply »
— and corrected itself two sentences later (32 openings of 60). Three rewordings changed
nothing. A block of its own, computed from the turn's items and stated LAST, after the
person's question, halved it (10 of 36); the same block right after the data, or as a
system message of its own, changed nothing. It does not remove the residual.

The lines name an item by its registry id — the id the data block lists it under — and
the instant of the answer. Nothing a correspondent wrote goes there: outside the data
block nothing marks a stranger's text as external, and the measurement showed the id
suffices where the block is read last.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.core.mail_reply_state import REPLY_STATE_KEY, answered_when


def _payload_of(item: object) -> Mapping[str, object]:
    """An item's payload, whether the registry holds the model or its checkpointed dict."""
    payload = item.get("payload") if isinstance(item, Mapping) else getattr(item, "payload", None)
    return payload if isinstance(payload, Mapping) else {}


def answered_mail_lines(registry: Mapping[str, object] | None) -> str:
    """One line per mail of the turn its mailbox says the person answered.

    Args:
        registry: The turn's registry items by id, as the data block lists them.

    Returns:
        ``- [<item id>] answered on <instant>`` lines in the registry's order; an empty
        string when the turn listed no answered mail.
    """
    lines = [
        f"- [{item_id}] {said}"
        for item_id, item in (registry or {}).items()
        if (said := answered_when(_payload_of(item).get(REPLY_STATE_KEY))) is not None
    ]
    return "\n".join(lines)


__all__ = ["answered_mail_lines"]
