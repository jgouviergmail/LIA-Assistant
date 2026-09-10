"""Stable identities for the effect ledger (ADR-263).

A digest answers *"is this still exactly the same object?"* — never *"is this
object correct?"*. Three identities are kept: the call that was authorised, the
draft the user was shown (ADR-092: what is confirmed must be what was last
displayed) and the result that came back.

``args_digest`` delegates to the loop guard's KEYED digest rather than hashing
again: one definition of "the same call", shared with the no-progress guard,
and keyed so a reader of the row cannot rebuild the arguments from it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from src.core.config import settings
from src.domains.agents.utils.loop_guard import compute_call_digest


def args_digest(tool_name: str, args: Mapping[str, Any] | None) -> str:
    """Keyed digest of one tool call (name + normalised arguments).

    Args:
        tool_name: Name of the tool being called.
        args: Call arguments; ``None`` is the empty call.

    Returns:
        64-character hex digest; identical calls yield identical digests.
    """
    return compute_call_digest(tool_name, dict(args or {}), settings.secret_key)


def payload_digest(payload: Any) -> str:
    """SHA-256 of a canonical JSON rendering of ``payload``.

    Not keyed: this one identifies a value the row already carries (a result, a
    draft), so it adds no secrecy — it exists to detect a change, and to let a
    reader verify that the stored payload is the one the digest describes.

    Args:
        payload: Any value; what JSON cannot render falls back to ``str()``.

    Returns:
        64-character hex digest, stable across key order.
    """
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def drafts_digest(contents: Sequence[Mapping[str, Any]]) -> str:
    """Identity of what a workboard run showed the person (ADR-276, lot 7).

    ONE draft or a BATCH of them, in order: approving « send these three »
    approves those three and no other set, so the identity covers the whole
    list and a batch of one is not the same identity as the bare draft.

    Args:
        contents: The ``draft_content`` mappings, in presentation order.

    Returns:
        64-character hex digest.
    """
    return payload_digest([dict(content) for content in contents])


def draft_digest(draft_content: Mapping[str, Any]) -> str:
    """Identity of the draft content the user was shown (ADR-092 binding).

    An edit yields a new digest, hence a new claim: the ledger cannot confuse
    the version that was approved with the version that was sent.

    Args:
        draft_content: The ``draft_content`` mapping of a pending draft.

    Returns:
        64-character hex digest.
    """
    return payload_digest(dict(draft_content))
