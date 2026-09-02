"""The MCP sub-agent prompt carries no per-server FACT in its prose.

2026-09-02: the prompt hardcoded "the server is already authenticated on the
user's behalf" — true for GitHub, false for every ``auth_type='none'`` server
(Coingecko, Exa, Firecrawl). A fact that varies per server is DATA: it now
arrives through the ``{auth_context}`` variable, derived from ``auth_type``
by the caller, and the template stays truthful for every server.
"""

import pytest

from src.domains.agents.prompts.prompt_loader import load_prompt


@pytest.mark.unit
class TestMCPReactPromptAuthContext:
    def test_template_declares_the_auth_context_variable(self) -> None:
        assert "{auth_context}" in load_prompt("mcp_react_agent_prompt")

    def test_template_formats_with_the_declared_variables(self) -> None:
        rendered = load_prompt("mcp_react_agent_prompt").format(
            server_name="Github",
            current_datetime="2026-09-02T00:00:00Z",
            auth_context="",
        )
        assert "Github" in rendered

    def test_no_hardcoded_authentication_claim_remains(self) -> None:
        template = load_prompt("mcp_react_agent_prompt")
        assert "already authenticated" not in template
