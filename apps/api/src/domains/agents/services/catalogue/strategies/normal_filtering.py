"""
Normal Filtering Strategy - Standard catalogue filtering.

This strategy applies intelligent filtering based on query analysis,
dramatically reducing token consumption while maintaining functionality.

Filtering logic:
1. Filter by domains (only include requested domains)
2. Filter by categories (search, detail, write, etc.)
3. Filter by semantic scores (exclude low-scoring tools)
4. Ensure domain coverage (at least one tool per domain)
5. Respect max_tools limit

Token savings:
- FULL contacts catalogue: ~5500 tokens
- FILTERED (search only): ~200 tokens
- Reduction: 96%

Architecture:
- Delegates to service helpers for manifest processing
- Uses ToolFilter from QueryIntelligence for filtering criteria
"""

from typing import TYPE_CHECKING, Any

from src.domains.agents.analysis.query_intelligence import ToolFilter
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import planner_catalogue_size_tools

if TYPE_CHECKING:
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.services.smart_catalogue_service import (
        FilteredCatalogue,
        SmartCatalogueService,
    )

logger = get_logger(__name__)

# Number of tools to protect per domain for coverage
# FIX 2026-02-06: Increased from 1 to 2 for better alternative coverage
_DOMAIN_COVERAGE_TOP_N = 2


