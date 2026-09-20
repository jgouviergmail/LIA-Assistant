"""The prompt blocks every voice mandate composes (ADR-301, amending ADR-299 A3, ADR-290 lot 2).

A voice that DELEGATES tells the model the same thing whichever line it
speaks on: what LIA does and only LIA, how a delegation behaves (say one
sentence, hand the request over, keep talking or wait, restitute the bounded
answer, relay LIA's question), what a delivery note is for, and the
examples. The browser mandate (``live/mandate.py``) and the phone's Live
mandate (``telephony/mandates.py``) compose that ONE block into their own
frame — the phone keeps its identity check, its acoustic output and its
``end_call``; the browser its psyche block and its provider's wire.

One instruction per context, in the file (ADR-284): the block is
``voice_delegation_block.txt``, its one-line scaffolds come from
``live_lines.txt`` through the one parser, and every ``{placeholder}`` is
produced here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from src.core.constants import LIVE_DELEGATION_TOOL_NAME
from src.core.prompt_store import parse_prompt_sections, read_prompt_file

_BLOCK: Final = "voice_delegation_block"
_LINES: Final = "live_lines"
_TONES: Final = "live_tone_lines"
#: The lines a delegation bridge returns to the voice as tool results —
#: technical English (ADR-256), the browser's and the phone's alike.
BRIDGE_LINE_KEYS: Final[tuple[str, ...]] = (
    "timed_out",
    "result_cut",
    "superseded",
    "empty_request",
    "busy",
    "quota_blocked",
    "failed",
    "budget_exhausted",
)


@dataclass(frozen=True, slots=True)
class DelegationBlockInputs:
    """What the delegation block draws on.

    Attributes:
        user_name: What the assistant calls the person.
        result_budget_tokens: The published bound of a delegated answer.
        async_delegation: The model keeps talking while a request runs (the
            block is written for that capability — a model that waits is not
            told to fill a silence).
        native_delegation: The model delegates by its own act (GPT-Live)
            rather than by calling the declared function.
        tone_notes: A delegated answer may carry a delivery note naming the
            register the answering model declared (ADR-253).
    """

    user_name: str
    result_budget_tokens: int
    async_delegation: bool
    native_delegation: bool = False
    tone_notes: bool = False


def voice_lines() -> dict[str, str]:
    """The one-line scaffolds of the voice mandates, from their lines file."""
    return dict(parse_prompt_sections(read_prompt_file(_LINES), 2))


def bridge_lines() -> dict[str, str]:
    """The lines a bridge hands the voice (published to the browser by ``/live/config``)."""
    lines = voice_lines()
    return {key: lines[key] for key in BRIDGE_LINE_KEYS}


def tone_lines() -> dict[str, str]:
    """One delivery note per register of the closed tone vocabulary (ADR-253).

    A bridge hands the voice the note of the register the answering model
    declared, beside the answer, so the voice restitutes it in the manner LIA
    chose. The file is complete over ``TONE_REGISTERS`` and holds nothing
    else (a guard says so).
    """
    return dict(parse_prompt_sections(read_prompt_file(_TONES), 2))


def personality_block(lines: dict[str, str], personality: str) -> str:
    """The personality line of a mandate: the configured instruction, or the default manner.

    One instruction per context, emitted from the file (ADR-284): the four
    voice mandates — the browser's two, the phone's two — render this the
    same way from their own lines file, so a frame that forgets the default
    line cannot leave the placeholder empty.

    Args:
        lines: The mandate's lines (``personality`` / ``no_personality``).
        personality: What the person configured, already neutralised by a
            frame that needs it; "" when none could be read.

    Returns:
        The rendered line.
    """
    configured = personality.strip()
    if configured:
        return lines["personality"].format(personality=configured)
    return lines["no_personality"]


def delegation_verb(lines: dict[str, str], *, native: bool) -> str:
    """How the mandate names the act of delegating: a function call, or the model's own act."""
    if native:
        return lines["delegate_native"]
    return lines["delegate_by_call"].format(tool_name=LIVE_DELEGATION_TOOL_NAME)


def render_delegation_block(inputs: DelegationBlockInputs) -> str:
    """The delegation block, rendered for one session.

    Args:
        inputs: The session's own facts.

    Returns:
        The block, without a trailing newline (the frame places it).
    """
    lines = voice_lines()
    delegate = delegation_verb(lines, native=inputs.native_delegation)
    if inputs.native_delegation:
        delegation_key = "delegation_native"
    else:
        delegation_key = "delegation_async" if inputs.async_delegation else "delegation_blocking"
    # One instruction per context, emitted only when its content exists
    # (ADR-284): a line of the list — its own newline included — or nothing,
    # so an absent note leaves no blank line inside the list.
    if inputs.tone_notes:
        tone_note_block = (
            lines["tone_note_native" if inputs.native_delegation else "tone_note_call"] + "\n"
        )
    else:
        tone_note_block = ""
    return (
        read_prompt_file(_BLOCK)
        .format(
            user_name=inputs.user_name,
            delegate=delegate,
            delegation_style_block=lines[delegation_key].format(delegate=delegate),
            tone_note_block=tone_note_block,
            result_budget_tokens=inputs.result_budget_tokens,
        )
        .rstrip("\n")
    )


def delegation_tool_description(user_name: str) -> str:
    """What the ONE function is for, in the words every provider and the phone's vendor read."""
    return voice_lines()["tool_description"].format(user_name=user_name)


#: The one parameter of the delegation function.
REQUEST_PARAMETER: Final = "request"


def delegation_request_schema() -> dict[str, Any]:
    """The parameters of the delegation function: the request, in the person's own words.

    The description is prose the model reads: it comes from the lines file
    (ADR-284), and the phone's webhook tool copies it from here rather than
    keeping a second wording.
    """
    return {
        "type": "object",
        "properties": {
            REQUEST_PARAMETER: {
                "type": "string",
                "description": voice_lines()["request_parameter"],
            }
        },
        "required": [REQUEST_PARAMETER],
    }


__all__ = [
    "BRIDGE_LINE_KEYS",
    "REQUEST_PARAMETER",
    "DelegationBlockInputs",
    "bridge_lines",
    "delegation_request_schema",
    "delegation_tool_description",
    "delegation_verb",
    "personality_block",
    "render_delegation_block",
    "tone_lines",
    "voice_lines",
]
