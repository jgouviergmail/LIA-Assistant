"""Guard the CAPABILITY TRUTH rule in the ReAct prompt (2026-09-02 incident).

With a conversation window full of its own past refusals ("I have no access to
your bank operations"), the ReAct model kept refusing in 1 iteration / 59
completion tokens even though the right tool was bound with a score-1.0
selection and a complete description — it imitated its own history instead of
reading the tool list. The refusals themselves dated from a defect that was
since fixed (v1.38.3 never built those tools), so every one of them was stale.

The rule states that the CURRENT turn's tool list is the sole authority on
capabilities. Removing it silently re-opens the self-imitation loop.
"""

import pytest

from src.domains.agents.prompts.prompt_loader import load_prompt


@pytest.mark.unit
class TestCapabilityTruthDirective:
    """The ReAct prompt carries the capability-truth rule."""

    def test_react_prompt_has_capability_truth_rule(self):
        """react_agent_prompt must name the current tool list as the authority."""
        content = load_prompt("react_agent_prompt", version="v1")
        assert "CAPABILITY TRUTH" in content

    def test_rule_forbids_trusting_past_refusals(self):
        """The rule must say past refusals are not evidence of a missing tool."""
        content = " ".join(load_prompt("react_agent_prompt", version="v1").split())
        assert "NOT evidence" in content

    def test_rule_survives_format(self):
        """The rule must not break str.format on the dynamic placeholders."""
        content = load_prompt("react_agent_prompt", version="v1")
        content.format(
            personnalite="p",
            user_language="fr",
            semantic_dependencies="none",
            current_datetime="2026-09-02 10:00",
            user_timezone="Europe/Paris",
        )


@pytest.mark.unit
class TestMcpSubAgentActRule:
    """The MCP sub-agent prompt forbids answering without acting.

    2026-09-02, GitHub: 3 runs out of 4 completed with ZERO tool calls,
    answering "I need your username" without trying search_repositories.
    The rule tells the sub-agent to try discovery tools before claiming
    anything is missing. A first version also hardcoded "the server is
    already authenticated on the user's behalf" — false for every
    ``auth_type='none'`` server, so that FACT now arrives through the
    ``{auth_context}`` variable, derived from ``auth_type`` by the caller
    (owner arbitration 2026-09-02: a prompt carries no per-server fact).
    """

    def test_prompt_has_act_rule(self):
        content = " ".join(load_prompt("mcp_react_agent_prompt", version="v1").split())
        assert "ACT, do not speculate" in content

    def test_auth_is_a_variable_not_a_claim(self):
        content = load_prompt("mcp_react_agent_prompt", version="v1")
        assert "already authenticated" not in content
        assert "{auth_context}" in content

    def test_rule_survives_format(self):
        content = load_prompt("mcp_react_agent_prompt", version="v1")
        content.format(
            server_name="Github",
            current_datetime="2026-09-02 15:00",
            auth_context="",
        )
