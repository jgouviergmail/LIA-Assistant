"""
Multi-Domain Strategy - LLM-based planning for multi-domain queries.

This strategy handles queries that involve multiple domains and require
LLM intelligence to reason about domain chains and generate an execution plan.

Examples:
- "Send an email to the participant of this meeting" → calendar + emails
- "Find the restaurant of this event" → calendar + places
- "Create a task from this email" → emails + tasks

Architecture:
- Uses filtered catalogue with tools from multiple domains
- Single LLM call with cross-domain reasoning
- Builds prompt with multi-domain context and dependencies
- LLM generates steps with data flow between domains

Token cost: ~1500-2000 (vs ~500 for single domain)
But handles the 20% of complex cases that bypass can't handle.

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


class MultiDomainStrategy:
    """
    Planning strategy for multi-domain queries using LLM.

    Requires a filtered catalogue with tools from multiple domains
    and uses LLM to reason about cross-domain dependencies.
    """

    def __init__(self, service: Any = None):
        """
        Initialize with optional service reference.

        Args:
            service: SmartPlannerService instance for delegating helper methods
        """
        self.service = service

    async def can_handle(
        self,
        intelligence: QueryIntelligence,
        catalogue: FilteredCatalogue | None = None,
    ) -> bool:
        """
        Check if this strategy can handle the query.

        Multi-domain strategy handles queries with MORE than one domain.
        This is checked AFTER bypass strategies have been tried.

        Args:
            intelligence: QueryIntelligence with user intent
            catalogue: Filtered catalogue (must be present)

        Returns:
            True if more than one domain, False otherwise
        """
        if not catalogue:
            return False

        # Must be MORE than 1 domain
        return len(intelligence.domains) > 1

    async def plan(
        self,
        intelligence: QueryIntelligence,
        config: RunnableConfig,
        catalogue: FilteredCatalogue | None = None,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: ExecutionPlan | None = None,
        journal_context: str = "",
    ) -> PlanningResult:
        """
        Plan for multi-domain query using generative LLM planning.

        The LLM reasons about domain chains and generates appropriate steps
        with dependencies and data flow between domains.

        Args:
            intelligence: QueryIntelligence with user intent
            config: RunnableConfig for LangGraph
            catalogue: Filtered catalogue with multi-domain tools
            validation_feedback: Feedback from semantic validation
            clarification_response: User's clarification response
            clarification_field: Field that was clarified
            existing_plan: Previous plan (for replanning)

        Returns:
            PlanningResult with LLM-generated multi-domain plan
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.domains.agents.utils.json_parser import extract_json_from_llm_response
        from src.infrastructure.llm import get_llm

        if not catalogue:
            return PlanningResult(
                success=False,
                plan=None,
                error="No catalogue provided for multi-domain planning",
            )

        # Delegate to service for prompt building (complex logic)
        if not self.service:
            return PlanningResult(
                success=False,
                plan=None,
                error="Service not injected for multi-domain planning",
            )

        logger.info(
            "smart_planner_multi_domain",
            domains=intelligence.domains,
            primary=intelligence.primary_domain,
        )

        # Build multi-domain prompt with temporal context (async for learned patterns)
        prompt = await self.service._build_multi_domain_prompt(
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

        try:
            from src.infrastructure.llm.invoke_helpers import (
                enrich_config_with_node_metadata,
            )

            config = enrich_config_with_node_metadata(config, "planner_multi_domain")
            response = await llm.ainvoke(messages, config=config)
            response_text = response.text.strip()

            parse_result = extract_json_from_llm_response(
                response_text=response_text,
                expected_type=dict,
                required_fields=["steps"],
            )

            if not parse_result.success:
                return PlanningResult(
                    plan=None,
                    success=False,
                    error=f"Generative planning failed: {parse_result.error}",
                )

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

            return PlanningResult(
                plan=plan,
                success=True,
                tokens_used=catalogue.token_estimate + 500,  # Prompt overhead
                tokens_saved=0,  # No savings, this is escape hatch
                used_generative=True,  # Mark as generative
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
                domains=intelligence.domains,
            )
            return PlanningResult(
                plan=None,
                success=False,
                error=f"Plan validation failed: {e}",
            )

        except Exception as e:
            logger.exception("smart_planner_generative_error")
            return PlanningResult(
                plan=None,
                success=False,
                error=f"Generative planning exception: {e}",
            )


__all__ = [
    "MultiDomainStrategy",
]
