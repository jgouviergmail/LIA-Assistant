"""The DIRECT live session: the voice reads LIA's tools itself, and never acts (ADR-300 wave 4).

The phone's own line, in the browser (owner decision 2026-09-19): the voice
model holds the phone's derived READ-ONLY tool set (ADR-290 lot 8 —
``agents/telephony/live_tools``: search or explicit ``read`` policy, a voice
domain, speakable parameters, plus the native memory recall), voice-projected
results, the phone's context block under a token budget, and no delegation to
the chat at all. What differs from an owner call is where it is FILED — the
``live_session`` surface, the session's run id — and that is the
:class:`~src.domains.agents.telephony.live_tools.VoiceToolHost`'s job.

Why read-only, in writing (the owner's premise corrected before the design was
frozen): a direct session gains latency and nothing else. Gemini re-bills the
WHOLE context every turn, so declarations and results in the live context cost
more, not less; transcription is a rounding error; HITL, mutations and the
registers all come free with delegation. A mutation asked here is refused in
one sentence and pointed at the chat or a delegated session.

What LIA learns from a direct session (ADR-301): nothing of its exchanges
is archived turn by turn — they are KEPT in the session record and, at the
end, become the message the person would have typed, relayed as their own
turn (``infrastructure/scheduler/voice_session_closing.py``); that spoken
turn runs the six extractions, so the learning happens once, on the relay.
The mandate says so: a request is NOTED and relayed, never refused.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from src.core.config import settings
from src.core.i18n import get_language_name
from src.core.i18n_treatments import render_treatment_domain
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.core.time_utils import format_datetime_for_display
from src.domains.agents.telephony.live_tools import (
    LIVE_SESSION_SURFACE,
    LiveToolSpec,
    available_live_tools,
    function_declaration,
)
from src.domains.agents.tools.telephony_self_tools import memory_fetcher_for, spoken_text
from src.domains.live.mandate import live_lines
from src.domains.live.preferences import LivePreferences
from src.domains.live.providers.protocol import LiveSetupInputs
from src.domains.telephony.self_call_context import build_owner_context, default_fetchers
from src.domains.voice_sessions.mandate import personality_block

_PROMPT: Final = "live_direct_system_prompt"
_LINES: Final = "live_direct_lines"
#: The language the prompt itself is written in — the domains are named in it.
_PROMPT_LANGUAGE: Final = "en"
#: Three or more line breaks left by an empty block collapse to a blank line.
_BLANK_RUN: Final = re.compile(r"\n{3,}")
#: The refusal sentences a tool call may be answered with (handed to the voice).
REFUSAL_LINE_KEYS: Final[tuple[str, ...]] = ("refused_mode", "refused_tool", "budget_exhausted")
#: The lines the BROWSER holds for a direct session (published by ``/live/config``).
BROWSER_LINE_KEYS: Final[tuple[str, ...]] = ("lookup_failed",)


@dataclass(frozen=True, slots=True)
class DirectMandateInputs:
    """What the rendered direct mandate draws on for one session.

    Attributes:
        language: Backend-canonical language code.
        user_name: What the assistant calls the person.
        personality: The instruction the person configured, or "".
        now: The instant the session starts.
        timezone: The person's IANA zone, for the spoken clock.
        psyche_block: LIA's inner state block, or "".
        user_context: The rendered context block (the phone's), or "".
        tool_domains: The domains the declared tools read, in the vocabulary's
            words; empty when no tool is declared.
    """

    language: str
    user_name: str
    personality: str
    now: datetime
    timezone: str
    psyche_block: str
    user_context: str
    tool_domains: tuple[str, ...]


def direct_lines() -> dict[str, str]:
    """The one-line scaffolds of the direct mandate, from their lines file."""
    return dict(parse_prompt_sections(read_prompt_file(_LINES), 2))


def refusal_line(key: str) -> str:
    """The sentence the voice is handed when the API refuses a lookup."""
    return direct_lines()[key]


def browser_lines() -> dict[str, str]:
    """The direct-session lines the browser answers the model with itself."""
    lines = direct_lines()
    return {key: lines[key] for key in BROWSER_LINE_KEYS}


def render_direct_mandate(inputs: DirectMandateInputs) -> str:
    """Render the system instruction of a direct session.

    Args:
        inputs: The session's own facts.

    Returns:
        The text placed in the credential constraint and replayed in ``setup``.
    """
    lines = direct_lines()
    # The domains in the prompt's own language: the model reads each tool's
    # description beside them.
    domains = ", ".join(
        render_treatment_domain(domain, _PROMPT_LANGUAGE) for domain in inputs.tool_domains
    )
    live_tools_block = (
        lines["live_tools"].format(live_tool_domains=domains)
        if inputs.tool_domains
        else lines["no_live_tools"]
    )
    rendered = read_prompt_file(_PROMPT).format(
        user_name=inputs.user_name,
        language_name=get_language_name(inputs.language),
        now_local=format_datetime_for_display(inputs.now, inputs.timezone, inputs.language),
        timezone=inputs.timezone,
        personality_block=personality_block(live_lines(), inputs.personality),
        psyche_block=inputs.psyche_block.strip(),
        live_tools_block=live_tools_block,
        user_context_block=inputs.user_context.strip() or lines["no_context"],
    )
    return _BLANK_RUN.sub("\n\n", rendered)


def tool_domains(specs: tuple[LiveToolSpec, ...]) -> tuple[str, ...]:
    """The distinct domains of the declared tools, first seen first."""
    seen: dict[str, None] = {}
    for spec in specs:
        seen.setdefault(spec.domain, None)
    return tuple(seen)


async def direct_tool_specs(disabled_domains: frozenset[str]) -> tuple[LiveToolSpec, ...]:
    """The tools a direct session declares: the phone's derived set, the person's switches applied.

    The telephony flag is not this session's gate — the live capability is
    (the router's), so the feature switch is passed explicitly.
    """
    return await available_live_tools(disabled_domains=disabled_domains, feature_enabled=True)


async def direct_context(user_id: UUID, *, language: str, timezone: str) -> str:
    """The phone's context block (memories, agenda, reminders, open loops, exchanges), filed on this surface.

    Always rich: the phone's « rich context » switch answers a phone
    concern (someone else may pick up the line) that an authenticated
    browser session does not have. The person's DOMAIN switches, on the
    other hand, apply here as on the phone (``direct_tool_specs``).
    """
    return await build_owner_context(
        user_id,
        language=language,
        rich_context_enabled=True,
        fetchers=default_fetchers(
            user_id,
            language=language,
            timezone=timezone,
            memory_fetcher=memory_fetcher_for(user_id, objective="live session"),
            flatten=spoken_text,
        ),
        surface=LIVE_SESSION_SURFACE,
    )


async def build_direct_setup_inputs(
    *,
    user_id: UUID,
    model: str,
    voice: str,
    thinking_level: str | None,
    preferences: LivePreferences,
    disabled_domains: frozenset[str],
    language: str,
    timezone: str,
    display_name: str,
    now: datetime,
    personality: str,
    psyche_block: str,
) -> LiveSetupInputs:
    """Everything a provider renders into a DIRECT session's setup.

    Args:
        user_id: The person.
        model: The provider model id.
        voice: The chosen voice.
        thinking_level: The chosen level, or None.
        preferences: The person's reflexes.
        disabled_domains: The domains the person switched off for their voice.
        language: Backend-canonical language.
        timezone: The person's IANA zone.
        display_name: What the assistant calls them.
        now: The instant of the start.
        personality: The configured personality instruction, or "".
        psyche_block: LIA's inner state block, or "".

    Returns:
        The setup inputs: the direct mandate, no delegation, the declared tools.
    """
    specs = await direct_tool_specs(disabled_domains)
    context = await direct_context(user_id, language=language, timezone=timezone)
    mandate = render_direct_mandate(
        DirectMandateInputs(
            language=language,
            user_name=display_name,
            personality=personality,
            now=now,
            timezone=timezone,
            psyche_block=psyche_block,
            user_context=context,
            tool_domains=tool_domains(specs),
        )
    )
    declarations: tuple[dict[str, Any], ...] = tuple(function_declaration(spec) for spec in specs)
    return LiveSetupInputs(
        model=model,
        voice=voice,
        thinking_level=thinking_level,
        system_instruction=mandate,
        tool_declaration=None,
        direct_tools=declarations,
        preferences=preferences,
        trigger_tokens=settings.live_context_trigger_tokens,
        target_tokens=settings.live_context_target_tokens,
    )


__all__ = [
    "BROWSER_LINE_KEYS",
    "REFUSAL_LINE_KEYS",
    "DirectMandateInputs",
    "browser_lines",
    "build_direct_setup_inputs",
    "direct_context",
    "direct_lines",
    "direct_tool_specs",
    "refusal_line",
    "render_direct_mandate",
    "tool_domains",
]
