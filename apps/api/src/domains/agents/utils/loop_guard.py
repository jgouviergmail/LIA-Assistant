"""No-progress guard: stop an agent that keeps making the same call.

The ReAct loop already has two ceilings — a maximum iteration count and a
compute budget. Neither notices *stagnation*: an agent that calls
``get_emails_tool(query="unread")`` fifteen times in a row burns the whole
budget, the user's tokens and the provider quota before either ceiling fires,
and the turn ends on a timeout rather than on an answer.

This module recognises the shape of that failure — the **exact same call**, same
name and same arguments — and lets the caller cut it short.

What is stored, and what is not
-------------------------------
Only an HMAC digest and a counter. Never the tool name, never the arguments:
the table lives in the LangGraph checkpoint, i.e. in PostgreSQL, and tool
arguments routinely carry the user's own data (an email query, a contact name).
A plain SHA-256 of a low-entropy argument set would be trivially reversible by
brute force, so the digest is keyed with the server secret. The same key across
workers is what makes a digest comparable after a HITL resume lands on a
different process — a per-process key (the shape this pattern usually takes)
would silently reset the guard on every resume.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

# Distinct calls tracked per turn. A turn that legitimately makes more than this
# many DIFFERENT calls has already lost to the iteration ceiling; the cap only
# stops an adversarial or degenerate turn from growing the checkpoint.
MAX_TRACKED_DIGESTS = 64


def compute_call_digest(tool_name: str, arguments: dict[str, Any] | None, secret: str) -> str:
    """Return a stable, non-reversible digest of a tool call.

    Args:
        tool_name: Name of the tool being called.
        arguments: Call arguments; ``None`` is treated as ``{}``.
        secret: Server-side key (``settings.secret_key``). Shared by every
            worker so the digest survives a resume on another process.

    Returns:
        Hex digest. Identical calls yield identical digests; key order and
        non-serialisable values are normalised first, otherwise two identical
        calls could hash differently and the guard would never fire.
    """
    payload = json.dumps(
        [str(tool_name or ""), dict(arguments or {})],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def register_call(
    digests: dict[str, int],
    digest: str,
    *,
    block_threshold: int,
    terminal_threshold: int,
) -> tuple[dict[str, int], str]:
    """Record one call and say what to do with it.

    The table is copied rather than mutated: LangGraph state values must be
    replaced, not edited in place, or the update can be missed.

    Args:
        digests: Current digest → count table for this turn.
        digest: Digest of the call being attempted.
        block_threshold: Repetition count at which the call is refused.
        terminal_threshold: Repetition count at which the turn should end.

    Returns:
        ``(updated_table, verdict)`` where verdict is ``"allow"``, ``"block"``
        or ``"terminal"``.
    """
    updated = dict(digests)
    count = updated.get(digest, 0) + 1

    # Past the cap we stop tracking NEW signatures, but existing counters keep
    # working — the degenerate case this guard targets repeats one signature.
    if digest in updated or len(updated) < MAX_TRACKED_DIGESTS:
        updated[digest] = count

    if count >= terminal_threshold:
        return updated, "terminal"
    if count >= block_threshold:
        return updated, "block"
    return updated, "allow"


def repeated_call_message(verdict: str) -> str:
    """Build the recoverable error handed back to the model.

    English technical message, like every other guard in this package: the model
    reformulates for the user in their own language. It has to say what to do
    next, not just that something was refused — a bare refusal is exactly what a
    stalled model retries verbatim.

    Args:
        verdict: ``"block"`` or ``"terminal"``.

    Returns:
        The ToolMessage body.
    """
    if verdict == "terminal":
        return (
            "ERROR: This exact call (same tool, same arguments) has been repeated "
            "without making progress, so the loop was stopped. Answer the user now "
            "with what you already have, and say plainly what you could not obtain."
        )
    return (
        "ERROR: This exact call (same tool, same arguments) has already been made "
        "several times and returned the same thing, so it was not run again. Do not "
        "retry it. First state in ONE short sentence why this approach did not "
        "work (Reflexion step — it will guide your next action), then either "
        "change the approach — different arguments, a different tool — or "
        "conclude with the information you already have."
    )


__all__ = [
    "MAX_TRACKED_DIGESTS",
    "compute_call_digest",
    "register_call",
    "repeated_call_message",
]
