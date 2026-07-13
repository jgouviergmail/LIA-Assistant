"""Unit tests for the ElevenLabs agent config builder (P2.2)."""

import pytest

from src.domains.telephony.agent_prompt import build_agent_config
from src.domains.telephony.schemas import StructuredCallData


@pytest.mark.unit
def test_build_agent_config_maps_language_and_includes_name():
    cfg = build_agent_config("zh-CN", "Jean")
    assert cfg.language == "zh"  # zh-CN -> zh for ElevenLabs
    assert "Jean" in cfg.name
    assert "{{objective}}" in cfg.first_message
    assert "{{user_name}}" in cfg.system_prompt
    # Guardrail: free/busy only, never details.
    assert "free/busy" in cfg.system_prompt


@pytest.mark.unit
def test_build_agent_config_fr_disclosure():
    cfg = build_agent_config("fr", "Jean")
    assert cfg.language == "fr"
    assert cfg.first_message.startswith("Bonjour")


@pytest.mark.unit
def test_build_agent_config_unknown_language_falls_back_to_english():
    cfg = build_agent_config("xx", "Jean")
    assert cfg.first_message.startswith("Hello")


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
