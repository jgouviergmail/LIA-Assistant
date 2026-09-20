"""The live connector type (ADR-299): a category of its own, a personal key,
no conflict while alone."""

from __future__ import annotations

import pytest

from src.domains.connectors.models import (
    CATEGORY_DISPLAY_NAMES,
    ConnectorType,
    get_conflicting_connector_types,
    get_connector_display_name,
    get_functional_category,
)

pytestmark = pytest.mark.unit


def test_live_connector_type_exists() -> None:
    assert ConnectorType.GEMINI_LIVE.value == "gemini_live"


def test_live_is_its_own_category_with_a_display_name() -> None:
    assert get_functional_category(ConnectorType.GEMINI_LIVE) == "live"
    assert CATEGORY_DISPLAY_NAMES["live"] == "Live"
    assert get_connector_display_name(ConnectorType.GEMINI_LIVE) == "Live (Gemini)"


def test_live_conflicts_with_nothing_while_alone() -> None:
    assert get_conflicting_connector_types(ConnectorType.GEMINI_LIVE) == frozenset()


def test_the_second_live_type_mirrors_the_first() -> None:
    # Wave 2 (spec A9/A10): GPT-Live is the same category, its own display name,
    # the person's own key, and — the category being additive — no conflict.
    assert ConnectorType.GPT_LIVE.value == "gpt_live"
    assert get_functional_category(ConnectorType.GPT_LIVE) == "live"
    assert get_connector_display_name(ConnectorType.GPT_LIVE) == "Live (OpenAI)"
    assert get_conflicting_connector_types(ConnectorType.GPT_LIVE) == frozenset()
    assert get_conflicting_connector_types(ConnectorType.GEMINI_LIVE) == frozenset()
    assert not ConnectorType.GPT_LIVE.is_keyless
    assert not ConnectorType.GPT_LIVE.uses_global_api_key
    assert not ConnectorType.GPT_LIVE.is_oauth


def test_live_needs_the_persons_own_key() -> None:
    # Neither keyless nor on the platform key: the whole cost line rests on it
    # (cost_bearers: the provider bills the person, LIA counts nothing).
    assert not ConnectorType.GEMINI_LIVE.is_keyless
    assert not ConnectorType.GEMINI_LIVE.uses_global_api_key
    assert not ConnectorType.GEMINI_LIVE.is_oauth


def test_the_third_live_type_mirrors_the_first_two() -> None:
    # ADR-300 wave 4: ElevenLabs Agents — the same category, its own display
    # name, the person's own key, no conflict (the category is additive).
    assert ConnectorType.ELEVENLABS_LIVE.value == "elevenlabs_live"
    assert get_functional_category(ConnectorType.ELEVENLABS_LIVE) == "live"
    assert get_connector_display_name(ConnectorType.ELEVENLABS_LIVE) == "Live (ElevenLabs)"
    assert get_conflicting_connector_types(ConnectorType.ELEVENLABS_LIVE) == frozenset()
    assert not ConnectorType.ELEVENLABS_LIVE.is_keyless
    assert not ConnectorType.ELEVENLABS_LIVE.uses_global_api_key
    assert not ConnectorType.ELEVENLABS_LIVE.is_oauth
