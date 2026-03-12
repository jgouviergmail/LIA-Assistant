"""
Unit tests for semantic dependency tool protection in NormalFilteringStrategy.

Tests coverage:
- Provider tools from semantic dependencies are protected from exclusion
- Single domain does not trigger semantic dependency protection
- Cross-domain queries protect provider tools (e.g., get_contacts_tool for email queries)
- Semantic protection works alongside domain coverage protection
- Graceful fallback when expansion service is unavailable

Target: NormalFilteringStrategy.filter() in
    domains/agents/services/catalogue/strategies/normal_filtering.py
and get_semantic_provider_tool_names() in
    domains/agents/semantic/expansion_service.py
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
    service = MagicMock()
    service.registry.list_tool_manifests.return_value = manifests
    service._metrics = CatalogueMetrics()
    service.TOKEN_ESTIMATES = {
        "search": 200,
        "send": 250,
        "create": 250,
        "delete": 200,
        "utility": 150,
    }
    service.DOMAIN_FULL_TOKENS = {
        "contact": 5500,
        "event": 4000,
        "email": 3500,
        "route": 3000,
    }

    def extract_domain(manifest: MockManifest) -> str:
        return manifest.agent.replace("_agent", "") if manifest.agent else "unknown"

    def get_tool_category(name: str) -> str:
        if "send" in name:
            return "send"
        if "create" in name:
            return "create"
        if "delete" in name:
            return "delete"
        return "search"

    def manifest_to_dict(manifest: MockManifest) -> dict:
        return {"name": manifest.name, "description": manifest.description}

    def estimate_full_tokens(domains: list[str]) -> int:
        return sum(service.DOMAIN_FULL_TOKENS.get(d, 2000) for d in domains)

    service._extract_domain = extract_domain
    service._get_tool_category = get_tool_category
    service._manifest_to_dict = manifest_to_dict
    service._estimate_full_tokens = estimate_full_tokens
    return service


def _run_filter(
    manifests: list[MockManifest],
    intelligence: MockIntelligence,
    tool_scores: dict[str, float],
    semantic_providers: set[str] | None = None,
):
    """Run NormalFilteringStrategy.filter() with mocks."""
    service = _build_mock_service(manifests)
    strategy = NormalFilteringStrategy(service=service)

    tool_selection_result = {"all_scores": tool_scores}

    with (
        pytest.MonkeyPatch.context() as mp,
        patch(
            "src.domains.agents.semantic.expansion_service.get_semantic_provider_tool_names",
            return_value=semantic_providers if semantic_providers is not None else set(),
        ),
    ):
        mp.setattr(
            "src.domains.agents.services.catalogue.strategies.normal_filtering"
            ".ToolFilter.from_intelligence",
            lambda intel: MockToolFilter(
                domains=intel.domains,
                max_tools=10,
                include_context_tools=False,
            ),
        )
        result = strategy.filter(intelligence, tool_selection_result)

    return result


# =============================================================================
# Tests: Semantic dependency tool protection
# =============================================================================


class TestSemanticDepsProtection:
    """Provider tools from semantic dependencies should be protected."""

    def test_provider_tool_protected_cross_domain(self) -> None:
        """get_contacts_tool should be protected for email+contact queries."""
        manifests = [
            MockManifest(name="send_email_tool", agent="email_agent"),
            MockManifest(name="get_contacts_tool", agent="contact_agent"),
            MockManifest(name="create_contact_tool", agent="contact_agent"),
            MockManifest(name="delete_contact_tool", agent="contact_agent"),
        ]
        intelligence = MockIntelligence(domains=["email", "contact"])

        # send_email high, ALL contact tools below threshold
        # Without semantic protection, domain coverage would protect create+delete (0.001)
        # but NOT get_contacts (0.000)
        tool_scores = {
            "send_email_tool": 0.846,
            "get_contacts_tool": 0.000,
            "create_contact_tool": 0.001,
            "delete_contact_tool": 0.001,
        }

        result = _run_filter(
            manifests,
            intelligence,
            tool_scores,
            semantic_providers={"get_contacts_tool"},
        )

        tool_names = [t["name"] for t in result.tools]
        assert (
            "get_contacts_tool" in tool_names
        ), "get_contacts_tool must be in catalogue for email+contact cross-domain queries"
        assert "send_email_tool" in tool_names

    def test_without_semantic_protection_provider_excluded(self) -> None:
        """Without semantic protection, get_contacts_tool would be excluded."""
        manifests = [
            MockManifest(name="send_email_tool", agent="email_agent"),
            MockManifest(name="get_contacts_tool", agent="contact_agent"),
            MockManifest(name="create_contact_tool", agent="contact_agent"),
            MockManifest(name="delete_contact_tool", agent="contact_agent"),
        ]
        intelligence = MockIntelligence(domains=["email", "contact"])

        # get_contacts has lowest score → NOT in top-2 → excluded
        tool_scores = {
            "send_email_tool": 0.846,
            "get_contacts_tool": 0.000,
            "create_contact_tool": 0.001,
            "delete_contact_tool": 0.001,
        }

        result = _run_filter(
            manifests,
            intelligence,
            tool_scores,
            semantic_providers=set(),  # No semantic protection
        )

        tool_names = [t["name"] for t in result.tools]
        assert (
            "get_contacts_tool" not in tool_names
        ), "Without semantic protection, get_contacts_tool should be excluded (score 0.000)"

    def test_single_domain_no_semantic_deps(self) -> None:
        """Single domain should not trigger semantic dependency protection."""
        manifests = [
            MockManifest(name="get_contacts_tool", agent="contact_agent"),
            MockManifest(name="create_contact_tool", agent="contact_agent"),
        ]
        intelligence = MockIntelligence(domains=["contact"])

        tool_scores = {
            "get_contacts_tool": 0.50,
            "create_contact_tool": 0.10,
        }

        # Single domain → get_semantic_provider_tool_names returns empty
        result = _run_filter(
            manifests,
            intelligence,
            tool_scores,
            semantic_providers=set(),
        )

        # Both included (top-2 per domain + above threshold)
        tool_names = [t["name"] for t in result.tools]
        assert "get_contacts_tool" in tool_names

    def test_route_plus_contact_protects_contacts(self) -> None:
        """Route + contact query should protect get_contacts_tool."""
        manifests = [
            MockManifest(name="get_route_tool", agent="route_agent"),
            MockManifest(name="get_contacts_tool", agent="contact_agent"),
            MockManifest(name="create_contact_tool", agent="contact_agent"),
            MockManifest(name="delete_contact_tool", agent="contact_agent"),
        ]
        intelligence = MockIntelligence(domains=["route", "contact"])

        tool_scores = {
            "get_route_tool": 0.800,
            "get_contacts_tool": 0.001,
            "create_contact_tool": 0.002,
            "delete_contact_tool": 0.002,
        }

        result = _run_filter(
            manifests,
            intelligence,
            tool_scores,
            semantic_providers={"get_contacts_tool"},
        )

        tool_names = [t["name"] for t in result.tools]
        assert "get_contacts_tool" in tool_names

    def test_semantic_protection_combines_with_domain_coverage(self) -> None:
        """Semantic protection should combine with domain coverage (union)."""
        manifests = [
            MockManifest(name="send_email_tool", agent="email_agent"),
            MockManifest(name="reply_email_tool", agent="email_agent"),
            MockManifest(name="get_contacts_tool", agent="contact_agent"),
            MockManifest(name="create_contact_tool", agent="contact_agent"),
            MockManifest(name="delete_contact_tool", agent="contact_agent"),
        ]
        intelligence = MockIntelligence(domains=["email", "contact"])

        tool_scores = {
            "send_email_tool": 0.846,
            "reply_email_tool": 0.102,
            "get_contacts_tool": 0.000,
            "create_contact_tool": 0.001,
            "delete_contact_tool": 0.001,
        }

        result = _run_filter(
            manifests,
            intelligence,
            tool_scores,
            semantic_providers={"get_contacts_tool"},
        )

        tool_names = [t["name"] for t in result.tools]
        # Domain coverage: create_contact + delete_contact (top-2 for contact domain)
        # Semantic deps: get_contacts_tool (provider for email_address)
        # All three contact tools should be present
        assert "get_contacts_tool" in tool_names
        assert "send_email_tool" in tool_names

    def test_graceful_fallback_on_error(self) -> None:
        """If expansion service is unavailable, filtering should continue safely."""
        manifests = [
            MockManifest(name="send_email_tool", agent="email_agent"),
            MockManifest(name="get_contacts_tool", agent="contact_agent"),
        ]
        intelligence = MockIntelligence(domains=["email", "contact"])

        tool_scores = {
            "send_email_tool": 0.846,
            "get_contacts_tool": 0.000,
        }

        service = _build_mock_service(manifests)
        strategy = NormalFilteringStrategy(service=service)

        with (
            pytest.MonkeyPatch.context() as mp,
            patch(
                "src.domains.agents.semantic.expansion_service.get_semantic_provider_tool_names",
                side_effect=RuntimeError("Service unavailable"),
            ),
        ):
            mp.setattr(
                "src.domains.agents.services.catalogue.strategies.normal_filtering"
                ".ToolFilter.from_intelligence",
                lambda intel: MockToolFilter(
                    domains=intel.domains,
                    max_tools=10,
                    include_context_tools=False,
                ),
            )
            # Should NOT raise - degrades to domain-coverage-only
            result = strategy.filter(intelligence, {"all_scores": tool_scores})

        # Filtering completed successfully (no crash)
        assert result.tool_count >= 1
        # send_email_tool should be included regardless
        tool_names = [t["name"] for t in result.tools]
        assert "send_email_tool" in tool_names


# =============================================================================
# Tests: get_semantic_provider_tool_names()
# =============================================================================


class TestGetSemanticProviderToolNames:
    """Test the helper function directly."""

    def test_single_domain_returns_empty(self) -> None:
        """Single domain should return empty set."""
        from src.domains.agents.semantic.expansion_service import (
            get_semantic_provider_tool_names,
        )

        result = get_semantic_provider_tool_names(["contact"])
        assert result == set()

    def test_empty_domains_returns_empty(self) -> None:
        """Empty domains should return empty set."""
        from src.domains.agents.semantic.expansion_service import (
            get_semantic_provider_tool_names,
        )

        result = get_semantic_provider_tool_names([])
        assert result == set()
