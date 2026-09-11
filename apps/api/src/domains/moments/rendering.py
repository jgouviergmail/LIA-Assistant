"""Turning a served moment into the FRESH block the decision reads first.

The heartbeat's dynamic context is English — the person's own language is
applied when the message is WRITTEN, not when the decision is taken — so this
renders English, like ``wake_context.fresh_section`` beside it.

It lives in ``moments`` rather than in ``heartbeat`` because the vocabulary is
the moment's: the headline comes from the kind's spec and the lines from its
revalidation. The heartbeat only knows that something became true.
"""

from __future__ import annotations

from typing import Any

from src.core.prompt_store import read_prompt_file

#: The versioned file this section is rendered from. Read by PATH (the shared
#: ``core.prompt_store`` reader, telephony's precedent) rather than through the
#: agents loader, so ``moments`` never imports ``agents``.
_PROMPT_NAME = "moment_fresh_prompt"


def render_moment_section(moment: Any) -> str:
    """Render one served moment as the prompt's opening FRESH block.

    Args:
        moment: A ``ServedMoment`` — duck-typed so the heartbeat's schema module
            need not import the moments package to annotate its field.

    Returns:
        The block, always non-empty: the sweep woke for this, and a blank line
        would tell the model it was woken for nothing.
    """
    headline = str(getattr(moment, "headline", "") or "Something just became true.")
    lines = tuple(getattr(moment, "lines", ()) or ())
    body = "\n".join(f"  - {line}" for line in lines)
    fresh = read_prompt_file(_PROMPT_NAME).strip().format(headline=headline)
    return f"{fresh}\n{body}" if body else fresh
