"""One vendor agent, three mandates — what each call says and knows (lot 2).

The agent is provisioned once with the THIRD-PARTY mandate baked in (read-only,
free/busy only, a stated objective). The owner's own call and the number-
verification call speak under a DIFFERENT mandate, sent as a per-call
``conversation_config_override`` the vendor accepts once the agent allows it
(measured 2026-09-16 on the production workspace: prompt and first message).
One agent, so the voice, language, model and duration cap stay in one place —
the ElevenLabs portal (owner decision, 2026-09-16); one override per call, so
nothing of the owner's context is ever baked into an agent that also phones
strangers. The live tools of an owner call are attached to the AGENT by the
dial path and named here for the prompt: the vendor refuses ``tool_ids``
inside an override (measured on a real call, 2026-09-16 — the call died at
pickup on « Tool IDs not attached to this agent »).

The override is rendered HERE, server-side, with ``str.format`` — never left to
the vendor's ``{{...}}`` substitution. Two reasons: the guard on placeholders
can then prove every key is produced, and a ``{{x}}`` inside the person's own
data (an e-mail subject) would otherwise become a vendor variable the call
cannot resolve, so every value is neutralised before it is formatted in.

A kind without a mandate refuses the boot (ADR-085): the dial path indexes
this table without a fallback, and a silent default would run the owner's
call under the stranger's rules.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from src.core.i18n import get_language_name
from src.core.i18n_telephony import (
    get_availability_phrases,
    get_greeting_first_message,
    get_self_greeting,
    get_verification_greeting,
)
from src.core.i18n_treatments import render_treatment_domain
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.core.time_utils import format_datetime_for_display
from src.domains.telephony.models import CallKind
from src.domains.telephony.prompts.loader import TelephonyPromptName, load_telephony_prompt

#: The vendor reads ``{{name}}`` as a dynamic variable. A value carrying that
#: sequence is broken apart so it stays text — the doubled brace never reaches
#: the wire from a value.
_VENDOR_OPEN: Final = "{{"
_VENDOR_OPEN_NEUTRAL: Final = "{ {"
_VENDOR_CLOSE: Final = "}}"
_VENDOR_CLOSE_NEUTRAL: Final = "} }"
#: The language the prompt files are written in.
PROMPT_LANGUAGE: Final = "en"

#: The two greetings, keyed by kind. The third-party greeting keeps the vendor
#: syntax (it is baked into the agent and the vendor fills ``{{user_name}}``);
#: the other two are rendered here.
_GREETINGS: Final[Mapping[CallKind, Callable[[str, str], str]]] = {
    CallKind.THIRD_PARTY: lambda language, _name: get_greeting_first_message(language),
    CallKind.SELF: lambda language, name: get_self_greeting(language, name=name),
    CallKind.VERIFICATION: lambda language, name: get_verification_greeting(language, name=name),
}


@dataclass(frozen=True)
class CallMandate:
    """What one kind of call needs, declared once.

    Attributes:
        kind: The call kind.
        overrides_agent: True when the call sends a per-call override (prompt
            and greeting) instead of the baked agent.
        prompt_name: The versioned prompt the override renders; None for the
            baked mandate.
        prefetch_availability: Whether the free/busy projection is read and
            given to the agent.
        rich_context: Whether the chat's context block is rendered into the
            prompt (subject to the person's own switch).
    """

    kind: CallKind
    overrides_agent: bool
    prompt_name: TelephonyPromptName | None
    prefetch_availability: bool
    rich_context: bool


@dataclass(frozen=True)
class MandateInputs:
    """Everything a rendered override can draw on for one call.

    Attributes:
        language: Backend-canonical language code.
        user_name: What the assistant calls the person.
        objective: The purpose of the call, in the person's words.
        user_context: The rendered context block (lot 4), or "" when none.
        availability_summary: The free/busy projection, or "" when not read.
        now: The instant of the dial.
        timezone: The person's IANA zone, for the spoken clock.
        verification_code: The digits to read aloud (verification only).
        live_tool_domains: The domains the live lookups of an owner call may
            read (lot 8), for the prompt — named in words, never fifty tool
            names; empty when none.
        personality: The instruction the person configured for LIA's
            personality (lot 9) — the same the chat and the voice flow weave
            in; "" when none could be read.
    """

    language: str
    user_name: str
    objective: str
    user_context: str
    availability_summary: str
    now: datetime
    timezone: str
    verification_code: str = ""
    live_tool_domains: tuple[str, ...] = ()
    personality: str = ""


MANDATES: Final[Mapping[CallKind, CallMandate]] = {
    CallKind.THIRD_PARTY: CallMandate(
        kind=CallKind.THIRD_PARTY,
        overrides_agent=False,
        prompt_name=None,
        prefetch_availability=True,
        rich_context=False,
    ),
    CallKind.SELF: CallMandate(
        kind=CallKind.SELF,
        overrides_agent=True,
        prompt_name="telephony_self_call_system_prompt",
        prefetch_availability=True,
        rich_context=True,
    ),
    CallKind.VERIFICATION: CallMandate(
        kind=CallKind.VERIFICATION,
        overrides_agent=True,
        prompt_name="telephony_verification_prompt",
        prefetch_availability=False,
        rich_context=False,
    ),
}


def assert_mandate_completeness() -> None:
    """Refuse to boot on a call kind without a mandate (ADR-085).

    Raises:
        RuntimeError: naming the kinds that have none.
    """
    missing = [kind.value for kind in CallKind if kind not in MANDATES]
    if missing:
        raise RuntimeError(f"CallKind without a mandate in telephony/mandates.py: {missing}")


def mandate_for(kind: CallKind) -> CallMandate:
    """The mandate of a kind.

    Args:
        kind: The call kind.

    Returns:
        Its mandate; the boot assert guarantees one exists.
    """
    return MANDATES[kind]


def neutralise_vendor_syntax(value: str) -> str:
    """Break any ``{{…}}`` inside a VALUE so the vendor reads it as text.

    Args:
        value: Text bound for the override prompt.

    Returns:
        The same text with doubled braces separated by a space.
    """
    return value.replace(_VENDOR_OPEN, _VENDOR_OPEN_NEUTRAL).replace(
        _VENDOR_CLOSE, _VENDOR_CLOSE_NEUTRAL
    )


def spoken_digits(code: str) -> str:
    """Space the digits of a code so a TTS reads them one by one.

    Args:
        code: The digits.

    Returns:
        ``"4 7 1 9"`` for ``"4719"``.
    """
    return " ".join(code)


def _scaffold_lines() -> dict[str, str]:
    """The one-line scaffolds of the owner prompt, from their lines file."""
    return dict(parse_prompt_sections(read_prompt_file("telephony_self_call_lines"), 2))


def _self_prompt(inputs: MandateInputs) -> str:
    template = load_telephony_prompt("telephony_self_call_system_prompt", "v1")
    phrases = get_availability_phrases(inputs.language)
    lines = _scaffold_lines()
    context_block = neutralise_vendor_syntax(inputs.user_context.strip()) or lines["no_context"]
    availability_block = (
        neutralise_vendor_syntax(inputs.availability_summary.strip()) or phrases["unavailable"]
    )
    # The domains in the prompt's own language (English): the vendor's model
    # reads each tool's description beside them.
    domains = ", ".join(
        render_treatment_domain(domain, PROMPT_LANGUAGE) for domain in inputs.live_tool_domains
    )
    live_tools_block = (
        lines["live_tools"].format(live_tool_domains=domains)
        if inputs.live_tool_domains
        else lines["no_live_tools"]
    )
    personality = neutralise_vendor_syntax(inputs.personality.strip())
    personality_block = (
        lines["personality"].format(personality=personality)
        if personality
        else lines["no_personality"]
    )
    return template.format(
        current_datetime=format_datetime_for_display(inputs.now, inputs.timezone, inputs.language),
        user_name=neutralise_vendor_syntax(inputs.user_name),
        language_name=get_language_name(inputs.language),
        objective=neutralise_vendor_syntax(inputs.objective.strip() or "A catch-up call."),
        user_context_block=context_block,
        availability_block=availability_block,
        live_tools_block=live_tools_block,
        personality_block=personality_block,
    )


def _verification_prompt(inputs: MandateInputs) -> str:
    template = load_telephony_prompt("telephony_verification_prompt", "v1")
    return template.format(
        user_name=neutralise_vendor_syntax(inputs.user_name),
        language_name=get_language_name(inputs.language),
        code_spoken=spoken_digits(inputs.verification_code),
    )


def build_override(kind: CallKind, inputs: MandateInputs) -> dict[str, Any] | None:
    """The per-call ``conversation_config_override`` of a kind, fully rendered.

    Args:
        kind: The call kind.
        inputs: What the render can draw on.

    Returns:
        The override body the client sends, or None for the baked mandate.
    """
    mandate = mandate_for(kind)
    if not mandate.overrides_agent:
        return None
    prompt = _verification_prompt(inputs) if kind is CallKind.VERIFICATION else _self_prompt(inputs)
    return {
        "agent": {
            "prompt": {"prompt": prompt},
            "first_message": _GREETINGS[kind](inputs.language, inputs.user_name),
        },
    }


__all__ = [
    "MANDATES",
    "CallMandate",
    "MandateInputs",
    "assert_mandate_completeness",
    "build_override",
    "mandate_for",
    "neutralise_vendor_syntax",
    "spoken_digits",
]
