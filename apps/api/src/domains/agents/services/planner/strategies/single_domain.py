"""
Single Domain Strategy - LLM-based planning for single domain queries.

This strategy handles queries that involve only one domain and require
LLM intelligence to generate an execution plan from a filtered catalogue.

Examples:
- "Find my contacts named John"
- "List upcoming events this week"
- "Search for files about project alpha"

Architecture:
- Uses filtered catalogue (~200-500 tokens instead of ~5500)
- Single LLM call with domain-specific tools
- Builds prompt with temporal context and resolved references
- Parses JSON response into ExecutionPlan

Note: This strategy delegates to SmartPlannerService helper methods for
prompt building and plan construction to avoid duplication during refactoring.
Future: Extract these helpers into shared modules.
"""

from typing import TYPE_CHECKING, Any

from src.domains.agents.services.planner.planning_result import PlanningResult
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan
    from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue

logger = get_logger(__name__)


class SingleDomainStrategy:
    """
    Planning strategy for single domain queries using LLM.

    Requires a filtered catalogue and builds a plan using LLM intelligence.
    """

    def __init__(self, service: "Any" = None):
        """
        Initialize with optional service reference.

        Args:
            service: SmartPlannerService instance for delegating helper methods
        """
        self.service = service

    async def can_handle(
        self,
        intelligence: "QueryIntelligence",
        catalogue: "FilteredCatalogue | None" = None,
    ) -> bool:
        """
        Check if this strategy can handle the query.

        Single domain strategy handles queries with exactly ONE domain.
        This is checked AFTER bypass strategies have been tried.

        Args:
            intelligence: QueryIntelligence with user intent
            catalogue: Filtered catalogue (must be present)

        Returns:
            True if exactly one domain, False otherwise
        """
        if not catalogue:
            return False

        # Must be exactly 1 domain
        return len(intelligence.domains) == 1

    async def plan(
        self,
        intelligence: "QueryIntelligence",
        config: "RunnableConfig",
        catalogue: "FilteredCatalogue | None" = None,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "ExecutionPlan | None" = None,
        journal_context: str = "",
    ) -> PlanningResult:
        """
        Plan for single domain query using LLM.

        Uses filtered catalogue (~200-500 tokens instead of ~5500).

        Args:
            intelligence: QueryIntelligence with user intent
            config: RunnableConfig for LangGraph
            catalogue: Filtered catalogue with domain-specific tools
            validation_feedback: Feedback from semantic validation
            clarification_response: User's clarification response
            clarification_field: Field that was clarified
            existing_plan: Previous plan (for replanning)
            journal_context: Per-request journal snippet (explicit parameter —
                the service is a singleton, instance state leaks across users)

        Returns:
            PlanningResult with LLM-generated plan
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.domains.agents.utils.json_parser import extract_json_from_llm_response
        from src.infrastructure.llm import get_llm

        if not catalogue:
            return PlanningResult(
                success=False,
                plan=None,
                error="No catalogue provided for single domain planning",
            )

        # Delegate to service for prompt building (complex logic)
        if not self.service:
            return PlanningResult(
                success=False,
                plan=None,
                error="Service not injected for single domain planning",
            )

        # Build prompt with temporal context (async for learned patterns)
        prompt = await self.service._build_prompt(
            intelligence,
            catalogue,
            config,
            validation_feedback,
            clarification_response,
            clarification_field,
            existing_plan,
            journal_context=journal_context,
        )

        from src.domains.agents.services.planner.human_message import (
            build_planner_human_message,
        )

        llm = get_llm("planner")
        # Original query (user's language) + resolved facts in the HUMAN message
        # (see build_planner_human_message — facts in the system context were
        # demonstrably ignored; this strategy is the runtime path, keep it in
        # sync with the service's fallback sites).
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(
                content=build_planner_human_message(
                    intelligence,
                    existing_plan=existing_plan if clarification_response is None else None,
                    validation_feedback=validation_feedback,
                )
            ),
        ]

        # Extract CONTEXT section from prompt for debugging
        _ctx_start = prompt.find("CONTEXT FROM PREVIOUS RESULTS:")
        _ctx_end = prompt.find("RESOLVED REFERENCES:")
        _ctx_preview = prompt[_ctx_start:_ctx_end][:500] if _ctx_start > 0 else "(no context)"

        logger.debug(
            "planner_prompt_debug",
            prompt_length=len(prompt),
            has_mcp_reference="MCP TOOL FORMAT REFERENCE" in prompt,
            context_preview=_ctx_preview,
        )

        try:
            from src.infrastructure.llm.invoke_helpers import (
                enrich_config_with_node_metadata,
            )

            config = enrich_config_with_node_metadata(config, "planner_single_domain")
            response = await llm.ainvoke(messages, config=config)
            response_text = response.text.strip()

            # Parse plan
            parse_result = extract_json_from_llm_response(
                response_text=response_text,
                expected_type=dict,
                required_fields=["steps"],
            )

            if not parse_result.success:
                return PlanningResult(
                    plan=None,
                    success=False,
                    error=f"JSON parse error: {parse_result.error}",
                )

            # Build ExecutionPlan (delegate to service)
            # `existing_plan` / `clarification_field` are threaded through so the
            # mechanical repair of fabricated parameters can run on the NOMINAL
            # path too (ADR-195). Omitting them left the repair wired only to the
            # panic-mode fallback, where it would almost never fire.
            plan = self.service._build_plan(
                parse_result.data,
                intelligence,
                config,
                existing_plan,
                clarification_field,
            )

            # Calculate savings
            full_tokens = self.service._estimate_full_catalogue_tokens(intelligence.domains)
            tokens_saved = full_tokens - catalogue.token_estimate

            return PlanningResult(
                plan=plan,
                success=True,
                tokens_used=catalogue.token_estimate,
                tokens_saved=tokens_saved,
            )

        except ValueError as e:
            # A rejected tool name OR a step the model left incomplete: both
            # surface as ValueError (pydantic's ValidationError IS one), and the
            # turn ends as a clean planning failure rather than a crash. The event
            # name stays neutral — naming a cause we have not established is the
            # invented diagnosis ADR-182 removed.
            logger.warning(
                "smart_planner_step_rejected",
                error=str(e),
                error_type=type(e).__name__,
                domain=intelligence.primary_domain,
            )
            return PlanningResult(
                plan=None,
                success=False,
                error=f"Plan validation failed: {e}",
            )

        except Exception as e:
            logger.exception("smart_planner_single_domain_error")
            return PlanningResult(
                plan=None,
                success=False,
                error=str(e),
            )


__all__ = [
    "SingleDomainStrategy",
]
