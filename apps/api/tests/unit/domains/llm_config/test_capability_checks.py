"""Unit tests for LLM capability filtering (llm_config).

Regression coverage for the 2026-07 codebase audit (wave 1):
- Three ReAct LLM types declared ``required_capabilities=["tool_calling"]``
  while the checker only knows ``"tools"`` — and silently returns True for
  unknown capabilities. Models WITHOUT tool support were therefore offered
  for the ReAct loop, which cannot work without tools.
- The vocabulary is locked by a registry-completeness test so a future
  unknown capability string fails loudly instead of passing silently.
"""

import pytest

from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from src.domains.llm_config.schemas import ModelCapabilities
from src.domains.llm_config.service import (
    KNOWN_MODEL_CAPABILITIES,
    _model_has_capability,
)

REACT_LLM_TYPES = ["mcp_app_react_agent", "mcp_react_agent", "react_agent"]


def _make_caps(*, supports_tools: bool) -> ModelCapabilities:
    """Build a ModelCapabilities snapshot for a chat model."""
    return ModelCapabilities(
        model_id="test-model",
        kind="chat",
        max_output_tokens=4096,
        supports_tools=supports_tools,
        supports_structured_output=True,
        supports_vision=False,
        is_reasoning_model=False,
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        reasoning_widget="none",
    )


@pytest.mark.unit
@pytest.mark.parametrize("llm_type", REACT_LLM_TYPES)
def test_react_types_reject_models_without_tools(llm_type):
    """A model without tool support must fail the ReAct types' capability check."""
    caps = _make_caps(supports_tools=False)
    required = LLM_TYPES_REGISTRY[llm_type].required_capabilities

    assert required, f"{llm_type} must declare a tools requirement"
    assert not all(_model_has_capability(caps, c) for c in required)


@pytest.mark.unit
@pytest.mark.parametrize("llm_type", REACT_LLM_TYPES)
def test_react_types_accept_models_with_tools(llm_type):
    """A model with tool support passes the ReAct types' capability check."""
    caps = _make_caps(supports_tools=True)
    required = LLM_TYPES_REGISTRY[llm_type].required_capabilities

    assert all(_model_has_capability(caps, c) for c in required)


@pytest.mark.unit
def test_registry_required_capabilities_are_all_known():
    """Every capability used in LLM_TYPES_REGISTRY must be known to the checker.

    Unknown capability strings pass silently (checker returns True), which is
    how 'tool_calling' shipped unverified — this test closes the bug class.
    """
    used = {
        capability
        for metadata in LLM_TYPES_REGISTRY.values()
        for capability in metadata.required_capabilities
    }

    unknown = used - KNOWN_MODEL_CAPABILITIES
    assert not unknown, f"Unknown capabilities in LLM_TYPES_REGISTRY: {sorted(unknown)}"


class TestDeclaredCapabilitiesAreComplete:
    """A capability the code relies on must be declared, and spelled correctly."""

    def test_the_five_structured_output_slots_declare_it(self) -> None:
        """Verified at each call site: these five ask the model for a schema.

        ``heartbeat_message`` and ``contacts_agent`` matched the same heuristic
        and were checked and discarded as false positives — do not add them.
        """
        from src.domains.llm_config.constants import LLM_TYPES_REGISTRY

        for slot in (
            "query_analyzer",
            "semantic_validator",
            "document_generation",
            "memory_reference_extraction",
            "open_loop_extraction",
        ):
            assert "structured_output" in LLM_TYPES_REGISTRY[slot].required_capabilities, slot

    def test_every_declared_capability_is_a_known_one(self) -> None:
        """A typo in a declaration must not silently disable the constraint."""
        from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
        from src.domains.llm_config.service import KNOWN_MODEL_CAPABILITIES

        unknown = sorted(
            {
                capability
                for metadata in LLM_TYPES_REGISTRY.values()
                for capability in metadata.required_capabilities
                if capability not in KNOWN_MODEL_CAPABILITIES
            }
        )
        assert unknown == [], f"undeclared capability names: {unknown}"

    def test_unknown_capability_raises_instead_of_passing(self) -> None:
        """``_model_has_capability`` used to answer True to anything unknown."""
        import pytest

        from src.domains.llm_config.service import _model_has_capability
        from src.infrastructure.llm.model_profiles import ModelProfile

        with pytest.raises(ValueError, match="unknown capability"):
            _model_has_capability(ModelProfile(), "telepathy")
