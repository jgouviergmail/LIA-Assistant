"""The JEV registry declares the usages that remain, each with its own switch and slot."""

import pytest

from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage, assert_jev_registry_complete
from src.domains.system_settings.models import SystemSettingKey
from src.domains.system_settings.registry import SETTING_SPECS

pytestmark = pytest.mark.unit

_PREVIEW_KINDS = ("email", "event", "task", "file", "reminder", "ticket", "mcp", "document")


def test_retired_preview_usages_are_gone() -> None:
    """ADR-374: the eight collection previews leave with their switch and slot."""
    retired_usages = {f"filter_{kind}" for kind in _PREVIEW_KINDS}
    retired_keys = {f"JEV_FILTER_{kind.upper()}_ENABLED" for kind in _PREVIEW_KINDS}
    retired_slots = {f"jev_filter_{kind}" for kind in _PREVIEW_KINDS}

    assert not {usage.value for usage in JevUsage} & retired_usages
    assert not {key.name for key in SystemSettingKey} & retired_keys
    assert not (set(LLM_TYPES_REGISTRY) | set(LLM_DEFAULTS)) & retired_slots
    assert_jev_registry_complete()


def test_every_remaining_usage_owns_a_declared_switch_and_slot() -> None:
    for usage, spec in JEV_USAGES.items():
        assert spec.setting_key in SETTING_SPECS, usage
        assert spec.llm_type in LLM_TYPES_REGISTRY and spec.llm_type in LLM_DEFAULTS, usage
