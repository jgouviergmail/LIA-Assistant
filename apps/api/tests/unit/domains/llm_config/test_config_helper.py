"""Tests for the rewritten get_llm_config_for_agent (code = source of truth)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import get_llm_config_for_agent, get_provider_api_key
from src.core.reasoning_types import ReasoningEffortToggleBudget
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
        config = get_llm_config_for_agent(settings, "router")

        assert isinstance(config, LLMAgentConfig)
        assert config.provider == "openai"
        assert config.model == "gpt-5-mini"
        assert config.temperature == 0.2
        assert config.max_tokens == 5000

    def test_applies_cache_override(self) -> None:
        """Should merge DB override on top of code defaults."""
        LLMConfigOverrideCache._overrides = {
            "router": {"model": "gpt-4.1-mini", "temperature": 0.5}
        }

        settings = MagicMock()
        config = get_llm_config_for_agent(settings, "router")

        # Overridden fields
        assert config.model == "gpt-4.1-mini"
        assert config.temperature == 0.5
        # Non-overridden fields keep defaults
        assert config.provider == "openai"
        assert config.max_tokens == 5000
        assert config.top_p == 1.0

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
        get_llm_config_for_agent(settings, "router")

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

    ``merge_config`` (via ``get_llm_config_for_agent``) drops a stored
    ``reasoning_effort`` whose shape/value does not match the *effective* model's
    ``reasoning_widget``, falling back to the model's intrinsic default. Other
    override fields are untouched.

    Regression: switching ``browser_agent`` from a DeepSeek model (enum widget,
    value ``{"effort": "off"}``) to the Qwen code-default model (toggle widget)
    left the stale enum-shaped value in the override row and crashed
    ``get_llm("browser_agent")`` with ``RuntimeError: ... must be
    ReasoningEffortToggleBudget, got ReasoningEffortEnum``.
    """

    _DEFAULT_MODEL = LLM_DEFAULTS["browser_agent"].model

    def setup_method(self) -> None:
        LLMConfigOverrideCache.reset()

    @staticmethod
    def _toggle_widget_caps(model: str) -> SimpleNamespace:
        return SimpleNamespace(
            model_id=model,
            reasoning_widget="toggle_budget",
            reasoning_enum_values=None,
            reasoning_budget_range={"min": 0, "max": 32768},
        )

    def test_incompatible_reasoning_effort_override_is_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # browser_agent's code-default model uses a Qwen toggle widget.
        monkeypatch.setattr(
            ModelCapabilitiesCache,
            "_cache",
            {self._DEFAULT_MODEL: self._toggle_widget_caps(self._DEFAULT_MODEL)},
        )
        # Override carries an enum-shaped effort left over from a previous model.
        LLMConfigOverrideCache._overrides = {
            "browser_agent": {"reasoning_effort": {"effort": "off"}, "temperature": 0.5}
        }

        config = get_llm_config_for_agent(MagicMock(), "browser_agent")

        assert config.model == self._DEFAULT_MODEL  # override didn't change the model
        assert config.reasoning_effort is None  # incompatible → dropped to model default
        assert config.temperature == 0.5  # unrelated override preserved

    def test_compatible_reasoning_effort_override_is_kept(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ModelCapabilitiesCache,
            "_cache",
            {self._DEFAULT_MODEL: self._toggle_widget_caps(self._DEFAULT_MODEL)},
        )
        LLMConfigOverrideCache._overrides = {
            "browser_agent": {"reasoning_effort": {"enabled": True, "budget": 8192}}
        }

        config = get_llm_config_for_agent(MagicMock(), "browser_agent")

        assert isinstance(config.reasoning_effort, ReasoningEffortToggleBudget)
        assert config.reasoning_effort.enabled is True
        assert config.reasoning_effort.budget == 8192

    def test_unknown_model_is_left_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Empty capabilities cache (e.g. a dynamically discovered model not in
        # the catalogue): merge_config cannot validate, so it must not mutate.
        monkeypatch.setattr(ModelCapabilitiesCache, "_cache", {})
        LLMConfigOverrideCache._overrides = {
            "browser_agent": {"reasoning_effort": {"enabled": False}}
        }

        config = get_llm_config_for_agent(MagicMock(), "browser_agent")

        assert isinstance(config.reasoning_effort, ReasoningEffortToggleBudget)
        assert config.reasoning_effort.enabled is False


@pytest.mark.unit
class TestReasoningEffortInheritanceOnModelChange:
    """What happens to the code default's ``reasoning_effort`` when a DB
    override changes the model without providing one.

    Measured defect, 2026-07-27: the three background extractors (memory,
    interests, journal) ran with NO reasoning block. The admin picks
    ``low``; the admin UI only sends fields that differ from the type's
    default (override semantics) and ``low`` IS the default, so the column
    stored NULL; the cache drops NULL fields; and this merge then read
    "model changed, no reasoning provided" as "no reasoning at all" instead
    of "keep the default". A knob that cannot express its own default value
    is a broken knob.

    Inheritance now requires proof of compatibility — never optimism.
    """

    _TYPE = "browser_agent"
    _DEFAULT = LLM_DEFAULTS["browser_agent"]

    def setup_method(self) -> None:
        LLMConfigOverrideCache.reset()

    @staticmethod
    def _caps(model: str, widget: str) -> SimpleNamespace:
        return SimpleNamespace(
            model_id=model,
            reasoning_widget=widget,
            reasoning_enum_values=["off", "low", "high"],
            reasoning_budget_range={"min": 0, "max": 32768},
        )

    def test_a_compatible_default_survives_a_model_change(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The regression this lot fixes: same widget on both sides, so the
        # admin's implicit "keep the default" must reach the runtime.
        new_model = "another-toggle-model"
        monkeypatch.setattr(
            ModelCapabilitiesCache,
            "_cache",
            {new_model: self._caps(new_model, "toggle_budget")},
        )
        LLMConfigOverrideCache._overrides = {self._TYPE: {"model": new_model, "temperature": 0.1}}

        config = get_llm_config_for_agent(MagicMock(), self._TYPE)

        assert config.model == new_model
        assert config.reasoning_effort == self._DEFAULT.reasoning_effort
        assert config.temperature == 0.1

    def test_an_incompatible_default_is_still_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # browser_agent's default is toggle-shaped; an enum-widget model cannot
        # take it, and carrying it over would crash the typed builder.
        new_model = "an-enum-model"
        monkeypatch.setattr(
            ModelCapabilitiesCache, "_cache", {new_model: self._caps(new_model, "enum")}
        )
        LLMConfigOverrideCache._overrides = {self._TYPE: {"model": new_model}}

        config = get_llm_config_for_agent(MagicMock(), self._TYPE)

        assert config.model == new_model
        assert config.reasoning_effort is None

    def test_an_unverifiable_model_drops_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Unknown model (dynamic Ollama tag, catalogue not loaded): compatibility
        # cannot be proven, so the safe branch wins — this is the property the
        # old unconditional drop protected, and it must not be lost.
        monkeypatch.setattr(ModelCapabilitiesCache, "_cache", {})
        LLMConfigOverrideCache._overrides = {self._TYPE: {"model": "some-unknown-tag"}}

        config = get_llm_config_for_agent(MagicMock(), self._TYPE)

        assert config.reasoning_effort is None

    def test_an_explicit_override_still_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        new_model = "another-toggle-model"
        monkeypatch.setattr(
            ModelCapabilitiesCache,
            "_cache",
            {new_model: self._caps(new_model, "toggle_budget")},
        )
        LLMConfigOverrideCache._overrides = {
            self._TYPE: {"model": new_model, "reasoning_effort": {"enabled": True, "budget": 4096}}
        }

        config = get_llm_config_for_agent(MagicMock(), self._TYPE)

        assert isinstance(config.reasoning_effort, ReasoningEffortToggleBudget)
        assert config.reasoning_effort.budget == 4096

    def test_no_model_change_keeps_the_default_untouched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ModelCapabilitiesCache,
            "_cache",
            {self._DEFAULT.model: self._caps(self._DEFAULT.model, "toggle_budget")},
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
