"""The mandate of the voice (ADR-299, spec A3-A4): rendered server-side.

One instruction per context, in the file (ADR-284): every ``{placeholder}`` of
``live_system_prompt.txt`` is produced HERE, and the one-line scaffolds come
from ``live_lines.txt`` through the one parser. Nothing in this module is
prose. The rendered text is placed in the credential's constraint AND replayed
by the browser in the session setup (measured 2026-09-18: the constraint does
not refuse another instruction, so the setup the server hands out is the one
that counts).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from src.core.constants import LIVE_DELEGATION_TOOL_NAME
from src.core.i18n import get_language_name
from src.core.prompt_store import read_prompt_file
from src.core.time_utils import format_datetime_for_display
from src.domains.voice_sessions.mandate import (
    BRIDGE_LINE_KEYS,
    DelegationBlockInputs,
    bridge_lines,
    delegation_request_schema,
    delegation_tool_description,
    personality_block,
    render_delegation_block,
    tone_lines,
    voice_lines,
)

_PROMPT: Final = "live_system_prompt"
#: Three or more line breaks left by an empty block collapse to a blank line.
_BLANK_RUN: Final = re.compile(r"\n{3,}")


@dataclass(frozen=True, slots=True)
class MandateInputs:
    """What the rendered mandate draws on for one session.

    Attributes:
        language: Backend-canonical language code (normalised on render).
        user_name: What the assistant calls the person.
        personality: The instruction the person configured for LIA's
            personality, or "" when none could be read.
        now: The instant the session starts.
        timezone: The person's IANA zone, for the spoken clock.
        result_budget_tokens: The published bound of a delegated answer.
        async_delegation: Whether the model keeps talking while a delegated
            request runs — the delegation block is written for that capability
            (a model that waits for the result is not told to fill a silence).
        native_delegation: Whether the model delegates by its own act (GPT-Live)
            rather than by calling the declared function — the verb the
            mandate uses, and the block that describes the wait.
        psyche_block: LIA's inner state at the session's start, rendered by
            the psyche engine's own block (the same one the reminders and the
            proactive messages carry), or "" when the engine is off for the
            instance or the person — then nothing about it is said.
        tone_notes: Whether a delegated answer may come with a delivery note
            naming the register the answering model declared (ADR-253): the
            mandate says what to do with it only when the annotation is on.
    """

    language: str
    user_name: str
    personality: str
    now: datetime
    timezone: str
    result_budget_tokens: int
    async_delegation: bool
    native_delegation: bool
    psyche_block: str = ""
    tone_notes: bool = False


#: The one-line scaffolds are the voice sessions' own (ADR-301); the browser's
#: config publishes the bridge lines and the tone notes from that one reader.
live_lines = voice_lines


def render_live_mandate(inputs: MandateInputs) -> str:
    """Render the system instruction for one session.

    Args:
        inputs: The session's own facts.

    Returns:
        The text placed in the credential constraint and replayed in ``setup``.
    """
    lines = live_lines()
    # The delegation block is the voice session's own (ADR-301): the phone's
    # Live mandate composes the very same text into its frame.
    rendered = read_prompt_file(_PROMPT).format(
        user_name=inputs.user_name,
        language_name=get_language_name(inputs.language),
        now_local=format_datetime_for_display(inputs.now, inputs.timezone, inputs.language),
        timezone=inputs.timezone,
        personality_block=personality_block(lines, inputs.personality),
        psyche_block=inputs.psyche_block.strip(),
        delegation_block=render_delegation_block(
            DelegationBlockInputs(
                user_name=inputs.user_name,
                result_budget_tokens=inputs.result_budget_tokens,
                async_delegation=inputs.async_delegation,
                native_delegation=inputs.native_delegation,
                tone_notes=inputs.tone_notes,
            )
        ),
    )
    return _BLANK_RUN.sub("\n\n", rendered)


def sample_greeting(text: str) -> str:
    """The instruction asking a live model to speak ``text`` once (the voice sample)."""
    return live_lines()["sample_greeting"].format(text=text)


def delegation_tool_declaration(user_name: str) -> dict[str, Any]:
    """The one function the voice may call, as an OpenAPI-subset declaration.

    Args:
        user_name: What the assistant calls the person (read by the model in
            the description).

    Returns:
        The declaration the provider setup carries, ``NON_BLOCKING``.
    """
    return {
        "name": LIVE_DELEGATION_TOOL_NAME,
        "description": delegation_tool_description(user_name),
        "parameters": delegation_request_schema(),
        "behavior": "NON_BLOCKING",
    }


__all__ = [
    "BRIDGE_LINE_KEYS",
    "MandateInputs",
    "bridge_lines",
    "delegation_tool_declaration",
    "live_lines",
    "render_live_mandate",
    "sample_greeting",
    "tone_lines",
]
