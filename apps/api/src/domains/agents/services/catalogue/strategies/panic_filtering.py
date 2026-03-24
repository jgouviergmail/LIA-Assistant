"""
Panic Filtering Strategy - Expanded catalogue for failed planning.

This strategy returns ALL tools for detected domains when normal filtering
results in planning failure. This is an anti-false-negative mechanism.

Use case:
When the planner fails with filtered catalogue, retry ONCE with expanded
catalogue to give the LLM more options for creative solutions.

Trade-off:
- More tokens (~2000 instead of ~200)
- But avoids false negatives where LLM could have been creative
- ONE TIME ONLY per request (prevents infinite loops)

Architecture:
- Creates expanded ToolFilter (all categories, higher limit)
- Delegates to NormalFilteringStrategy with expanded filter
- Marks result as panic_mode for debugging
"""

from typing import TYPE_CHECKING

from src.core.context import panic_mode_used
from src.domains.agents.analysis.query_intelligence import ToolFilter
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import planner_catalogue_size_tools

if TYPE_CHECKING:
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.services.catalogue.strategies.normal_filtering import (
        NormalFilteringStrategy,
    )
    from src.domains.agents.services.smart_catalogue_service import (
        FilteredCatalogue,
        SmartCatalogueService,
    )

logger = get_logger(__name__)


class PanicFilteringStrategy:
    """
    Panic mode catalogue filtering strategy.

    Returns expanded catalogue when normal filtering fails.
    ONE TIME ONLY per request to prevent infinite loops.
    """

    def __init__(
        self,
        service: "SmartCatalogueService",
        normal_strategy: "NormalFilteringStrategy",
    ):
        """
        Initialize with service and normal strategy reference.

        Args:
            service: SmartCatalogueService instance for state management
            normal_strategy: NormalFilteringStrategy to delegate filtering to
        """
        self.service = service
        self.normal_strategy = normal_strategy

    def can_handle(
        self,
        intelligence: "QueryIntelligence",
        panic_mode: bool = False,
    ) -> bool:
        """
        Check if panic filtering should be used.

        Panic filtering is used when:
        1. panic_mode is True
        2. Panic mode has NOT been used yet (one time only)

        Args:
            intelligence: QueryIntelligence with user intent
            panic_mode: Whether panic mode is requested

        Returns:
            True if panic_mode requested and not used yet, False otherwise
        """
        return panic_mode and not panic_mode_used.get()

    def filter(
        self,
        intelligence: "QueryIntelligence",
        tool_selection_result: dict | None = None,
    ) -> "FilteredCatalogue":
        """
        Execute panic filtering strategy.

        Returns ALL tools for detected domains with:
        - All categories included (no category filtering)
        - Higher max_tools limit (15 instead of 5)
        - Context tools included

        ONE TIME ONLY: If already used, falls back to normal filtering
        to prevent infinite loops.

        Args:
            intelligence: QueryIntelligence with user intent
            tool_selection_result: Semantic tool scores (unused in panic mode)

        Returns:
            FilteredCatalogue with expanded tools, marked as panic_mode
        """
        from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue

        # Check if already used (infinite loop prevention)
        if panic_mode_used.get():
            logger.warning(
                "panic_mode_already_used",
                domains=intelligence.domains,
            )
            # Fall back to normal filtering
            return self.normal_strategy.filter(intelligence, tool_selection_result)

        # Mark panic mode as used (ContextVar per-request isolation)
        panic_mode_used.set(True)
        self.service._metrics.panic_mode_used = True

        logger.info(
            "panic_mode_activated",
            domains=intelligence.domains,
            original_intent=intelligence.immediate_intent,
        )

        # Create expanded filter: all categories, higher limit
        # Create temporary intelligence with expanded ToolFilter

        expanded_filter = ToolFilter(
            domains=intelligence.domains,
            categories=[],  # Empty = all categories
            max_tools=15,  # Higher limit (vs 5 for normal)
            include_context_tools=True,
        )

        # Build filtered catalogue using expanded filter
        # KISS: Replicate the filtering logic from normal strategy
        # but use expanded_filter instead of building from intelligence

        from src.core.context import get_request_tool_manifests, user_mcp_tools_ctx

        all_manifests = get_request_tool_manifests()

        # Panic mode: force-include ALL user MCP domains for safety net
        user_ctx = user_mcp_tools_ctx.get()
        if user_ctx and user_ctx.server_domains:
            for slug in user_ctx.server_domains.values():
                if slug not in expanded_filter.domains:
                    expanded_filter.domains = [*expanded_filter.domains, slug]

        # Collect tools for expanded filter
        tools_by_domain: dict[str, list[tuple[dict, str]]] = {
            d: [] for d in expanded_filter.domains
        }
        if expanded_filter.include_context_tools:
            tools_by_domain["context"] = []

        for manifest in all_manifests:
            tool_domain = self.service._extract_domain(manifest)
            if tool_domain not in tools_by_domain:
                continue

            # NO category filtering in panic mode (all categories allowed)
            tool_category = self.service._get_tool_category(manifest.name)

            # FIX 2026-02-06: NO threshold filtering in panic mode
            # The purpose of panic mode is to provide ALL tools when normal filtering
            # was too aggressive. Applying a threshold defeats this purpose and can
            # result in 0 tools being returned, blocking the user completely.
            # Trade-off: More tokens (~2000) but guarantees tools are available.

            tools_by_domain[tool_domain].append(
                (self.service._manifest_to_dict(manifest), tool_category)
            )

        # Build filtered list with expanded limit
        filtered_tools: list[dict] = []
        domains_included = set()
        categories_included = set()

        # Add at least one tool per domain
        for domain, tools in tools_by_domain.items():
            if tools and len(filtered_tools) < expanded_filter.max_tools:
                tool_dict, tool_category = tools[0]
                filtered_tools.append(tool_dict)
                domains_included.add(domain)
                categories_included.add(tool_category)

        # Fill remaining slots
        for _domain, tools in tools_by_domain.items():
            for tool_dict, tool_category in tools[1:]:
                if len(filtered_tools) >= expanded_filter.max_tools:
                    break
                filtered_tools.append(tool_dict)
                categories_included.add(tool_category)

        # Calculate token estimate
        token_estimate = sum(
            self.service.TOKEN_ESTIMATES.get(self.service._get_tool_category(t["name"]), 200)
            for t in filtered_tools
        )

        # Observe panic catalogue size for Prometheus recording rules
        domains_label = "+".join(sorted(domains_included)) if domains_included else "all"
        planner_catalogue_size_tools.labels(
            filtering_applied="true", domains_loaded=domains_label
        ).observe(len(filtered_tools))

        logger.debug(
            "panic_mode_catalogue_built",
            tool_count=len(filtered_tools),
            domains=list(domains_included),
            token_estimate=token_estimate,
        )

        # Mark as panic mode in result
        return FilteredCatalogue(
            tools=filtered_tools,
            tool_count=len(filtered_tools),
            token_estimate=token_estimate,
            domains_included=list(domains_included),
            categories_included=["ALL_PANIC_MODE"],  # Marker
            is_panic_mode=True,
        )


__all__ = [
    "PanicFilteringStrategy",
]
