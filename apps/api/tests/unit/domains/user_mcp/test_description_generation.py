"""Describing a user's MCP server, and billing it to the person who owns it.

Extracted from ``user_mcp/service.py`` on 2026-09-07 to keep that module under
its shrink-only size cap, and shipped with no test of its own — an extraction
that moves code from a covered module to an uncovered one changes no behaviour
and loses every oracle.

Two properties matter beyond « it returns a string »:

- **the spend is billed to the server's owner.** This is an ``ACCOUNTED`` road
  (``spend_roads``): the call happens out of turn, for one person, on the
  deployment's model key — so it must reach that person's counters and nobody
  else's.
- **the fallback is reached on ANY failure.** A server whose description
  generation fails must still be routable; a raised exception here would leave
  the person's server undescribed and therefore unreachable by the router.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.user_mcp.description_generation import (
    _account_description_spend,
    generate_domain_description,
)

pytestmark = pytest.mark.unit

_TOOLS = [
    {"name": "list_repos", "description": "List the repositories"},
    {"name": "star_repo"},
]


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text
        self.usage_metadata = {"input_tokens": 30, "output_tokens": 7}


def _llm(text: str = "Answers questions about repositories.") -> Any:
    client = AsyncMock()
    client.ainvoke = AsyncMock(return_value=_Response(text))
    client.model_name = "gpt-test"
    return client


class TestTheSpendIsBilledToTheOwner:
    """An ACCOUNTED road that reaches no account is an unbilled euro."""

    async def test_the_owner_is_charged_for_their_own_server(self) -> None:
        owner = uuid.uuid4()
        with patch(
            "src.infrastructure.proactive.tracking.track_proactive_tokens",
            new=AsyncMock(),
        ) as tracked:
            await _account_description_spend(owner, "github", _llm(), _Response("x"))

        assert tracked.await_count == 1
        call = tracked.await_args.kwargs
        assert call["user_id"] == owner
        assert call["task_type"] == "mcp_description"
        assert call["tokens_in"] == 30
        assert call["tokens_out"] == 7

    async def test_the_authorship_is_the_persons_own(self) -> None:
        """They created the server; nothing about this is LIA's initiative."""
        with patch(
            "src.infrastructure.proactive.tracking.track_proactive_tokens",
            new=AsyncMock(),
        ) as tracked:
            await _account_description_spend(uuid.uuid4(), "github", _llm(), _Response("x"))

        assert tracked.await_args.kwargs["source"] == "user"

    async def test_with_no_owner_in_scope_nobody_is_charged(self) -> None:
        """Charging a random account would be worse than not accounting."""
        with patch(
            "src.infrastructure.proactive.tracking.track_proactive_tokens",
            new=AsyncMock(),
        ) as tracked:
            await _account_description_spend(None, "github", _llm(), _Response("x"))

        assert tracked.await_count == 0

    async def test_the_target_id_stays_within_its_column(self) -> None:
        with patch(
            "src.infrastructure.proactive.tracking.track_proactive_tokens",
            new=AsyncMock(),
        ) as tracked:
            await _account_description_spend(
                uuid.uuid4(), "a-very-long-server-name", _llm(), _Response("x")
            )

        assert len(tracked.await_args.kwargs["target_id"]) <= 12


class TestWhatTheModelIsTold:
    """Fed only tool names, the generator called an authenticated GitHub server
    « public GitHub repositories », and every routing surface repeated it
    (2026-09-02)."""

    async def _prompt(self, *, account_scoped: bool) -> str:
        client = _llm()
        with (
            patch("src.infrastructure.llm.get_llm", return_value=client),
            patch(
                "src.domains.agents.prompts.load_prompt",
                return_value="system",
            ),
            patch(
                "src.domains.user_mcp.description_generation._account_description_spend",
                new=AsyncMock(),
            ),
        ):
            await generate_domain_description(
                tool_list=_TOOLS, server_name="github", account_scoped=account_scoped
            )
        return str(client.ainvoke.await_args.args[0][1].content)

    async def test_an_authenticated_server_is_never_described_as_public(self) -> None:
        prompt = await self._prompt(account_scoped=True)
        assert "user's own account" in prompt
        assert "never describe this server as public-only" in prompt

    async def test_an_anonymous_server_says_so(self) -> None:
        assert "public or anonymous data" in await self._prompt(account_scoped=False)

    async def test_a_tool_without_a_description_is_still_listed(self) -> None:
        prompt = await self._prompt(account_scoped=False)
        assert "- list_repos: List the repositories" in prompt
        assert "- star_repo" in prompt


class TestWhatComesBack:
    """A description is routing material: quotes and blanks are not answers."""

    async def _generate(self, text: str) -> str:
        with (
            patch("src.infrastructure.llm.get_llm", return_value=_llm(text)),
            patch("src.domains.agents.prompts.load_prompt", return_value="system"),
            patch(
                "src.domains.user_mcp.description_generation._account_description_spend",
                new=AsyncMock(),
            ),
        ):
            return await generate_domain_description(tool_list=_TOOLS, server_name="github")

    async def test_a_generated_description_is_returned(self) -> None:
        assert await self._generate("Answers questions about repos.") == (
            "Answers questions about repos."
        )

    @pytest.mark.parametrize("quoted", ['"Repos."', "'Repos.'"])
    async def test_surrounding_quotes_are_removed(self, quoted: str) -> None:
        assert await self._generate(quoted) == "Repos."

    async def test_an_empty_answer_falls_back_rather_than_returning_nothing(self) -> None:
        """A server with an empty description is a server the router skips."""
        assert await self._generate("   ") != ""


class TestTheFallbackAlwaysAnswers:
    """A server that cannot be described must still be routable."""

    async def test_a_provider_failure_returns_the_algorithmic_description(self) -> None:
        client = AsyncMock()
        client.ainvoke = AsyncMock(side_effect=RuntimeError("provider down"))
        with (
            patch("src.infrastructure.llm.get_llm", return_value=client),
            patch("src.domains.agents.prompts.load_prompt", return_value="system"),
        ):
            described = await generate_domain_description(tool_list=_TOOLS, server_name="github")

        assert isinstance(described, str)
        assert described

    async def test_a_missing_client_never_raises_at_the_call_site(self) -> None:
        with patch("src.infrastructure.llm.get_llm", side_effect=RuntimeError("no slot")):
            described = await generate_domain_description(tool_list=_TOOLS, server_name="github")

        assert described

    async def test_no_tool_at_all_still_produces_something(self) -> None:
        with patch("src.infrastructure.llm.get_llm", side_effect=RuntimeError("no slot")):
            described = await generate_domain_description(tool_list=[], server_name="github")

        assert isinstance(described, str)
