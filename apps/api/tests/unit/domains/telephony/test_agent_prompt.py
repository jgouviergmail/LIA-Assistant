"""Unit tests for the ElevenLabs agent config builder (P2.2)."""

import pytest

from src.core.i18n_telephony import GREETING_FIRST_MESSAGE
from src.domains.telephony.agent_prompt import build_agent_config
from src.domains.telephony.schemas import StructuredCallData


@pytest.mark.unit
def test_build_agent_config_maps_language_and_includes_name():
    cfg = build_agent_config("zh-CN", "Jean")
    assert cfg.language == "zh"  # zh-CN -> zh for ElevenLabs
    assert "Jean" in cfg.name
    # Instant localized greeting (identity only — an empty first message caused
    # a silent standoff at pickup; the LLM continues with objective + question).
    assert cfg.first_message == GREETING_FIRST_MESSAGE["zh"]
    assert "{{user_name}}" in cfg.first_message
    assert "{{user_name}}" in cfg.system_prompt
    # Guardrails: availability shared as free/busy only, never meeting details,
    # and scheduling decisions bounded by the busy periods (2026-07 rewrite).
    assert "ONLY as free or busy" in cfg.system_prompt
    assert "never meeting titles" in cfg.system_prompt
    assert "{{availability_summary}}" in cfg.system_prompt


@pytest.mark.unit
def test_build_agent_config_fr_language():
    cfg = build_agent_config("fr", "Jean")
    assert cfg.language == "fr"
    assert cfg.first_message == GREETING_FIRST_MESSAGE["fr"]


@pytest.mark.unit
def test_agent_config_fingerprint_stable_and_sensitive():
    """Same inputs → same hash (no false re-syncs); any knob change → new hash."""
    from src.domains.telephony.agent_prompt import agent_config_fingerprint

    cfg = build_agent_config("fr", "Jean")
    knobs = {
        "llm_model": "gpt-4o-mini",
        "tts_model_id": "eleven_flash_v2_5",
        "voice_id": None,
        "audio_format": "ulaw_8000",
        "max_duration_seconds": 600,
    }
    a = agent_config_fingerprint(cfg, **knobs)
    b = agent_config_fingerprint(build_agent_config("fr", "Jean"), **knobs)
    assert a == b  # deterministic across rebuilds

    changed = agent_config_fingerprint(cfg, **{**knobs, "voice_id": "voice_x"})
    assert changed != a
    changed_llm = agent_config_fingerprint(cfg, **{**knobs, "llm_model": "gemini-2.5-flash"})
    assert changed_llm != a  # LLM pin drift must trigger the lazy re-sync
    other_user = agent_config_fingerprint(build_agent_config("fr", "Paul"), **knobs)
    assert other_user != a  # name is part of the baked config


@pytest.mark.unit
def test_build_agent_config_truncates_regional_codes():
    cfg = build_agent_config("fr-FR", "Jean")
    assert cfg.language == "fr"  # regional app codes truncate to the ISO base


@pytest.mark.unit
def test_data_collection_identifiers_match_extraction_contract():
    """The agent collects EXACTLY the fields the post-call webhook extracts.

    Guards the contract between ``_DATA_COLLECTION`` (what the agent gathers) and
    ``StructuredCallData`` (what ``return_synthesis._extract_structured`` reads) —
    a drift on either side would silently empty ``structured_data``.
    """
    cfg = build_agent_config("fr", "Jean")
    identifiers = {field["identifier"] for field in cfg.data_collection}
    assert identifiers == set(StructuredCallData.model_fields)
    # Mandate-boundary fields must be part of the contract (cost never dropped,
    # out-of-mandate decisions surfaced for the user).
    assert {"additional_costs", "pending_user_decision"} <= identifiers
