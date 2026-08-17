"""DOCUMENT_GENERATION is an administrable capability wired to the env flag (ADR-226)."""

import pytest

from src.core.config import Settings
from src.domains.feature_switches.registry import CAPABILITY_SPECS, PlatformCapability


@pytest.mark.unit
class TestDocumentGenerationCapability:
    """The operator switch exists, targets the agent, and maps to a real flag."""

    def test_capability_spec_registered(self) -> None:
        spec = CAPABILITY_SPECS[PlatformCapability.DOCUMENT_GENERATION]
        assert spec.env_flag == "document_generation_enabled"
        assert "document_generation_agent" in spec.agents
        # No route of its own: the gate lives at the generate_document tool entry.
        assert spec.route_enforced is False
        assert spec.service_enforced is True
        assert spec.label_key == "capabilities.items.document_generation"

    def test_env_flag_is_a_real_setting(self) -> None:
        # A typo here silently disconnects the admin switch from the runtime flag.
        spec = CAPABILITY_SPECS[PlatformCapability.DOCUMENT_GENERATION]
        assert spec.env_flag in Settings.model_fields
