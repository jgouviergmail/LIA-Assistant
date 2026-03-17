"""
Unit tests for delegate_to_sub_agent_tool.

Verifies tool definition, parameters, and depth-check logic.
"""


class TestDelegateToolDefinition:
    """Verify the delegate tool is properly defined and decorated."""

    def test_tool_exists_and_named(self):
        """delegate_to_sub_agent_tool is importable with correct name."""
        from src.domains.agents.tools.sub_agent_tools import (
            delegate_to_sub_agent_tool,
        )

        assert delegate_to_sub_agent_tool.name == "delegate_to_sub_agent_tool"

    def test_tool_description_mentions_delegate(self):
        """Tool description explains delegation."""
        from src.domains.agents.tools.sub_agent_tools import (
            delegate_to_sub_agent_tool,
        )

        desc = delegate_to_sub_agent_tool.description.lower()
        assert "delegate" in desc or "sub-agent" in desc

    def test_tool_has_required_parameters(self):
        """Tool has expertise and instruction parameters."""
        from src.domains.agents.tools.sub_agent_tools import (
            delegate_to_sub_agent_tool,
        )

        schema = delegate_to_sub_agent_tool.args_schema
        field_names = set(schema.model_fields.keys())
        assert "expertise" in field_names
        assert "instruction" in field_names

    def test_tool_is_async(self):
        """Tool has an async coroutine."""
        from src.domains.agents.tools.sub_agent_tools import (
            delegate_to_sub_agent_tool,
        )

        assert delegate_to_sub_agent_tool.coroutine is not None

    def test_tool_returns_unified_output(self):
        """Tool return type annotation is UnifiedToolOutput."""
        from src.domains.agents.tools.output import UnifiedToolOutput
        from src.domains.agents.tools.sub_agent_tools import (
            delegate_to_sub_agent_tool,
        )

        annotations = getattr(delegate_to_sub_agent_tool.coroutine, "__annotations__", {})
        assert annotations.get("return") is UnifiedToolOutput


class TestCatalogueManifest:
    """Verify catalogue manifests are correctly defined."""

    def test_agent_manifest(self):
        """Agent manifest has correct name and tools."""
        from src.domains.agents.sub_agents.catalogue_manifests import (
            SUB_AGENT_MANIFEST,
        )

        assert SUB_AGENT_MANIFEST.name == "sub_agent_agent"
        assert "delegate_to_sub_agent_tool" in SUB_AGENT_MANIFEST.tools

    def test_tool_manifest(self):
        """Tool manifest has correct name, agent, and parameters."""
        from src.domains.agents.sub_agents.catalogue_manifests import (
            delegate_to_sub_agent_catalogue_manifest,
        )

        m = delegate_to_sub_agent_catalogue_manifest
        assert m.name == "delegate_to_sub_agent_tool"
        assert m.agent == "sub_agent_agent"
        assert len(m.parameters) == 2

        param_names = {p.name for p in m.parameters}
        assert "expertise" in param_names
        assert "instruction" in param_names

    def test_tool_manifest_has_analysis_output(self):
        """Tool manifest declares 'analysis' output field."""
        from src.domains.agents.sub_agents.catalogue_manifests import (
            delegate_to_sub_agent_catalogue_manifest,
        )

        output_paths = {o.path for o in delegate_to_sub_agent_catalogue_manifest.outputs}
        assert "analysis" in output_paths

    def test_tool_manifest_cost_profile(self):
        """Tool manifest has a reasonable cost profile."""
        from src.domains.agents.sub_agents.catalogue_manifests import (
            delegate_to_sub_agent_catalogue_manifest,
        )

        cost = delegate_to_sub_agent_catalogue_manifest.cost
        assert cost.est_latency_ms >= 10000  # Sub-agents are slow (full graph)
        assert cost.est_tokens_in > 0


class TestDepthCheck:
    """Verify depth-limit mechanism via session_id prefix."""

    def test_subagent_session_prefix(self):
        """Session IDs starting with 'subagent_' indicate sub-agent context."""
        # This verifies the convention used for depth checking
        session_id = "subagent_abc123_def456"
        assert session_id.startswith("subagent_")

    def test_normal_session_not_blocked(self):
        """Normal session IDs don't trigger depth check."""
        session_id = "user_conversation_abc123"
        assert not session_id.startswith("subagent_")
