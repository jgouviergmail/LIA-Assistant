"""Builder for the LIA-controlled ElevenLabs agent configuration.

The agent's guardrails are fixed here; only per-call context varies (injected as
dynamic variables at call time). The agent presents itself as the user's
assistant and may only ever share free/busy availability — never meeting details.

The fixed guardrail system prompt is a versioned file
(``prompts/v1/telephony_agent_system_prompt.txt``); the caller-facing disclosure
first message lives in ``core.i18n_telephony`` (all 6 languages). Per-call
context ({{objective}}, {{callee_name}}, {{availability_summary}},
{{recording_disclosure}}) is injected as ElevenLabs dynamic variables.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.i18n_telephony import get_disclosure_first_message
from src.domains.agents.prompts.prompt_loader import load_prompt

# Structured data the agent must collect during the call. The identifiers MUST
# match the keys read by return_synthesis._extract_structured / StructuredCallData
# — this is the contract that lets the post-call webhook populate structured_data.
# Without this, the agent collects nothing and structured_data stays empty.
# spike(P2.0): confirm the exact ElevenLabs data-collection config path in the
# create-agent body (see client.create_agent).
_DATA_COLLECTION: list[dict[str, str]] = [
    {
        "identifier": "agreed",
        "type": "boolean",
        "description": "True if the callee agreed to the objective, false if they declined.",
    },
    {
        "identifier": "proposed_datetime",
        "type": "string",
        "description": "Any date/time proposed or agreed during the call (ISO-8601 if possible).",
    },
    {
        "identifier": "location",
        "type": "string",
        "description": "Any location proposed or agreed during the call.",
    },
    {
        "identifier": "notes",
        "type": "string",
        "description": "A short note capturing any other useful outcome, minimized.",
    },
]


@dataclass(frozen=True)
class AgentConfig:
    """Config to create the LIA-controlled ElevenLabs agent."""

    name: str
    system_prompt: str
    first_message: str
    language: str  # ISO code for ElevenLabs (fr, en, de, es, it, zh)
    data_collection: list[dict[str, str]]  # fields the agent extracts (contract w/ webhook)


def _el_language(user_language: str) -> str:
    """Map an app language code to the ElevenLabs ISO code (e.g. 'zh-CN' -> 'zh')."""
    return user_language.split("-")[0].lower()


def build_agent_config(user_language: str, user_name: str) -> AgentConfig:
    """Build the create-agent config for a user's telephony connector.

    Args:
        user_language: The user's app language code (e.g. 'fr', 'zh-CN').
        user_name: Display name used in the agent's name (never the raw phone).

    Returns:
        The immutable :class:`AgentConfig`.
    """
    lang = _el_language(user_language)
    first_message = get_disclosure_first_message(user_language)
    return AgentConfig(
        name=f"LIA telephony — {user_name}",
        system_prompt=load_prompt("telephony_agent_system_prompt", "v1"),
        first_message=first_message,
        language=lang,
        data_collection=_DATA_COLLECTION,
    )
