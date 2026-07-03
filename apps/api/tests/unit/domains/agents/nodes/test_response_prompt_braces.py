"""Regression: curly braces in conversation history must not break the
response-node prompt.

`response_node` builds `ChatPromptTemplate.from_messages([("system", ...), ...])`,
which re-processes every system string as an f-string template. The base
system prompt embeds the conversation history, so literal braces from the
user/assistant (LaTeX like ``\\frac{d}{2}``, MCP/HTML payloads) were parsed
as template variables — ``{2}`` raised ``ValueError: Invalid variable name
'2'`` and crashed every follow-up turn. `escape_braces()` must neutralize
them.
"""

import pytest
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.domains.agents.prompts import escape_braces


class TestPromptBraceEscaping:
    """The exact from_messages seam response_node uses."""

    def test_raw_latex_braces_crash_from_messages(self):
        """Guards that the failure mode is real (unescaped braces raise)."""
        system_prompt = "History:\nA = \\pi \\left(\\frac{d}{2}\\right)^2"

        with pytest.raises(ValueError, match="Invalid variable name"):
            ChatPromptTemplate.from_messages(
                [("system", system_prompt), MessagesPlaceholder(variable_name="messages")]
            )

    def test_escaped_braces_build_and_render(self):
        """escape_braces() makes the same content safe end to end."""
        system_prompt = "History:\nA = \\pi \\left(\\frac{d}{2}\\right)^2 and {value} and {2}"

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", escape_braces(system_prompt)),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        # Only the real MessagesPlaceholder variable is expected.
        assert prompt.input_variables == ["messages"]

        rendered = prompt.format_messages(messages=[])
        # Braces survive verbatim (doubled -> single), nothing substituted.
        assert "\\frac{d}{2}" in rendered[0].content
        assert "{value}" in rendered[0].content
        assert "{2}" in rendered[0].content

    def test_mcp_style_html_braces_are_safe(self):
        """MCP/JSON payloads with braces don't introduce template variables."""
        system_prompt = 'data: {"nodes": [{"id": 1}], "style": {"w": 2}}'

        prompt = ChatPromptTemplate.from_messages([("system", escape_braces(system_prompt))])
        assert prompt.input_variables == []
