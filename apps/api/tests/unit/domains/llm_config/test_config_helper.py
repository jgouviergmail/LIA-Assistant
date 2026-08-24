"""Tests for the rewritten get_llm_config_for_agent (code = source of truth)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import get_llm_config_for_agent, get_provider_api_key
from src.core.reasoning_intent import ReasoningIntent
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache


class TestGetLLMConfigForAgent:
    """Tests for get_llm_config_for_agent with code defaults + cache overrides."""

    def setup_method(self) -> None:
        """Reset cache before each test."""
        LLMConfigOverrideCache.reset()

    def test_returns_code_defaults_when_no_override(self) -> None:
        """Should return LLM_DEFAULTS when no DB override exists."""
        settings = MagicMock()
        config = get_llm_config_for_agent(settings, "hitl_classifier")

        assert isinstance(config, LLMAgentConfig)
        # Compared against the declaration, not against literals: which model a
        # slot defaults to is a configuration decision, and hard-coding it made
        # this test a tripwire for every retarget (ADR-244 moved 21 slots).
        defaults = LLM_DEFAULTS["hitl_classifier"]
        assert config.provider == defaults.provider
        assert config.model == defaults.model
        assert config.temperature == defaults.temperature
        assert config.max_tokens == defaults.max_tokens

    def test_applies_cache_override(self) -> None:
        """Should merge DB override on top of code defaults."""
        LLMConfigOverrideCache._overrides = {
            "hitl_classifier": {"model": "gpt-5.6-luna", "temperature": 0.5}
        }

        settings = MagicMock()
        config = get_llm_config_for_agent(settings, "hitl_classifier")

        defaults = LLM_DEFAULTS["hitl_classifier"]
        # Overridden fields take the override...
        assert config.model == "gpt-5.6-luna"
        assert config.temperature == 0.5
        # ...and every field the override omits keeps the code default. Read
        # from the declaration, never from a literal: the real per-agent
        # configuration lives in the database and differs between deployments,
        # so a literal here pins nothing and breaks on every retarget.
        assert config.provider == defaults.provider
        assert config.max_tokens == defaults.max_tokens
        assert config.top_p == defaults.top_p

    def test_alias_resolution(self) -> None:
        """Aliases like 'contact_agent' should resolve to 'contacts_agent'."""
        settings = MagicMock()
        config = get_llm_config_for_agent(settings, "contact_agent")

        assert isinstance(config, LLMAgentConfig)
        assert config.provider == "openai"

    def test_unknown_type_raises_error(self) -> None:
        """Should raise ValueError for unknown agent types."""
        settings = MagicMock()
        with pytest.raises(ValueError, match="Unknown agent_type"):
            get_llm_config_for_agent(settings, "nonexistent_type")

    def test_settings_parameter_not_used(self) -> None:
        """Settings parameter should not be accessed (code = source of truth)."""
        settings = MagicMock()
        get_llm_config_for_agent(settings, "hitl_classifier")

        # Settings should not have been accessed for any LLM config attribute
        assert not settings.router_llm_provider.called
        assert not settings.router_llm_model.called

    def test_all_34_types_resolve(self) -> None:
        """All 34 LLM types should resolve without error."""
        from src.domains.llm_config.constants import LLM_DEFAULTS

        settings = MagicMock()
        for llm_type in LLM_DEFAULTS:
            config = get_llm_config_for_agent(settings, llm_type)
            assert isinstance(config, LLMAgentConfig), f"Failed for type: {llm_type}"

    def test_special_types_resolve(self) -> None:
        """Previously special types should now resolve through the unified path."""
        settings = MagicMock()
        special_types = [
            "heartbeat_decision",
            "heartbeat_message",
            "mcp_app_react_agent",
            "mcp_description",
            "memory_extraction",
            "interest_extraction",
            "interest_content",
        ]
        for llm_type in special_types:
            config = get_llm_config_for_agent(settings, llm_type)
            assert isinstance(config, LLMAgentConfig), f"Failed for type: {llm_type}"

    def test_partial_override_preserves_defaults(self) -> None:
        """Override with only temperature should preserve all other defaults."""
        LLMConfigOverrideCache._overrides = {"response": {"temperature": 0.9}}

        settings = MagicMock()
        config = get_llm_config_for_agent(settings, "response")

        assert config.temperature == 0.9
        assert config.model == "qwen3.5-plus"  # Default preserved
        assert config.max_tokens == 10000  # Default preserved
        assert config.provider == "qwen"  # Default preserved


@pytest.mark.unit
class TestEffectiveConfigReasoningReconciliation:
    """A DB override must never let a stale / incompatible ``reasoning_effort``
    reach the typed reasoning builder.

    A stored ``reasoning_effort`` now SURVIVES a model change, whatever its
    original shape, and the runtime coerces its level to the nearest the new
    model offers (ADR-245).

    The regression this class was written for cannot recur by construction:
    switching ``browser_agent`` from a DeepSeek model to the Qwen code default
    used to leave a stale enum-shaped value in the override row and crash
    ``get_llm("browser_agent")`` with ``RuntimeError: ... must be
    ReasoningEffortToggleBudget, got ReasoningEffortEnum``. There is one shape
    now and nothing raises — so the tests below assert the NEW contract, and
    the first of them replays the exact stale value that used to crash.
    """

    _DEFAULT_MODEL = LLM_DEFAULTS["browser_agent"].model

    def setup_method(self) -> None:
        LLMConfigOverrideCache.reset()

    @staticmethod
    def _caps(model: str, levels: list[str] | None = None) -> SimpleNamespace:
        return SimpleNamespace(
            model_id=model,
            reasoning_widget="enum",
            reasoning_enum_values=levels,
            reasoning_budget_range=None,
            max_output_tokens=32768,
        )

    def test_the_value_that_used_to_crash_now_resolves(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exact stale override from the original regression."""
        monkeypatch.setattr(
            ModelCapabilitiesCache,
            "_cache",
            {self._DEFAULT_MODEL: self._caps(self._DEFAULT_MODEL)},
        )
        LLMConfigOverrideCache._overrides = {
            "browser_agent": {"reasoning_effort": {"effort": "off"}, "temperature": 0.5}
        }

        config = get_llm_config_for_agent(MagicMock(), "browser_agent")

        assert config.model == self._DEFAULT_MODEL
        assert config.reasoning_effort == ReasoningIntent(level="none")
        assert config.temperature == 0.5

    def test_a_legacy_toggle_shape_is_read_as_an_intent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The database still holds these until the migration runs."""
        monkeypatch.setattr(
            ModelCapabilitiesCache,
            "_cache",
            {self._DEFAULT_MODEL: self._caps(self._DEFAULT_MODEL)},
        )
        LLMConfigOverrideCache._overrides = {
            "browser_agent": {"reasoning_effort": {"enabled": True, "budget": 8192}}
        }

        config = get_llm_config_for_agent(MagicMock(), "browser_agent")

        assert config.reasoning_effort == ReasoningIntent(budget_tokens=8192)

    def test_an_unknown_model_is_left_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A dynamically discovered model has no catalogue row and needs none."""
        monkeypatch.setattr(ModelCapabilitiesCache, "_cache", {})
        LLMConfigOverrideCache._overrides = {
            "browser_agent": {"reasoning_effort": {"enabled": False}}
        }

        config = get_llm_config_for_agent(MagicMock(), "browser_agent")

        assert config.reasoning_effort == ReasoningIntent(level="none")


