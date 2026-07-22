"""Guard the CROSS-DOMAIN CHAINS guidance blocks (P4, interdomain program Lot 1).

The planner and ReAct prompts must carry the concrete high-value chaining
examples (place→phone call, event→route+weather, email→file attachments,
task→event). The adjacency matrix in ``domain_taxonomy.py`` only feeds the
initiative node's structural pre-filter — the planner/ReAct LLMs learn the
chains from these prompt blocks. Removing them silently degrades chaining.
"""

import pytest

from src.domains.agents.prompts.prompt_loader import load_prompt


@pytest.mark.unit
class TestCrossDomainChainsGuidance:
    """Both orchestration prompts carry the chaining guidance."""

    def test_planner_prompt_has_chains_block(self):
        """smart_planner_prompt must document the cross-domain chains."""
        content = load_prompt("smart_planner_prompt", version="v1")
        assert "CROSS-DOMAIN CHAINS" in content

    def test_planner_chains_cover_the_four_pairs(self):
        """The four audited high-value pairs are all present (planner)."""
        content = load_prompt("smart_planner_prompt", version="v1")
        for marker in ("phone", "arrival_time", "attachment", "slot"):
            assert marker in content, f"planner chains block misses '{marker}'"

    def test_react_prompt_has_chains_block(self):
        """react_agent_prompt must document the cross-domain chains."""
        content = load_prompt("react_agent_prompt", version="v1")
        assert "<CrossDomainChains>" in content

    def test_react_chains_have_no_stray_format_braces(self):
        """The block must not break str.format on the dynamic placeholders."""
        content = load_prompt("react_agent_prompt", version="v1")
        # Formatting with the documented placeholders must not raise on
        # any stray literal brace introduced by the guidance block.
        content.format(
            personnalite="p",
            user_language="fr",
            semantic_dependencies="none",
            current_datetime="2026-07-22 10:00",
            user_timezone="Europe/Paris",
        )
