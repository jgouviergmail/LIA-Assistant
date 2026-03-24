"""
Unit tests for NormalFilteringStrategy domain coverage (CORRECTION 6).

Tests coverage:
- Top-N (N=2) tools per domain are protected from threshold filtering
- Single domain with multiple tools protects top-2
- Cross-domain queries protect top-2 per domain
- Tools below threshold but in top-N are kept

Target: NormalFilteringStrategy in
    domains/agents/services/catalogue/strategies/normal_filtering.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.domains.agents.services.catalogue.strategies.normal_filtering import (
    _DOMAIN_COVERAGE_TOP_N,
    NormalFilteringStrategy,
)
from src.domains.agents.services.smart_catalogue_service import CatalogueMetrics

# =============================================================================
# Fixtures & Helpers
# =============================================================================


@dataclass
class MockManifest:
    """Minimal manifest for testing."""

    name: str
    agent: str = ""
    description: str = ""
    parameters: list[Any] = field(default_factory=list)
    outputs: list[Any] = field(default_factory=list)
    semantic_keywords: list[str] | None = None


@dataclass
class MockIntelligence:
    """Minimal QueryIntelligence for testing."""

    domains: list[str] = field(default_factory=lambda: ["contact"])
    immediate_intent: str = "search"
    is_mutation_intent: bool = False
    for_each_detected: bool = False


@dataclass
class MockToolFilter:
    """Minimal ToolFilter for testing."""

    domains: list[str] = field(default_factory=lambda: ["contact"])
    categories: list[str] = field(default_factory=list)
    max_tools: int = 10
    include_context_tools: bool = False


def _build_mock_service(manifests: list[MockManifest]) -> MagicMock:
    """Build a mock SmartCatalogueService with given manifests."""
    from src.core.context import request_tool_manifests_ctx

    # Set the per-request ContextVar so get_request_tool_manifests() works in tests
    request_tool_manifests_ctx.set(manifests)

    service = MagicMock()
    service.registry.list_tool_manifests.return_value = manifests
    service._metrics = CatalogueMetrics()
    service.TOKEN_ESTIMATES = {"search": 200, "update": 250, "delete": 200, "utility": 150}
    service.DOMAIN_FULL_TOKENS = {"contact": 5500, "event": 4000, "email": 3500}

    def extract_domain(manifest: MockManifest) -> str:
        return manifest.agent.replace("_agent", "") if manifest.agent else "unknown"

    def get_tool_category(name: str) -> str:
        if "search" in name or "get_" in name or "detail" in name:
            return "search"
        if "delete" in name:
            return "delete"
        if "update" in name:
            return "update"
        return "utility"

    def manifest_to_dict(manifest: MockManifest) -> dict:
        return {"name": manifest.name, "description": manifest.description}

    def estimate_full_tokens(domains: list[str]) -> int:
        return sum(service.DOMAIN_FULL_TOKENS.get(d, 2000) for d in domains)

    service._extract_domain = extract_domain
    service._get_tool_category = get_tool_category
    service._manifest_to_dict = manifest_to_dict
    service._estimate_full_tokens = estimate_full_tokens
    return service


# =============================================================================
# Tests: Domain Coverage Top-N
# =============================================================================


class TestDomainCoverageTopN:
    """CORRECTION 6: Top-N tools per domain should be protected from filtering."""

    def test_constant_is_2(self) -> None:
        """Domain coverage constant should be 2."""
        assert _DOMAIN_COVERAGE_TOP_N == 2

    def test_top_2_tools_protected_per_domain(self) -> None:
        """Top-2 tools by score per domain should survive threshold filtering."""
        manifests = [
            MockManifest(name="get_contacts_tool", agent="contact_agent"),
            MockManifest(name="get_contact_details_tool", agent="contact_agent"),
            MockManifest(name="search_contacts_tool", agent="contact_agent"),
        ]
        service = _build_mock_service(manifests)
        strategy = NormalFilteringStrategy(service=service)

        intelligence = MockIntelligence(domains=["contact"])

        # Scores: get_contacts=0.30 (above threshold), details=0.10 (below), search=0.05 (below)
        # Top-2 by score: get_contacts + details → both protected
        tool_selection_result = {
            "all_scores": {
                "get_contacts_tool": 0.30,
                "get_contact_details_tool": 0.10,
                "search_contacts_tool": 0.05,
            },
        }

        # Mock ToolFilter.from_intelligence
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.domains.agents.services.catalogue.strategies.normal_filtering.ToolFilter.from_intelligence",
                lambda intel: MockToolFilter(domains=intel.domains, max_tools=10),
            )
            result = strategy.filter(intelligence, tool_selection_result)

        tool_names = [t["name"] for t in result.tools]
        # Top-2 protected: get_contacts (0.30) and details (0.10)
        assert "get_contacts_tool" in tool_names
        assert "get_contact_details_tool" in tool_names

    def test_cross_domain_protects_top_2_per_domain(self) -> None:
        """Cross-domain query should protect top-2 per domain."""
        manifests = [
            MockManifest(name="get_contacts_tool", agent="contact_agent"),
            MockManifest(name="get_contact_details_tool", agent="contact_agent"),
            MockManifest(name="get_events_tool", agent="event_agent"),
            MockManifest(name="get_event_details_tool", agent="event_agent"),
        ]
        service = _build_mock_service(manifests)
        strategy = NormalFilteringStrategy(service=service)

        intelligence = MockIntelligence(domains=["contact", "event"])

        # All below threshold (0.15) but top-2 per domain protected
        tool_selection_result = {
            "all_scores": {
                "get_contacts_tool": 0.12,
                "get_contact_details_tool": 0.08,
                "get_events_tool": 0.10,
                "get_event_details_tool": 0.06,
            },
        }

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.domains.agents.services.catalogue.strategies.normal_filtering.ToolFilter.from_intelligence",
                lambda intel: MockToolFilter(
                    domains=intel.domains,
                    max_tools=10,
                    include_context_tools=False,
                ),
            )
            result = strategy.filter(intelligence, tool_selection_result)

        tool_names = [t["name"] for t in result.tools]
        # All 4 tools should be protected (2 per domain, 2 domains)
        assert "get_contacts_tool" in tool_names
        assert "get_contact_details_tool" in tool_names
        assert "get_events_tool" in tool_names
        assert "get_event_details_tool" in tool_names

    def test_third_tool_below_threshold_excluded(self) -> None:
        """Third tool per domain (not in top-2) should be excluded if below threshold."""
        manifests = [
            MockManifest(name="get_contacts_tool", agent="contact_agent"),
            MockManifest(name="get_contact_details_tool", agent="contact_agent"),
            MockManifest(name="search_contacts_tool", agent="contact_agent"),
        ]
        service = _build_mock_service(manifests)
        strategy = NormalFilteringStrategy(service=service)

        intelligence = MockIntelligence(domains=["contact"])

        # search_contacts has lowest score and is 3rd → NOT protected
        tool_selection_result = {
            "all_scores": {
                "get_contacts_tool": 0.12,
                "get_contact_details_tool": 0.08,
                "search_contacts_tool": 0.03,
            },
        }

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.domains.agents.services.catalogue.strategies.normal_filtering.ToolFilter.from_intelligence",
                lambda intel: MockToolFilter(domains=intel.domains, max_tools=10),
            )
            result = strategy.filter(intelligence, tool_selection_result)

        tool_names = [t["name"] for t in result.tools]
        # Top-2 protected, third excluded (below threshold and not protected)
        assert "get_contacts_tool" in tool_names
        assert "get_contact_details_tool" in tool_names
        assert "search_contacts_tool" not in tool_names

    def test_no_scores_returns_all_tools(self) -> None:
        """Without scores, all tools in matching domains should be included."""
        manifests = [
            MockManifest(name="get_contacts_tool", agent="contact_agent"),
            MockManifest(name="get_contact_details_tool", agent="contact_agent"),
        ]
        service = _build_mock_service(manifests)
        strategy = NormalFilteringStrategy(service=service)

        intelligence = MockIntelligence(domains=["contact"])

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.domains.agents.services.catalogue.strategies.normal_filtering.ToolFilter.from_intelligence",
                lambda intel: MockToolFilter(domains=intel.domains, max_tools=10),
            )
            result = strategy.filter(intelligence, tool_selection_result=None)

        assert result.tool_count == 2
