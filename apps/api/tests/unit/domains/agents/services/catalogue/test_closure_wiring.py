"""The closure must survive the max_tools cap inside the real filtering pass.

Computing the right providers is useless if the cap silently drops them.
``max_tools`` defaults to 5 (10 for multi-domain), and the production
catalogues measured 3-4 tools — so the cap genuinely binds. A catalogue that
honours the cap but offers no runnable plan is worth nothing, which is why a
closure provider outranks a filler tool, and why a closure that cannot be
applied is logged rather than silently skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.services.catalogue.strategies.normal_filtering import (
    NormalFilteringStrategy,
)
from src.domains.agents.services.smart_catalogue_service import CatalogueMetrics
from tests.unit.domains.agents.services.catalogue.conftest import wire_placement_domain


@dataclass
class _Param:
    name: str
    semantic_type: str | None = None
    required: bool = False


@dataclass
class _Output:
    path: str
    semantic_type: str | None = None


@dataclass
class MockManifest:
    name: str
    agent: str = "email_agent"
    tool_category: str | None = "search"
    description: str = ""
    parameters: list[Any] = field(default_factory=list)
    outputs: list[Any] = field(default_factory=list)
    semantic_keywords: list[str] | None = None
    # Mirrors the real ToolManifest field: catalogue filtering reads it to
    # decide reachability, so a double without it bypasses that rule.
    serves_domains: list[str] = field(default_factory=list)


@dataclass
class MockIntelligence:
    domains: list[str] = field(default_factory=lambda: ["email"])
    immediate_intent: str = "send"
    is_mutation_intent: bool = False
    for_each_detected: bool = False


@dataclass
class MockToolFilter:
    domains: list[str] = field(default_factory=lambda: ["email"])
    categories: list[str] = field(default_factory=list)
    max_tools: int = 10
    include_context_tools: bool = False


GET_EMAILS = MockManifest(
    "get_emails_tool",
    tool_category="search",
    outputs=[_Output("emails[].id", "message_id")],
)
REPLY_EMAIL = MockManifest(
    "reply_email_tool",
    tool_category="send",
    parameters=[_Param("message_id", "message_id", required=True)],
    outputs=[_Output("message_id", "message_id")],
)
SEND_EMAIL = MockManifest("send_email_tool", tool_category="send")
FILLERS = [MockManifest(f"filler_{index}_tool", tool_category="search") for index in range(1, 6)]


def _build_service(manifests: list[MockManifest]) -> MagicMock:
    from src.core.context import request_tool_manifests_ctx

    request_tool_manifests_ctx.set(manifests)

    service = MagicMock()
    service.registry.list_tool_manifests.return_value = manifests
    service._metrics = CatalogueMetrics()
    service.TOKEN_ESTIMATES = {"search": 200, "send": 250}
    service._extract_domain = lambda m: m.agent.replace("_agent", "") if m.agent else "unknown"
    wire_placement_domain(service)
    service._get_tool_category = lambda name: (
        "send" if "reply" in name or "send" in name else "search"
    )
    service._manifest_to_dict = lambda m: {"name": m.name, "description": m.description}
    service._estimate_full_tokens = lambda domains: 3500 * len(domains)
    return service


def _run(
    manifests: list[MockManifest],
    tool_scores: dict[str, float],
    max_tools: int = 10,
) -> Any:
    service = _build_service(manifests)
    strategy = NormalFilteringStrategy(service=service)

    with (
        pytest.MonkeyPatch.context() as mp,
        patch(
            "src.domains.agents.semantic.expansion_service.get_semantic_provider_tool_names",
            return_value=set(),
        ),
    ):
        mp.setattr(
            "src.domains.agents.services.catalogue.strategies.normal_filtering"
            ".ToolFilter.from_intelligence",
            lambda intel: MockToolFilter(domains=intel.domains, max_tools=max_tools),
        )
        return strategy.filter(MockIntelligence(), {"all_scores": tool_scores})


@pytest.mark.unit
class TestClosureInsideTheFilteringPass:
    def test_the_excluded_read_tool_comes_back(self) -> None:
        """The production scores, verbatim: get_emails_tool sat at 0.010."""
        result = _run(
            [GET_EMAILS, REPLY_EMAIL, SEND_EMAIL],
            {"get_emails_tool": 0.010, "reply_email_tool": 0.574, "send_email_tool": 0.373},
        )

        assert "get_emails_tool" in {tool["name"] for tool in result.tools}

    def test_a_closed_catalogue_gains_nothing(self) -> None:
        """No handle required — the catalogue must not grow by a single tool."""
        result = _run(
            [GET_EMAILS, SEND_EMAIL],
            {"get_emails_tool": 0.9, "send_email_tool": 0.8},
        )

        assert {tool["name"] for tool in result.tools} == {"get_emails_tool", "send_email_tool"}


@pytest.mark.unit
class TestMaxToolsArbitration:
    def test_a_filler_is_evicted_to_make_room_for_the_provider(self) -> None:
        """A well-formed catalogue of N beats an ill-formed one of N."""
        manifests = [GET_EMAILS, REPLY_EMAIL, *FILLERS]
        scores = {"reply_email_tool": 0.9, "get_emails_tool": 0.01}
        scores.update({f"filler_{index}_tool": 0.5 - index / 100 for index in range(1, 6)})

        result = _run(manifests, scores, max_tools=4)
        names = {tool["name"] for tool in result.tools}

        assert "get_emails_tool" in names
        assert "reply_email_tool" in names
        assert len(result.tools) <= 4

    def test_the_cap_is_respected_while_closing(self) -> None:
        manifests = [GET_EMAILS, REPLY_EMAIL, *FILLERS]
        scores = {"reply_email_tool": 0.9, "get_emails_tool": 0.01}
        scores.update({f"filler_{index}_tool": 0.5 for index in range(1, 6)})

        result = _run(manifests, scores, max_tools=3)

        assert len(result.tools) <= 3

    def test_the_sole_tool_of_a_domain_is_never_evicted(self) -> None:
        """Cross-domain coverage must not be traded for closure.

        The second pass seeds one tool per domain in MANIFEST order, not by
        score, so that tool is not necessarily among the top-N protected ones.
        Here the contact tool scores lowest of all and is the only contact tool:
        it must survive even though it is the obvious sacrifice.
        """
        lone_contact = MockManifest(
            "get_contacts_tool", agent="contact_agent", tool_category="search"
        )
        manifests = [GET_EMAILS, REPLY_EMAIL, lone_contact, *FILLERS]
        scores = {"reply_email_tool": 0.9, "get_emails_tool": 0.01, "get_contacts_tool": 0.001}
        scores.update({f"filler_{index}_tool": 0.5 for index in range(1, 6)})

        service = _build_service(manifests)
        strategy = NormalFilteringStrategy(service=service)
        with (
            pytest.MonkeyPatch.context() as mp,
            patch(
                "src.domains.agents.semantic.expansion_service.get_semantic_provider_tool_names",
                return_value=set(),
            ),
        ):
            mp.setattr(
                "src.domains.agents.services.catalogue.strategies.normal_filtering"
                ".ToolFilter.from_intelligence",
                lambda intel: MockToolFilter(domains=["email", "contact"], max_tools=4),
            )
            result = strategy.filter(
                MockIntelligence(domains=["email", "contact"]), {"all_scores": scores}
            )

        assert "get_contacts_tool" in {tool["name"] for tool in result.tools}

    def test_the_lowest_scoring_filler_is_the_one_dropped(self) -> None:
        manifests = [GET_EMAILS, REPLY_EMAIL, *FILLERS]
        scores = {"reply_email_tool": 0.9, "get_emails_tool": 0.01}
        # filler_5 is the weakest — it must be the sacrifice.
        scores.update({f"filler_{index}_tool": 0.5 - index / 100 for index in range(1, 6)})

        result = _run(manifests, scores, max_tools=6)
        names = {tool["name"] for tool in result.tools}

        assert "get_emails_tool" in names
        assert "filler_5_tool" not in names