class NormalFilteringStrategy:
    """
    Standard catalogue filtering strategy.

    Applies intelligent filtering to reduce token consumption while
    ensuring all necessary tools are available for the LLM.
    """

    def __init__(self, service: "SmartCatalogueService"):
        """
        Initialize with service reference for helper methods.

        Args:
            service: SmartCatalogueService instance for accessing helpers
        """
        self.service = service

    def can_handle(
        self,
        intelligence: "QueryIntelligence",
        panic_mode: bool = False,
    ) -> bool:
        """
        Check if normal filtering should be used.

        Normal filtering is used when panic_mode is False.

        Args:
            intelligence: QueryIntelligence with user intent
            panic_mode: Whether panic mode is requested

        Returns:
            True if not panic_mode, False otherwise
        """
        return not panic_mode

    def filter(
        self,
        intelligence: "QueryIntelligence",
        tool_selection_result: dict | None = None,
    ) -> "FilteredCatalogue":
        """
        Execute normal filtering strategy.

        Applies intelligent filtering based on:
        - Domains (from intelligence)
        - Categories (from intent)
        - Semantic scores (from tool_selection_result)
        - Max tools limit
        - Domain coverage (at least one tool per domain)

        Args:
            intelligence: QueryIntelligence with user intent
            tool_selection_result: Semantic tool scores from router

        Returns:
            FilteredCatalogue with filtered tools
        """
        from src.core.config import get_settings

        settings = get_settings()
        threshold = settings.v3_tool_calibrated_primary_min

        # Build ToolFilter from intelligence
        tool_filter = ToolFilter.from_intelligence(intelligence)

        all_manifests = self.service.registry.list_tool_manifests()

        # Inject user MCP tool manifests (evolution F2.1)
        # F2.2: Per-server domains are detected by the LLM (no force-include needed)
        from src.core.context import user_mcp_tools_ctx

        user_ctx = user_mcp_tools_ctx.get()
        if user_ctx and user_ctx.tool_manifests:
            all_manifests = list(all_manifests) + user_ctx.tool_manifests

        # Extract semantic scores for filtering (exclude low-scoring tools)
        tool_scores: dict[str, float] = {}
        excluded_tools: list[str] = []
        kept_for_foreach: list[str] = []
        if tool_selection_result and "all_scores" in tool_selection_result:
            tool_scores = tool_selection_result["all_scores"]

        # FIX 2026-01-29: Bypass semantic filtering for mutation tools when FOR_EACH pattern
        # When user wants "search X AND apply/delete/send to each", we MUST include mutation tools
        # even if their semantic score is low (the query is diluted by the search part)
        bypass_mutation_filtering = (
            intelligence.for_each_detected and intelligence.is_mutation_intent
        )
        mutation_categories = {"update", "delete", "send", "create"}

        # FIX 2026-02-06: Pre-pass to identify top-N tools per domain for domain coverage
        # This ensures cross-domain queries have alternative tools available per domain,
        # even if those tools have low semantic scores.
        # Example: "contact details" needs both get_contacts AND get_contact_details
        best_tools_per_domain: dict[str, list[tuple[str, float]]] = {}
        for manifest in all_manifests:
            tool_domain = self.service._extract_domain(manifest)
            if tool_domain not in tool_filter.domains:
                continue
            score = tool_scores.get(manifest.name, 0.0)

            if tool_domain not in best_tools_per_domain:
                best_tools_per_domain[tool_domain] = []

            best_tools_per_domain[tool_domain].append((manifest.name, score))

        # Sort by score and keep top-N per domain
        for domain in best_tools_per_domain:
            best_tools_per_domain[domain] = sorted(
                best_tools_per_domain[domain],
                key=lambda x: x[1],
                reverse=True,
            )[:_DOMAIN_COVERAGE_TOP_N]

        # Flatten to set of protected tools
        domain_protected_tools = {
            name for tools in best_tools_per_domain.values() for name, _ in tools
        }

        # FIX 2026-02-06: Protect tools that provide cross-domain semantic types
        # Without this, "send email to Marie" would exclude get_contacts_tool (score 0.000)
        # even though it's needed to resolve the recipient's email address.
        # The semantic dependency hints tell the planner to use these tools,
        # so the catalogue must include them.
        kept_for_semantic_deps: list[str] = []
        try:
            from src.domains.agents.semantic.expansion_service import (
                get_semantic_provider_tool_names,
            )

            semantic_provider_tools = get_semantic_provider_tool_names(tool_filter.domains)
            if semantic_provider_tools:
                new_providers = semantic_provider_tools - domain_protected_tools
                if new_providers:
                    kept_for_semantic_deps = [
                        f"{name}({tool_scores.get(name, 0.0):.3f})" for name in new_providers
                    ]
                domain_protected_tools = domain_protected_tools | semantic_provider_tools
        except Exception:
            # Fail-safe: if semantic expansion service is unavailable,
            # fall back to domain-coverage-only protection
            logger.debug(
                "semantic_provider_tools_fallback",
                message="Semantic provider tool lookup failed, using domain coverage only",
            )

        # First pass: collect tools per domain
        # This ensures cross-domain queries have all necessary tools
        tools_by_domain: dict[str, list[tuple[dict, str]]] = {d: [] for d in tool_filter.domains}
        if tool_filter.include_context_tools:
            tools_by_domain["context"] = []
        kept_for_domain_coverage: list[str] = []

        for manifest in all_manifests:
            tool_domain = self.service._extract_domain(manifest)
            if tool_domain not in tools_by_domain:
                continue

            # Check category match (if categories specified)
            tool_category = self.service._get_tool_category(manifest.name)
            if tool_filter.categories and tool_category not in tool_filter.categories:
                continue

            # FIX 2026-01-25: Exclude tools with low semantic scores
            # This prevents the LLM from choosing simpler but incorrect tools
            # Example: get_current_weather vs get_weather_forecast for calendar events
            if tool_scores and manifest.name in tool_scores:
                score = tool_scores[manifest.name]
                if score < threshold:
                    # FIX 2026-01-30: Keep tools protected by domain coverage
                    # Cross-domain queries need at least one tool per domain
                    if manifest.name in domain_protected_tools:
                        kept_for_domain_coverage.append(f"{manifest.name}({score:.3f})")
                    # FIX 2026-01-29: Keep mutation tools when FOR_EACH + mutation detected
                    elif bypass_mutation_filtering and tool_category in mutation_categories:
                        kept_for_foreach.append(f"{manifest.name}({score:.3f})")
                    else:
                        excluded_tools.append(f"{manifest.name}({score:.3f})")
                        continue

            tools_by_domain[tool_domain].append(
                (self.service._manifest_to_dict(manifest), tool_category)
            )

        if excluded_tools:
            logger.info(
                "catalogue_tools_excluded_by_score",
                excluded=excluded_tools,
                threshold=threshold,
            )

        if kept_for_foreach:
            logger.info(
                "catalogue_tools_kept_for_foreach_mutation",
                kept=kept_for_foreach,
                threshold=threshold,
                for_each_detected=intelligence.for_each_detected,
                is_mutation_intent=intelligence.is_mutation_intent,
            )

        if kept_for_domain_coverage:
            logger.info(
                "catalogue_tools_kept_for_domain_coverage",
                kept=kept_for_domain_coverage,
                threshold=threshold,
                domains=tool_filter.domains,
            )

        if kept_for_semantic_deps:
            logger.info(
                "catalogue_tools_kept_for_semantic_deps",
                kept=kept_for_semantic_deps,
                threshold=threshold,
                domains=tool_filter.domains,
            )

        # Second pass: build filtered list ensuring domain coverage
        filtered_tools: list[dict[str, Any]] = []
        domains_included = set()
        categories_included = set()

        # First, add at least one tool per domain (domain coverage)
        for domain, tools in tools_by_domain.items():
            if tools and len(filtered_tools) < tool_filter.max_tools:
                tool_dict, tool_category = tools[0]
                filtered_tools.append(tool_dict)
                domains_included.add(domain)
                categories_included.add(tool_category)

        # Then, fill remaining slots with additional tools
        for _domain, tools in tools_by_domain.items():
            for tool_dict, tool_category in tools[1:]:  # Skip first (already added)
                if len(filtered_tools) >= tool_filter.max_tools:
                    break
                filtered_tools.append(tool_dict)
                categories_included.add(tool_category)

        # F6: Force-include sub-agent delegation tool (transversal, always available)
        # This tool bypasses domain/score filtering — the planner decides autonomously.
        if getattr(tool_filter, "include_sub_agent_tools", False):
            existing_names = {t["name"] for t in filtered_tools}
            if "delegate_to_sub_agent_tool" not in existing_names:
                for manifest in all_manifests:
                    if manifest.name == "delegate_to_sub_agent_tool":
                        filtered_tools.append(self.service._manifest_to_dict(manifest))
                        domains_included.add("sub_agent")
                        break

        # Calculate token estimate
        token_estimate = sum(
            self.service.TOKEN_ESTIMATES.get(self.service._get_tool_category(t["name"]), 200)
            for t in filtered_tools
        )

        # Update metrics
        self.service._metrics.original_size = len(all_manifests)
        self.service._metrics.filtered_size = len(filtered_tools)
        self.service._metrics.tokens_saved = (
            self.service._estimate_full_tokens(tool_filter.domains) - token_estimate
        )
        self.service._metrics.filter_reason = (
            f"Intent: {intelligence.immediate_intent}, Domains: {intelligence.domains}"
        )

        # Observe catalogue sizes for Prometheus recording rules
        domains_label = "+".join(sorted(domains_included)) if domains_included else "all"
        planner_catalogue_size_tools.labels(
            filtering_applied="false", domains_loaded="all"
        ).observe(len(all_manifests))
        planner_catalogue_size_tools.labels(
            filtering_applied="true", domains_loaded=domains_label
        ).observe(len(filtered_tools))

        logger.debug(
            "catalogue_filtered",
            original=len(all_manifests),
            filtered=len(filtered_tools),
            domains=list(domains_included),
            categories=list(categories_included),
            tokens_saved=self.service._metrics.tokens_saved,
        )

        from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue

        return FilteredCatalogue(
            tools=filtered_tools,
            tool_count=len(filtered_tools),
            token_estimate=token_estimate,
            domains_included=list(domains_included),
            categories_included=list(categories_included),
        )


__all__ = [
    "NormalFilteringStrategy",
]
