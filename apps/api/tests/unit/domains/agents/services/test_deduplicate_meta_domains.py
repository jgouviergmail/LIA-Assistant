"""
Unit tests for _deduplicate_meta_domains.

Tests coverage:
- Meta-domain present removes aggregated domains
- No meta-domain returns unchanged list
- Empty list returns empty list
- Order preserved after filtering
- Non-aggregated domains kept alongside meta-domain
- Only aggregated domains removed (partial overlap)

Target: _deduplicate_meta_domains in
    domains/agents/services/query_analyzer_service.py
"""

from __future__ import annotations

from src.domains.agents.services.query_analyzer_service import (
    _deduplicate_meta_domains,
)


class TestDeduplicateMetaDomains:
    """Tests for meta-domain deduplication logic."""

    def test_meta_domain_removes_aggregated(self) -> None:
        """web_search should suppress brave, perplexity, wikipedia."""
        result = _deduplicate_meta_domains(["web_search", "brave", "perplexity"])
        assert result == ["web_search"]

    def test_no_meta_domain_returns_unchanged(self) -> None:
        """Without a meta-domain, the list should be returned as-is."""
        result = _deduplicate_meta_domains(["brave", "perplexity"])
        assert result == ["brave", "perplexity"]

    def test_empty_list(self) -> None:
        """Empty input should return empty output."""
        result = _deduplicate_meta_domains([])
        assert result == []

    def test_order_preserved(self) -> None:
        """Non-aggregated domains should retain their original order."""
        result = _deduplicate_meta_domains(["contact", "web_search", "event", "brave"])
        assert result == ["contact", "web_search", "event"]

    def test_non_aggregated_domains_kept(self) -> None:
        """Domains not in the meta-domain's aggregates should be kept."""
        result = _deduplicate_meta_domains(["web_search", "contact", "brave", "event"])
        assert result == ["web_search", "contact", "event"]

    def test_meta_domain_alone(self) -> None:
        """Meta-domain without any aggregated domains present should be unchanged."""
        result = _deduplicate_meta_domains(["web_search", "contact"])
        assert result == ["web_search", "contact"]

    def test_all_three_aggregated_removed(self) -> None:
        """All three aggregated domains (brave, perplexity, wikipedia) removed."""
        result = _deduplicate_meta_domains(["web_search", "brave", "perplexity", "wikipedia"])
        assert result == ["web_search"]

    def test_single_non_meta_domain(self) -> None:
        """Single domain that is not a meta-domain should pass through."""
        result = _deduplicate_meta_domains(["contact"])
        assert result == ["contact"]
