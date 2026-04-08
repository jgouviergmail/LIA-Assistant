"""
SmartCatalogueService - Intelligent tool catalogue filtering.

Architecture v3 - Intelligence, Autonomy, Relevance.

This service filters the tool catalogue based on query analysis,
dramatically reducing token consumption while maintaining functionality.

KEY PRINCIPLE: Inject ONLY the tools that are needed.

Token savings:
- FULL contacts catalogue: ~5500 tokens
- FILTERED (search only): ~200 tokens
- Reduction: 96%

PANIC MODE (Anti False-Negative):
If the planner fails with filtered catalogue, we can request
an expanded catalogue for a second attempt.
→ Avoids blocking creative cases the LLM could have solved.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.core.constants import (
    V3_CATALOGUE_DOMAIN_FULL_TOKENS,
    V3_CATALOGUE_TOKEN_ESTIMATES,
)
from src.core.context import panic_mode_used
from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.registry import AgentRegistry
    from src.domains.agents.registry.manifest_builder import ToolManifest

logger = get_logger(__name__)


@dataclass
class FilteredCatalogue:
    """Filtered catalogue ready for LLM prompt injection."""

    tools: list[dict[str, Any]]
    tool_count: int
    token_estimate: int
    domains_included: list[str]
    categories_included: list[str]
    is_panic_mode: bool = False

    def to_prompt_string(self) -> str:
        """Format for LLM prompt injection (compact JSON to minimize tokens)."""
        import json

        return json.dumps(self.tools, separators=(",", ":"), ensure_ascii=False)

    def get_tool_names(self) -> list[str]:
        """Get list of tool names in catalogue."""
        return [t["name"] for t in self.tools]


@dataclass
class CatalogueMetrics:
    """Metrics for catalogue filtering."""

    original_size: int = 0
    filtered_size: int = 0
    tokens_saved: int = 0
    panic_mode_used: bool = False
    filter_reason: str = ""


class SmartCatalogueService:
    """
    Intelligent catalogue filtering service.

    KEY PRINCIPLE: Inject ONLY the tools that are needed.

    Filtering strategies:
    1. By INTENT: search → search_tools, detail → get_tools
    2. By DOMAIN: contacts, emails, etc.
    3. By CONTEXT: context tools if reference turn

    PANIC MODE (Anti False-Negative):
    If the planner fails with the filtered catalogue, we can
    request an expanded catalogue for ONE retry.
    → Avoids false negatives where filtering was too aggressive.
    → Gives LLM a chance to be creative with more tools.

    Usage:
        service = get_smart_catalogue_service()
        filtered = service.filter_for_intelligence(intelligence)
        # If planner fails:
        expanded = service.filter_for_intelligence(intelligence, panic_mode=True)
    """

    # Centralized token estimates (from constants.py)
    TOKEN_ESTIMATES = V3_CATALOGUE_TOKEN_ESTIMATES
    DOMAIN_FULL_TOKENS = V3_CATALOGUE_DOMAIN_FULL_TOKENS

    def __init__(self, registry: "AgentRegistry"):
        self.registry = registry
        self._metrics = CatalogueMetrics()

        # Strategy Pattern: Filtering strategies
        from src.domains.agents.services.catalogue.strategies import (
            NormalFilteringStrategy,
            PanicFilteringStrategy,
        )

        self.normal_strategy = NormalFilteringStrategy(service=self)
        self.panic_strategy = PanicFilteringStrategy(
            service=self,
            normal_strategy=self.normal_strategy,
        )

    def filter_for_intelligence(
        self,
        intelligence: QueryIntelligence,
        panic_mode: bool = False,
        tool_selection_result: dict | None = None,
    ) -> FilteredCatalogue:
        """
        Filter catalogue based on query intelligence.

        Strategy Pattern: Delegates to NormalFilteringStrategy or PanicFilteringStrategy.

        Args:
            intelligence: Query intelligence result
            panic_mode: If True, return expanded catalogue (all tools for detected domains)
                       Used when filtered planning fails.
            tool_selection_result: Semantic tool scores from router (excludes low-scoring tools)

        Returns:
            FilteredCatalogue ready for prompt injection.
        """
        # Strategy selection: panic mode vs normal
        if self.panic_strategy.can_handle(intelligence, panic_mode):
            return self.panic_strategy.filter(intelligence, tool_selection_result)

        # Default to normal filtering
        return self.normal_strategy.filter(intelligence, tool_selection_result)

    def reset_panic_mode(self) -> None:
        """Reset panic mode flag for new request."""
        panic_mode_used.set(False)  # ContextVar per-request isolation
        self._metrics = CatalogueMetrics()

    def _extract_domain(self, manifest: "ToolManifest") -> str:
        """Extract domain from tool manifest."""
        # Try agent field first
        if hasattr(manifest, "agent") and manifest.agent:
            return manifest.agent.removesuffix("_agent")

        # Fallback to name prefix
        name = manifest.name.lower()
        for domain in self.DOMAIN_FULL_TOKENS.keys():
            if name.startswith(domain) or domain in name:
                return domain

        return "unknown"

    def _get_tool_category(self, tool_name: str) -> str:
        """
        Extract category from tool name.

        Updated 2026-01: Unified architecture - all data retrieval (get/search/list/detail)
        is now unified under "search" category.
        """
        name_lower = tool_name.lower()

        # Action tools (check first to avoid confusion with "get_")
        if "create" in name_lower or "add_" in name_lower:
            return "create"
        elif (
            "update" in name_lower
            or "modify" in name_lower
            or "edit" in name_lower
            or "apply" in name_lower
        ):
            return "update"
        elif "delete" in name_lower or "remove" in name_lower:
            return "delete"
        elif "send" in name_lower or "reply" in name_lower or "forward" in name_lower:
            return "send"

        # Unified data retrieval category (2026-01: search/list/detail/get → "search")
        elif (
            "search" in name_lower
            or "find" in name_lower
            or "list" in name_lower
            or "detail" in name_lower
            or name_lower.startswith("get_")
        ):
            return "search"

        return "utility"

    def _manifest_to_dict(self, manifest: "ToolManifest") -> dict:
        """
        Convert manifest to COMPACT dict for prompt injection.

        TOKEN OPTIMIZATION (2026-01):
        - Old format: ~900 tokens per tool (verbose outputs, descriptions)
        - New format: ~200 tokens per tool (compact outputs, minimal descriptions)
        - Savings: ~75% per tool

        Compact format:
        1. Parameters: Only name, type, required. Description only if required=True.
        2. Outputs: Compact string format "path:type" or "path:type:semantic_type"
        3. No reference_examples (redundant with outputs paths)
        """
        # Compact parameters: only essential info
        compact_params = []
        for p in manifest.parameters:
            param = {
                "name": p.name,
                "type": p.type,
                "required": p.required,
            }
            # Include description for required params, params with semantic_type, pattern, or ID arrays
            # FIX 2026-01-25: semantic_type params need descriptions for cross-domain matching
            # Example: date param in get_weather_forecast_tool explains "use event's start_datetime"
            # Without this, LLM can't distinguish get_current_weather vs get_weather_forecast
            # FIX 2026-01-30: pattern params need descriptions to explain format requirements
            # Example: resource_name description "Single contact ID (people/c...)" clarifies format
            # FIX 2026-01-30: ID array params need descriptions to prevent name/ID confusion
            # Example: resource_names must explain these are IDs not names
            has_pattern = hasattr(p, "constraints") and any(
                c.kind == "pattern" for c in (p.constraints or [])
            )
            is_id_array = p.type == "array" and (
                p.name.endswith("_names") or p.name.endswith("_ids") or "id" in p.name.lower()
            )
            if p.description and (
                p.required
                or (hasattr(p, "semantic_type") and p.semantic_type)
                or has_pattern
                or is_id_array
            ):
                param["description"] = p.description
            # FIX 2026-01-11: Include semantic_type for cross-domain dependency detection
            # This enables LLM to match parameters like "to" (semantic_type: email_address)
            # with outputs from other tools that provide email_address type.
            # Example: send_email_tool(to) needs email_address → get_contacts_tool provides it
            if hasattr(p, "semantic_type") and p.semantic_type:
                param["semantic_type"] = p.semantic_type
            # FIX 2026-01-30: Include pattern constraints for ID format validation
            # This tells LLM that resource_name MUST match "^people/" format,
            # preventing it from using names like "Jane Smith" instead of IDs.
            # Example: get_contacts_tool(resource_name) expects "people/c123", not a name
            if hasattr(p, "constraints") and p.constraints:
                for c in p.constraints:
                    if c.kind == "pattern":
                        param["pattern"] = c.value
                        break  # Only include first pattern constraint
            # FIX 2026-03-05: Include JSON Schema for complex types (array, object)
            # so the LLM sees the internal structure (items, nested properties, enums).
            # Critical for MCP tools with structured inputs (e.g., Excalidraw elements).
            schema_val = getattr(p, "schema", None)
            if schema_val and isinstance(schema_val, dict):
                param["schema"] = schema_val
            compact_params.append(param)

        # Get result_key for $steps references
        # Priority: manifest.context_key (actual data key) > domain taxonomy
        # This handles tools like get_current_location_tool where:
        # - domain = "place" (from place_agent) → taxonomy result_key = "places"
        # - But actual data is under context_key = "locations"
        from src.domains.agents.registry.domain_taxonomy import get_result_key

        domain = self._extract_domain(manifest)
        result_key = manifest.context_key or get_result_key(domain)

        result = {
            "name": manifest.name,
            "description": manifest.description,
            "parameters": compact_params,
            "agent": manifest.agent if hasattr(manifest, "agent") else None,
            "result_key": result_key,  # Canonical key for $steps.STEP_ID.{result_key}
        }

        # Compact outputs: "path:type" or "path:type:semantic_type" for cross-domain
        # This tells LLM what paths to reference without verbose descriptions
        if hasattr(manifest, "outputs") and manifest.outputs:
            compact_outputs = []
            for o in manifest.outputs:
                semantic = getattr(o, "semantic_type", None)
                if semantic:
                    # Cross-domain output: include semantic type for dependency detection
                    compact_outputs.append(f"{o.path}:{o.type}:{semantic}")
                else:
                    # Regular output: just path and type
                    compact_outputs.append(f"{o.path}:{o.type}")
            result["outputs"] = compact_outputs

        # NOTE: reference_examples removed - LLM can infer syntax from outputs paths

        return result

    def _estimate_full_tokens(self, domains: list[str]) -> int:
        """Estimate tokens for full catalogue (for comparison)."""
        return sum(self.DOMAIN_FULL_TOKENS.get(d, 3000) for d in domains)

    def get_metrics(self) -> CatalogueMetrics:
        """Get current filtering metrics."""
        return self._metrics


# Singleton
_smart_catalogue: SmartCatalogueService | None = None


def get_smart_catalogue_service() -> SmartCatalogueService:
    """Get singleton SmartCatalogueService instance."""
    global _smart_catalogue
    if _smart_catalogue is None:
        from src.domains.agents.registry import get_global_registry

        _smart_catalogue = SmartCatalogueService(get_global_registry())
    return _smart_catalogue