@pytest.mark.unit
class TestReasoningEffortInheritanceOnModelChange:
    """The code default's ``reasoning_effort`` when an override changes the model.

    Measured defect, 2026-07-27: the three background extractors (memory,
    interests, journal) ran with NO reasoning block. The admin picks ``low``;
    the admin UI only sends fields that differ from the type's default
    (override semantics) and ``low`` IS the default, so the column stored NULL;
    the cache drops NULL fields; and the merge then read "model changed, no
    reasoning provided" as "no reasoning at all". A knob that cannot express
    its own default value is a broken knob.

    ADR-245 removed the drop entirely. The value always survives, and the
    translator coerces it — which fixes the mirror image of that defect too: a
    default of ``level="none"`` dropped onto a model whose own default is
    thinking-on silently TURNED REASONING ON, the opposite of what was written.
    """

    _TYPE = "browser_agent"
    _DEFAULT = LLM_DEFAULTS["browser_agent"]

    def setup_method(self) -> None:
        LLMConfigOverrideCache.reset()

    @staticmethod
    def _caps(model: str) -> SimpleNamespace:
        return SimpleNamespace(
            model_id=model,
            reasoning_widget="enum",
            reasoning_enum_values=["none", "low", "high"],
            reasoning_budget_range=None,
            max_output_tokens=32768,
        )

    def test_the_default_survives_a_model_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        new_model = "another-model"
        monkeypatch.setattr(ModelCapabilitiesCache, "_cache", {new_model: self._caps(new_model)})
        LLMConfigOverrideCache._overrides = {self._TYPE: {"model": new_model, "temperature": 0.1}}

        config = get_llm_config_for_agent(MagicMock(), self._TYPE)

        assert config.model == new_model
        assert config.reasoning_effort == self._DEFAULT.reasoning_effort
        assert config.temperature == 0.1

    def test_the_default_survives_even_an_unverifiable_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unknown model no longer costs the operator their choice.

        Dropping was the old safe branch because the typed builder raised on a
        mismatch. Nothing raises now: an unknown model resolves to its family's
        ladder, and coercion handles a level that ladder does not offer.
        """
        monkeypatch.setattr(ModelCapabilitiesCache, "_cache", {})
        LLMConfigOverrideCache._overrides = {self._TYPE: {"model": "some-unknown-tag"}}

        config = get_llm_config_for_agent(MagicMock(), self._TYPE)

        assert config.reasoning_effort == self._DEFAULT.reasoning_effort

    def test_an_explicit_override_still_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        new_model = "another-model"
        monkeypatch.setattr(ModelCapabilitiesCache, "_cache", {new_model: self._caps(new_model)})
        LLMConfigOverrideCache._overrides = {
            self._TYPE: {"model": new_model, "reasoning_effort": {"enabled": True, "budget": 4096}}
        }

        config = get_llm_config_for_agent(MagicMock(), self._TYPE)

        assert config.reasoning_effort == ReasoningIntent(budget_tokens=4096)

    def test_no_model_change_keeps_the_default_untouched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ModelCapabilitiesCache,
            "_cache",
            {self._DEFAULT.model: self._caps(self._DEFAULT.model)},
        )
        LLMConfigOverrideCache._overrides = {self._TYPE: {"temperature": 0.3}}

        config = get_llm_config_for_agent(MagicMock(), self._TYPE)

        assert config.reasoning_effort == self._DEFAULT.reasoning_effort


class TestGetProviderApiKey:
    """Tests for the core facade over the provider API-key cache (ADR-126)."""

    def setup_method(self) -> None:
        """Reset cache before each test."""
        LLMConfigOverrideCache.reset()

    def test_returns_key_when_registered(self) -> None:
        """Should return the decrypted key stored in the cache."""
        LLMConfigOverrideCache._provider_keys = {"elevenlabs": "sk-test-key"}

        assert get_provider_api_key("elevenlabs") == "sk-test-key"

    def test_returns_none_when_absent(self) -> None:
        """Should return None for providers without a registered key."""
        assert get_provider_api_key("elevenlabs") is None
