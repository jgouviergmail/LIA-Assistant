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

from dataclasses import replace

import pytest
from pydantic import JsonValue

from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
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


@pytest.mark.parametrize("aggregates", [None, True, 17, 1.5, "brave", {"brave": True}, [{}]])
def test_malformed_metadata_does_not_remove_unlisted_domains(
    monkeypatch: pytest.MonkeyPatch, aggregates: JsonValue
) -> None:
    """Generic JSON metadata cannot become a character/key collection or crash routing."""
    config = replace(
        DOMAIN_REGISTRY["web_search"],
        metadata={"is_meta_domain": True, "aggregates": aggregates},
    )
    monkeypatch.setitem(DOMAIN_REGISTRY, "web_search", config)
    domains = ["web_search", "brave", "b", "contact"]
    assert _deduplicate_meta_domains(domains) == domains


def test_mixed_metadata_only_aggregates_explicit_string_domains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = replace(
        DOMAIN_REGISTRY["web_search"],
        metadata={"is_meta_domain": True, "aggregates": ["brave", {}, 17, False]},
    )
    monkeypatch.setitem(DOMAIN_REGISTRY, "web_search", config)
    assert _deduplicate_meta_domains(["web_search", "brave", "contact"]) == [
        "web_search",
        "contact",
    ]
