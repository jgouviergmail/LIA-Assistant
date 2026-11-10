"""Unit tests for the ElevenLabs agent config builder (P2.2)."""

import pytest

from src.core.i18n_telephony import GREETING_FIRST_MESSAGE
from src.domains.telephony.agent_prompt import agent_config_fingerprint, build_agent_config
from src.domains.telephony.schemas import SelfCallData, StructuredCallData


@pytest.mark.unit
def test_build_agent_config_localizes_the_greeting_and_includes_name():
    cfg = build_agent_config("zh-CN", "Jean")
    assert "Jean" in cfg.name
    # Instant localized greeting (identity only — an empty first message caused
    # a silent standoff at pickup; the LLM continues with objective + question).
    assert cfg.first_message == GREETING_FIRST_MESSAGE["zh-CN"]
    assert "{{user_name}}" in cfg.first_message
    assert "{{user_name}}" in cfg.system_prompt
    # Guardrails: availability shared as free/busy only, never meeting details,
    # and scheduling decisions bounded by the busy periods (2026-07 rewrite).
    assert "ONLY as free or busy" in cfg.system_prompt
    assert "never meeting titles" in cfg.system_prompt
    assert "{{availability_summary}}" in cfg.system_prompt


@pytest.mark.unit
def test_build_agent_config_carries_no_portal_setting():
    """The agent's language, model, voice, audio format and duration cap are
    administered on the ElevenLabs portal (owner decision 2026-09-16): the
    config LIA bakes is its prompt, its greeting and its data contract."""
    cfg = build_agent_config("fr", "Jean")
    assert set(cfg.__dataclass_fields__) == {
        "name",
        "system_prompt",
        "first_message",
        "data_collection",
    }
    assert cfg.first_message == GREETING_FIRST_MESSAGE["fr"]


@pytest.mark.unit
def test_agent_config_fingerprint_stable_and_sensitive():
    """Same inputs → same hash (no false re-syncs); any knob change → new hash."""
    cfg = build_agent_config("fr", "Jean")
    a = agent_config_fingerprint(cfg)
    b = agent_config_fingerprint(build_agent_config("fr", "Jean"))
    assert a == b  # deterministic across rebuilds

    other_user = agent_config_fingerprint(build_agent_config("fr", "Paul"))
    assert other_user != a  # name is part of the baked config
    other_greeting = agent_config_fingerprint(build_agent_config("en", "Jean"))
    assert other_greeting != a  # the greeting is LIA's, and localized


@pytest.mark.unit
def test_data_collection_identifiers_match_extraction_contract():
    """The agent collects EXACTLY the fields the post-call webhook extracts.

    Guards the contract between ``_DATA_COLLECTION`` (what the agent gathers) and
    ``StructuredCallData`` (what ``return_synthesis._extract_structured`` reads) —
    a drift on either side would silently empty ``structured_data``.
    """
    cfg = build_agent_config("fr", "Jean")
    identifiers = {field["identifier"] for field in cfg.data_collection}
    # ONE agent serves both mandates (lot 4): the collection is the union of
    # what the third-party return and the owner relay each read.
    assert identifiers == set(StructuredCallData.model_fields) | set(SelfCallData.model_fields)
    # Mandate-boundary fields must be part of the contract (cost never dropped,
    # out-of-mandate decisions surfaced for the user).
    assert {"additional_costs", "pending_user_decision"} <= identifiers


@pytest.mark.unit
def test_the_agent_drops_the_vendors_default_persona_and_the_fingerprint_covers_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-373: the vendor's « helpful » lines would fight the personality LIA sends.

    The setting rides in the body AND the fingerprint, so a provisioned agent
    drifts once and is re-synced before its next call.
    """
    from src.domains.telephony.agent_prompt import agent_config_fingerprint, build_agent_config
    from src.domains.telephony.client import _agent_config_body, agent_prompt_settings

    cfg = build_agent_config("fr", "Alex")
    body = _agent_config_body(
        name=cfg.name,
        system_prompt=cfg.system_prompt,
        first_message=cfg.first_message,
        data_collection=cfg.data_collection,
    )
    prompt = body["conversation_config"]["agent"]["prompt"]
    assert prompt["ignore_default_personality"] is True
    assert agent_prompt_settings() == {"ignore_default_personality": True}
    # The fingerprint moves with the setting: a provisioned agent drifts once.
    import src.domains.telephony.agent_prompt as agent_prompt_module

    before = agent_config_fingerprint(cfg)
    monkeypatch.setattr(agent_prompt_module, "agent_prompt_settings", lambda: {})
    assert agent_config_fingerprint(cfg) != before
