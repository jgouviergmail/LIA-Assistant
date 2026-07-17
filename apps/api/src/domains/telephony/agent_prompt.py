"""Builder for the LIA-controlled ElevenLabs agent configuration.

The agent's guardrails are fixed here; only per-call context varies (injected as
dynamic variables at call time). The agent presents itself as the user's
assistant and may only ever share free/busy availability — never meeting details.

The fixed guardrail system prompt is a versioned file in the CENTRAL prompt
store (``src/domains/agents/prompts/v1/telephony_agent_system_prompt.txt``,
read path-only via ``telephony.prompts.loader`` — no agents import, T2). The
first message is a SHORT localized greeting (identity only) spoken the instant
the call connects — an empty one caused a silent standoff at pickup; the LLM
then continues with objective + first question at the person's first response
(the prompt's Opening mandate). Per-call context ({{objective}},
{{callee_name}}, {{availability_summary}}, {{recording_disclosure}}) is
injected as ElevenLabs dynamic variables.

The config is baked into the vendor agent at ACTIVATION, but
``TelephonyService._sync_agent_config`` re-PATCHes the agent lazily on the next
call whenever the config fingerprint (see ``agent_config_fingerprint``) drifts —
prompt/settings edits no longer require a connector deactivate/reactivate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from src.core.i18n_telephony import get_greeting_first_message
from src.domains.telephony.prompts.loader import load_telephony_prompt

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
        "description": (
            "The answer to any question asked, and any other useful outcome "
            "(information obtained, commitment, refusal reason), minimized."
        ),
    },
    {
        "identifier": "additional_costs",
        "type": "string",
        "description": (
            "Any extra cost, surcharge, price change or fee mentioned on the call, "
            "with its amount (e.g. 'extra cheese +3€'). Empty if none was discussed."
        ),
    },
    {
        "identifier": "pending_user_decision",
        "type": "string",
        "description": (
            "Anything left UNCONFIRMED for the user to decide — an option, upsell, "
            "surcharge or new information outside the mandate that you did NOT accept "
            "and flagged for a call-back. Empty if nothing was deferred."
        ),
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
    return AgentConfig(
        name=f"LIA telephony — {user_name}",
        system_prompt=load_telephony_prompt("telephony_agent_system_prompt", "v1"),
        # SHORT greeting spoken the instant the call connects. An EMPTY first
        # message caused a multi-second silent standoff at pickup (agent waited
        # for speech, callee waited for the caller); the old LONG disclosure
        # (identity + objective) made the agent stall after it. Identity plays
        # instantly, then the LLM continues with objective + first question at
        # the person's first response (Opening mandate in the prompt).
        first_message=get_greeting_first_message(user_language),
        language=lang,
        data_collection=_DATA_COLLECTION,
    )


def agent_config_fingerprint(
    cfg: AgentConfig,
    *,
    llm_model: str | None,
    tts_model_id: str | None,
    voice_id: str | None,
    audio_format: str | None,
    max_duration_seconds: int | None,
) -> str:
    """Stable fingerprint of everything baked into the vendor agent.

    Stored in ``connector_metadata`` at activation and compared on every call:
    a mismatch (prompt edit, settings change, new deployment) triggers a lazy
    in-place ``update_agent`` — no connector deactivation needed. Covers exactly
    the fields ``client._agent_config_body`` sends.
    """
    payload = {
        "name": cfg.name,
        "system_prompt": cfg.system_prompt,
        "first_message": cfg.first_message,
        "language": cfg.language,
        "data_collection": cfg.data_collection,
        "llm_model": llm_model,
        "tts_model_id": tts_model_id,
        "voice_id": voice_id,
        "audio_format": audio_format,
        "max_duration_seconds": max_duration_seconds,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
