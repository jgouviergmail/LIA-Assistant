"""
SmartPlannerService - Intelligent planning with filtered catalogue.

Architecture v3 - Intelligence, Autonomy, Relevance.

This service generates execution plans using a filtered catalogue,
dramatically reducing token consumption while maintaining functionality.

DIFFERENCES with HierarchicalPlannerService:
1. SINGLE LLM call (not 3 stages)
2. FILTERED catalogue by intent (not full)
3. Multi-domain handled by generative planning (LLM reasons about chains)

Token efficiency:
- Old: Stage1 (1600) + Stage2 (12000) + Stage3 (500) = 14100 tokens
- New: Single call with filtered catalogue = ~1500 tokens
- Savings: 89%

PANIC MODE: If planning fails with filtered catalogue,
retry ONCE with expanded catalogue.
"""

from typing import TYPE_CHECKING, Any, Literal, cast

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.core.constants import (
    FOR_EACH_STEP_ATTRIBUTES,
    PLANNER_FIELD_TO_PARAM_NAMES,
    PLANNER_PRESERVABLE_PARAM_NAMES,
    V3_PLANNER_DOMAIN_FULL_TOKENS,
)
from src.core.context import exclude_sub_agents_from_prompt, panic_mode_attempted
from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.domains.agents.prompts import (
    get_smart_planner_multi_domain_prompt,
    get_smart_planner_prompt,
)
from src.domains.agents.semantic.expansion_service import (
    generate_semantic_dependencies_for_prompt,
)
from src.domains.agents.services.planner.planning_result import PlanningResult
from src.domains.agents.services.smart_catalogue_service import (
    FilteredCatalogue,
    get_smart_catalogue_service,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    planner_for_each_auto_corrections,
)

if TYPE_CHECKING:
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep
    from src.domains.agents.services.planner.strategies.base_strategy import PlanningStrategy

logger = get_logger(__name__)


class SmartPlannerService:
    """
    Intelligent planner with filtered catalogue.

    DIFFERENCES with HierarchicalPlannerService:
    1. SINGLE LLM call (not 3 stages)
    2. FILTERED catalogue by intent (not full)
    3. Multi-domain handled by generative planning (LLM reasons about chains)

    PANIC MODE: If planning fails with filtered catalogue,
    retry ONCE with expanded catalogue.
    """

    # Domain token estimates (from centralized constants)
    DOMAIN_FULL_TOKENS = V3_PLANNER_DOMAIN_FULL_TOKENS

    def __init__(self) -> None:
        self.catalogue_service = get_smart_catalogue_service()
        # Prompts are built at call-time with context (V3 architecture)
        # - get_smart_planner_prompt() and get_smart_planner_multi_domain_prompt()
        #   are formatting functions that load AND format in one step

        # Strategy Pattern: Planning strategies ordered by priority
        # Strategies are tried in order until one can handle the request
        from src.domains.agents.services.planner.strategies.cross_domain_bypass import (
            CrossDomainBypassStrategy,
        )
        from src.domains.agents.services.planner.strategies.multi_domain import (
            MultiDomainStrategy,
        )
        from src.domains.agents.services.planner.strategies.reference_bypass import (
            ReferenceBypassStrategy,
        )
        from src.domains.agents.services.planner.strategies.single_domain import (
            SingleDomainStrategy,
        )

        self.strategies: list[PlanningStrategy] = [
            ReferenceBypassStrategy(),  # Priority 1: Bypass for pure references
            CrossDomainBypassStrategy(),  # Priority 2: Bypass for cross-domain references
            SingleDomainStrategy(service=self),  # Priority 3: LLM for single domain
            MultiDomainStrategy(service=self),  # Priority 4: LLM for multi-domain
        ]

        # Skills: insert SkillBypassStrategy at position 0 if enabled
        from src.core.config import get_settings

        if getattr(get_settings(), "skills_enabled", False):
            from src.domains.agents.services.planner.strategies.skill_bypass import (
                SkillBypassStrategy,
            )

            self.strategies.insert(0, SkillBypassStrategy())

    async def plan(
        self,
        intelligence: QueryIntelligence,
        config: RunnableConfig,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "ExecutionPlan | None" = None,
        tool_selection_result: dict | None = None,
        exclude_tools: set[str] | None = None,
        journal_context: str = "",
    ) -> PlanningResult:
        """
        Generate execution plan based on query intelligence.

        Steps:
        0. FAST PATH: Bypass LLM for resolved reference queries (REFERENCE_PURE with detail intent)
        1. Filter catalogue based on intelligence
        2. Check for cross-domain patterns
        3. Generate plan with filtered tools
        4. If fail → PANIC MODE (retry with expanded catalogue)

        Args:
            intelligence: QueryIntelligence with user intent analysis
            config: RunnableConfig for LangGraph
            validation_feedback: Feedback from semantic validation (issues to fix)
            clarification_response: User's response to HITL clarification question
                                    (e.g., email content they want to write)
            clarification_field: Specific field for which clarification was asked
                                 (e.g., "subject", "body", "description")
            existing_plan: Previous execution plan to preserve parameters from
                          (used when replanning after multi-step clarification)
        """
        # Reset panic mode for new request
        self.catalogue_service.reset_panic_mode()
        panic_mode_attempted.set(False)  # ContextVar per-request isolation

        # F6: Signal prompt builder to suppress sub-agent delegation section
        # when replanning after user rejection of a sub-agent plan.
        # This prevents contradictory instructions (catalogue excludes the tool
        # but prompt section still encourages delegation).
        from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT

        exclude_sub_agents_from_prompt.set(
            bool(exclude_tools and TOOL_NAME_DELEGATE_SUB_AGENT in exclude_tools)
        )

        # Initialize with default failure result (will be replaced if strategy matches)
        result: PlanningResult = PlanningResult(
            plan=None,
            success=False,
            error="No matching strategy found",
        )

        # === STRATEGY PATTERN: Try strategies in priority order ===
        # 1. Bypass strategies (no catalogue needed)
        # Dynamic split: strategies with requires_catalogue=False go first
        bypass_count = len(
            [s for s in self.strategies if not getattr(s, "requires_catalogue", True)]
        )
        for strategy in self.strategies[:bypass_count]:
            if await strategy.can_handle(intelligence, catalogue=None):
                result = await strategy.plan(
                    intelligence=intelligence,
                    config=config,
                    catalogue=None,
                    validation_feedback=validation_feedback,
                    clarification_response=clarification_response,
                    clarification_field=clarification_field,
                    existing_plan=existing_plan,
                )
                if result.success:
                    logger.info(
                        "smart_planner_strategy_success",
                        strategy=strategy.__class__.__name__,
                        intent=intelligence.immediate_intent,
                        turn_type=intelligence.turn_type,
                    )
                    return result
                # Fallback to next strategy if this one failed

        # 2. LLM strategies (require filtered catalogue)
        # Filter catalogue (exclude low-scoring tools from semantic selection)
        filtered = self.catalogue_service.filter_for_intelligence(
            intelligence, tool_selection_result=tool_selection_result
        )

        # F6: Post-filter excluded tools (e.g., sub-agent delegation after user rejection)
        if exclude_tools:
            original_count = filtered.tool_count
            filtered.tools = [t for t in filtered.tools if t["name"] not in exclude_tools]
            filtered.tool_count = len(filtered.tools)
            if filtered.tool_count < original_count:
                logger.info(
                    "smart_planner_tools_excluded",
                    excluded=list(exclude_tools),
                    original_count=original_count,
                    filtered_count=filtered.tool_count,
                )

        logger.info(
            "smart_planner_start",
            domains=intelligence.domains,
            intent=intelligence.immediate_intent,
            tools_count=filtered.tool_count,
            token_estimate=filtered.token_estimate,
        )

        # Store journal context for strategy access via self._current_journal_context
        # (strategies call self.service._build_prompt() which reads this)
        self._current_journal_context = journal_context

        # Try SingleDomain or MultiDomain strategy based on domain count
        for strategy in self.strategies[bypass_count:]:
            if await strategy.can_handle(intelligence, catalogue=filtered):
                result = await strategy.plan(
                    intelligence=intelligence,
                    config=config,
                    catalogue=filtered,
                    validation_feedback=validation_feedback,
                    clarification_response=clarification_response,
                    clarification_field=clarification_field,
                    existing_plan=existing_plan,
                )
                break  # Only one LLM strategy should match

        # Attach filtered catalogue to result for debug panel
        result.filtered_catalogue = filtered

        # Step 3: PANIC MODE if planning failed
        if not result.success and not panic_mode_attempted.get():
            logger.warning(
                "smart_planner_panic_mode",
                original_error=result.error,
                domains=intelligence.domains,
            )
            panic_result = await self._retry_with_panic_mode(
                intelligence,
                config,
                result.error,
                validation_feedback,
                clarification_response,
                clarification_field,
                existing_plan,
                exclude_tools=exclude_tools,
                journal_context=journal_context,
            )
            # Also attach catalogue to panic result
            return panic_result

        return result

    async def _plan_with_catalogue(
        self,
        intelligence: QueryIntelligence,
        catalogue: FilteredCatalogue,
        config: RunnableConfig,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "ExecutionPlan | None" = None,
        journal_context: str = "",
    ) -> PlanningResult:
        """Plan with given catalogue (filtered or panic mode)."""
        if len(intelligence.domains) > 1:
            return await self._plan_multi_domain(
                intelligence,
                catalogue,
                config,
                validation_feedback,
                clarification_response,
                clarification_field,
                existing_plan,
                journal_context=journal_context,
            )
        return await self._plan_single_domain(
            intelligence,
            catalogue,
            config,
            validation_feedback,
            clarification_response,
            clarification_field,
            existing_plan,
            journal_context=journal_context,
        )

    async def _retry_with_panic_mode(
        self,
        intelligence: QueryIntelligence,
        config: RunnableConfig,
        original_error: str | None,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "ExecutionPlan | None" = None,
        exclude_tools: set[str] | None = None,
        journal_context: str = "",
    ) -> PlanningResult:
        """
        PANIC MODE: Retry with expanded catalogue.

        Called when:
        1. Planning failed with filtered catalogue
        2. Panic mode not already attempted

        Purpose:
        - Avoid false negatives where filtering was too aggressive
        - Give LLM a chance to be creative with more tools
        """
        panic_mode_attempted.set(True)

        # Get expanded catalogue
        panic_catalogue = self.catalogue_service.filter_for_intelligence(
            intelligence, panic_mode=True
        )

        # F6: Post-filter excluded tools in panic mode too
        if exclude_tools:
            panic_catalogue.tools = [
                t for t in panic_catalogue.tools if t["name"] not in exclude_tools
            ]
            panic_catalogue.tool_count = len(panic_catalogue.tools)

        logger.info(
            "smart_planner_panic_retry",
            tools_count=panic_catalogue.tool_count,
            original_error=original_error,
        )

        # Retry planning
        result = await self._plan_with_catalogue(
            intelligence,
            panic_catalogue,
            config,
            validation_feedback,
            clarification_response,
            clarification_field,
            existing_plan,
            journal_context=journal_context,
        )

        if result.success:
            result.used_panic_mode = True
            result.filtered_catalogue = panic_catalogue  # Attach panic catalogue for debug
            result.tokens_saved = -panic_catalogue.token_estimate  # Negative = more tokens used
            logger.info("smart_planner_panic_success")
        else:
            result.filtered_catalogue = panic_catalogue  # Still attach for debug even on failure
            logger.error(
                "smart_planner_panic_failed",
                error=result.error,
            )

        return result

    async def _plan_single_domain(
        self,
        intelligence: QueryIntelligence,
        catalogue: FilteredCatalogue,
        config: RunnableConfig,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "ExecutionPlan | None" = None,
        journal_context: str = "",
    ) -> PlanningResult:
        """
        Plan for single domain query.

        Uses filtered catalogue (~200-500 tokens instead of ~5500).
        """
        from src.domains.agents.utils.json_parser import extract_json_from_llm_response
        from src.infrastructure.llm import get_llm

        # Build prompt with temporal context (async for learned patterns)
        prompt = await self._build_prompt(
            intelligence,
            catalogue,
            config,
            validation_feedback,
            clarification_response,
            clarification_field,
            existing_plan,
            journal_context=journal_context,
        )

        llm = get_llm("planner")
        # Use ORIGINAL query (user's language) for planner
        # Memory references are resolved via RESOLVED REFERENCES section in prompt
        # This ensures tool parameters (content, summary, etc.) are in user's language
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Query: {intelligence.original_query}"),
        ]

        logger.debug(
            "planner_prompt_debug",
            prompt_length=len(prompt),
        )

        try:
            from src.infrastructure.llm.invoke_helpers import (
                enrich_config_with_node_metadata,
            )

            config = enrich_config_with_node_metadata(config, "planner")
            response = await llm.ainvoke(messages, config=config)
            response_text = str(response.content).strip()

            logger.debug(
                "planner_response_debug",
                response_length=len(response_text),
            )

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

            # Build ExecutionPlan
            plan = self._build_plan(parse_result.data, intelligence, config)  # type: ignore

            # Calculate savings
            full_tokens = self._estimate_full_catalogue_tokens(intelligence.domains)
            tokens_saved = full_tokens - catalogue.token_estimate

            return PlanningResult(
                plan=plan,
                success=True,
                tokens_used=catalogue.token_estimate,
                tokens_saved=tokens_saved,
            )

        except ValueError as e:
            # Hallucinated tool detected - specific handling
            logger.warning(
                "smart_planner_hallucinated_tool",
                error=str(e),
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

    async def _plan_multi_domain(
        self,
        intelligence: QueryIntelligence,
        catalogue: FilteredCatalogue,
        config: RunnableConfig,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "ExecutionPlan | None" = None,
        journal_context: str = "",
    ) -> PlanningResult:
        """
        Plan for multi-domain query using generative planning.

        The LLM reasons about domain chains and generates appropriate steps
        with dependencies and data flow between domains.

        Examples:
        - "envoie un email au participant de ce rdv" → calendar + emails
        - "recherche le restaurant de ce rendez-vous" → calendar + places
        """
        logger.info(
            "smart_planner_multi_domain",
            domains=intelligence.domains,
            primary=intelligence.primary_domain,
        )
        result = await self._plan_generative_multi_domain(
            intelligence,
            catalogue,
            config,
            validation_feedback,
            clarification_response,
            clarification_field,
            existing_plan,
            journal_context=journal_context,
        )
        result.used_generative = True
        return result

    async def _plan_generative_multi_domain(
        self,
        intelligence: QueryIntelligence,
        catalogue: FilteredCatalogue,
        config: RunnableConfig,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "ExecutionPlan | None" = None,
        journal_context: str = "",
    ) -> PlanningResult:
        """
        Generative planning for multi-domain queries.

        The LLM generates the plan understanding:
        - Dependencies between steps
        - Data flow between domains
        - Implicit conditions

        Token cost: ~1500-2000 (vs ~500 for template)
        But covers the 20% of cases templates don't handle.
        """
        from src.domains.agents.utils.json_parser import extract_json_from_llm_response
        from src.infrastructure.llm import get_llm

        # Build multi-domain prompt with temporal context (async for learned patterns)
        prompt = await self._build_multi_domain_prompt(
            intelligence,
            catalogue,
            config,
            validation_feedback,
            clarification_response,
            clarification_field,
            existing_plan,
            journal_context=journal_context,
        )

        llm = get_llm("planner")
        # Use ORIGINAL query (user's language) for planner
        # Memory references are resolved via RESOLVED REFERENCES section in prompt
        # This ensures tool parameters (content, summary, etc.) are in user's language
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Query: {intelligence.original_query}"),
        ]

        try:
            from src.infrastructure.llm.invoke_helpers import (
                enrich_config_with_node_metadata,
            )

            config = enrich_config_with_node_metadata(config, "planner_multi_domain")
            response = await llm.ainvoke(messages, config=config)
            response_text = str(response.content).strip()

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

            plan = self._build_plan(parse_result.data, intelligence, config)  # type: ignore

            return PlanningResult(
                plan=plan,
                success=True,
                tokens_used=catalogue.token_estimate + 500,  # Prompt overhead
                tokens_saved=0,  # No savings, this is escape hatch
            )

        except ValueError as e:
            # Hallucinated tool detected - specific handling
            logger.warning(
                "smart_planner_hallucinated_tool",
                error=str(e),
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

    def _build_context_with_clarification(
        self,
        intelligence: QueryIntelligence,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "ExecutionPlan | None" = None,
    ) -> str:
        """
        Build context string with optional clarification response injection.

        This is a helper method to avoid DRY violation between _build_prompt
        and _build_multi_domain_prompt.

        Args:
            intelligence: QueryIntelligence with resolved_context
            clarification_response: User's response to HITL clarification question
            clarification_field: Specific field for which clarification was asked
                                 (e.g., "subject", "body", "description")
            existing_plan: Previous execution plan to preserve parameters from
                          (used when replanning after multi-step clarification)

        Returns:
            Context string ready for prompt injection
        """
        # Build base context from resolved_context
        context = (
            intelligence.resolved_context.to_llm_context() if intelligence.resolved_context else ""
        )

        # =========================================================================
        # FIX 2026-01-14: Preserve parameters from existing plan during multi-step clarification
        # =========================================================================
        # When user clarifies one field (e.g., body), we must preserve parameters
        # that were already set in a previous clarification (e.g., subject="retard").
        # Without this, the planner regenerates the plan and loses previous clarifications.
        # =========================================================================
        if existing_plan and clarification_field:
            try:
                preserved_params = self._extract_preserved_parameters(
                    existing_plan, clarification_field
                )
            except Exception as e:
                # Fail-safe: log error but don't break planning
                # Parameter preservation is an optimization, not critical path
                logger.warning(
                    "planner_extract_preserved_params_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    clarification_field=clarification_field,
                )
                preserved_params = {}

            if preserved_params:
                preserved_section = (
                    "\n\n## PRESERVED PARAMETERS (FROM PREVIOUS CLARIFICATION)\n"
                    "The following parameters were already set in a previous step. "
                    "You MUST preserve these exact values in the new plan:\n"
                )
                for param_name, param_value in preserved_params.items():
                    preserved_section += f'- {param_name}: "{param_value}"\n'
                preserved_section += "\nDo NOT modify or regenerate these values."

                logger.info(
                    "planner_preserving_existing_params",
                    preserved_count=len(preserved_params),
                    preserved_keys=list(preserved_params.keys()),
                    clarification_field=clarification_field,
                )
                context = (context + preserved_section) if context else preserved_section.strip()

        # Inject user's clarification response as additional context
        # This is used when user provides content after HITL clarification
        # Example: "I want to wish them happy birthday" after "send an email to marie"
        if clarification_response:
            # FIX 2026-01-14: Use field-specific instruction when clarification_field is known
            # This prevents the planner from putting the response in the wrong field
            # (e.g., putting email subject in body)
            if clarification_field:
                # Field-specific instruction based on the field that was asked for
                field_instruction = self._get_field_specific_instruction(clarification_field)
                logger.debug(
                    "planner_clarification_field_specific",
                    clarification_field=clarification_field,
                    instruction_preview=field_instruction[:50],
                    clarification_preview=(
                        clarification_response[:30] if clarification_response else ""
                    ),
                )
                clarification_section = (
                    "\n\n## USER CLARIFICATION\n"
                    "The user provided this additional information in response to a clarification question:\n"
                    f'"{clarification_response}"\n'
                    f"{field_instruction}"
                )
            else:
                # Fallback to generic instruction when field is unknown
                logger.debug(
                    "planner_clarification_generic_fallback",
                    reason="clarification_field is None",
                    clarification_preview=(
                        clarification_response[:30] if clarification_response else ""
                    ),
                )
                clarification_section = (
                    "\n\n## USER CLARIFICATION\n"
                    "The user provided this additional information in response to a clarification question:\n"
                    f'"{clarification_response}"\n'
                    "Use this as the content for the operation (email body, event description, etc.)."
                )
            context = (
                (context + clarification_section) if context else clarification_section.strip()
            )

        return context

    @staticmethod
    def _build_mcp_reference(selected_domains: list[str] | None = None) -> str:
        """Build MCP reference documentation for planner prompt injection.

        Collects read_me content from admin MCP and per-user MCP, but ONLY
        for servers whose domain is among ``selected_domains``.  This avoids
        injecting large reference content into every planner call.

        Admin MCP takes priority; user MCP only adds servers not already
        present from admin (case-insensitive dedup by server key).

        Args:
            selected_domains: Domain slugs from the query analyzer
                (e.g. ``["mcp_excalidraw", "weather"]``).  Only MCP domains
                (prefixed ``mcp_``) are considered.

        Returns:
            Formatted reference string, or empty string if no relevant content.
        """
        from src.core.config import get_settings
        from src.core.context import user_mcp_tools_ctx
        from src.domains.agents.constants import MCP_DOMAIN_PREFIX

        if not selected_domains:
            return ""

        # Extract server keys from selected MCP domains (e.g. "mcp_excalidraw" → "excalidraw")
        mcp_server_keys = {
            d.removeprefix(MCP_DOMAIN_PREFIX).lower()
            for d in selected_domains
            if d.startswith(MCP_DOMAIN_PREFIX)
        }
        if not mcp_server_keys:
            return ""

        _settings = get_settings()
        max_ref_chars = _settings.mcp_reference_content_max_chars
        if max_ref_chars <= 0:
            return ""

        # Collect from admin MCP first, then user MCP (admin wins on conflict)
        all_references: dict[str, str] = {}

        from src.infrastructure.mcp.client_manager import get_mcp_client_manager

        admin_manager = get_mcp_client_manager()
        admin_keys_lower: set[str] = set()
        if admin_manager:
            admin_ref = admin_manager.reference_content
            admin_keys_lower = {k.lower() for k in admin_ref}
            for name, content in admin_ref.items():
                if name.lower() in mcp_server_keys:
                    all_references[name.lower()] = content

        mcp_ctx = user_mcp_tools_ctx.get()
        if mcp_ctx and mcp_ctx.server_reference_content:
            for name, content in mcp_ctx.server_reference_content.items():
                if name.lower() in mcp_server_keys and name.lower() not in all_references:
                    all_references[name.lower()] = content

        if not all_references:
            return ""

        sections: list[str] = []
        for server_name, ref_content in all_references.items():
            logger.info(
                "mcp_reference_content_stats",
                server_name=server_name,
                source="admin" if server_name in admin_keys_lower else "user",
                content_length=len(ref_content),
                max_ref_chars=max_ref_chars,
                will_truncate=len(ref_content) > max_ref_chars,
            )
            # Line-aware truncation: cut at last complete line boundary
            if len(ref_content) > max_ref_chars:
                cut_pos = ref_content.rfind("\n", 0, max_ref_chars)
                if cut_pos <= 0:
                    cut_pos = max_ref_chars
                truncated = ref_content[:cut_pos] + "\n... (truncated)"
            else:
                truncated = ref_content

            sections.append(
                f"\nMCP TOOL FORMAT REFERENCE — {server_name} (MANDATORY):\n"
                f"When generating parameters for any {server_name} tool, you MUST "
                f"follow the exact structure, field names, types, and enum values "
                f"described below. Match parameter names from the catalogue above "
                f"to the format documented here.\n\n"
                f"IMPORTANT: For parameters that expect a JSON string (type='string' "
                f"containing JSON data like element arrays), you MAY provide the value "
                f"as a native JSON array/object in the plan — it will be auto-converted "
                f"to a JSON string. This avoids error-prone double-escaping.\n"
                f'Example: "elements": [{{"type":"rectangle","x":100,...}}] is valid.\n\n'
                f"{truncated}"
            )

        return "\n".join(sections)

    @staticmethod
    def _build_skills_catalog(config: RunnableConfig) -> str:
        """Build skills L1 catalogue for planner prompt injection.

        Per agentskills.io standard: XML catalogue with name + description + location.
        Returns empty string when skills are disabled or no skills available.
        """
        from src.core.config import get_settings

        if not getattr(get_settings(), "skills_enabled", False):
            return ""

        from src.core.context import active_skills_ctx
        from src.domains.skills.injection import build_skills_catalog

        user_id = config.get("configurable", {}).get("user_id", "")
        return build_skills_catalog(
            str(user_id),
            active_skills=active_skills_ctx.get(),
        )

    @staticmethod
    def _build_sub_agents_section() -> str:
        """Build sub-agents delegation section for planner prompt.

        Returns the section content when SUB_AGENTS_ENABLED, empty string otherwise.
        Returns empty string when exclude_sub_agents_from_prompt ContextVar is True
        (F6: user rejected a sub-agent plan, replanning without delegation).
        Braces in examples are escaped for Python .format() compatibility.
        """
        from src.core.config import get_settings

        if not getattr(get_settings(), "sub_agents_enabled", False):
            return ""

        # F6: Suppress sub-agent section during replan after user rejection.
        # The catalogue already excludes delegate_to_sub_agent_tool, but without
        # suppressing this prompt section the LLM receives contradictory instructions
        # (told to delegate while the tool is absent from AVAILABLE TOOLS).
        if exclude_sub_agents_from_prompt.get():
            return ""

        return (
            "SUB-AGENT DELEGATION (Optional Advanced Capability):\n"
            "You can delegate complex, specialized, or research-intensive tasks "
            "to ephemeral sub-agents. A sub-agent is a temporary expert you create "
            "with specific directives.\n\n"
            "WHEN TO DELEGATE:\n"
            "- Deep domain expertise needed (accounting, legal, technical analysis)\n"
            "- Task decomposes into independent parallel research tracks\n"
            "- Quality benefits from a specialist's focused analysis\n"
            "- Complex multi-faceted request (compare options, cross-reference)\n\n"
            "WHEN NOT TO DELEGATE:\n"
            "- Simple factual queries (weather, contact lookup, calendar)\n"
            "- Standard CRUD operations (send email, create event)\n"
            "- Tasks requiring user confirmation (sub-agents are read-only)\n\n"
            "HOW TO USE delegate_to_sub_agent_tool:\n"
            "- expertise: Specialist role description\n"
            "- instruction: Detailed task with context and expected output\n"
            "- Independent sub-agents → leave depends_on empty (they run in parallel)\n"
            "- ALWAYS set timeout_seconds: 120 for delegate steps (sub-agents need more time)\n"
            "- Reference results: $steps.step_N.analysis\n"
            "- Handle mutations (send_email, etc.) YOURSELF after sub-agent results\n\n"
            "IMPORTANT — AVOID DUPLICATING SUB-AGENT WORK:\n"
            "- Do NOT add search/research steps that sub-agents will perform themselves.\n"
            "  Sub-agents have full access to web search and other tools — they handle "
            "  their own research autonomously.\n"
            "- Your plan should ONLY contain: delegate steps + any non-delegated actions "
            "  (HITL operations, write operations, steps the user asked YOU to do).\n"
            "- BAD: step_1=web_search, step_2=delegate(expert, use $steps.step_1)\n"
            "  GOOD: step_1=delegate(expert, 'research X and produce analysis')\n"
        )

    def _extract_preserved_parameters(
        self,
        existing_plan: "ExecutionPlan",
        clarification_field: str,
    ) -> dict[str, Any]:
        """
        Extract parameters from existing plan that should be preserved.

        When replanning after a clarification, we want to preserve parameters
        that were already set (from previous clarifications or original query),
        EXCEPT for the field currently being clarified.

        Args:
            existing_plan: The previous execution plan
            clarification_field: The field being clarified (to exclude from preservation)

        Returns:
            Dict of parameter_name -> value for parameters to preserve

        Note:
            Uses PLANNER_PRESERVABLE_PARAM_NAMES and PLANNER_FIELD_TO_PARAM_NAMES
            from constants.py, which are automatically derived from
            INSUFFICIENT_CONTENT_REQUIRED_FIELDS to ensure consistency.
        """
        preserved: dict[str, Any] = {}

        if not existing_plan or not existing_plan.steps:
            return preserved

        # Get all param_names that correspond to the clarification_field
        # Example: clarification_field="body" → skip {"body", "content", "content_instruction"}
        # This handles the case where tool uses "content_instruction" but we clarify "body"
        params_to_skip = PLANNER_FIELD_TO_PARAM_NAMES.get(clarification_field, frozenset())
        # Also include the clarification_field itself in case it's a direct match
        params_to_skip = params_to_skip | {clarification_field}

        # Look at all steps to preserve parameters across the plan
        for step in existing_plan.steps:
            if not step.parameters:
                continue

            for param_name, param_value in step.parameters.items():
                # Skip all param_names related to the field being clarified
                # This correctly handles "body" vs "content_instruction" mismatch
                if param_name in params_to_skip:
                    continue

                # Skip non-preservable fields (like IDs, flags, etc.)
                # Uses centralized constant derived from INSUFFICIENT_CONTENT_REQUIRED_FIELDS
                if param_name not in PLANNER_PRESERVABLE_PARAM_NAMES:
                    continue

                # Skip empty/None values
                if param_value is None or param_value == "":
                    continue

                # Skip values that look like placeholders or references
                if isinstance(param_value, str):
                    if param_value.startswith("$steps.") or param_value.startswith("{{"):
                        continue

                preserved[param_name] = param_value

        return preserved

    def _get_field_specific_instruction(self, clarification_field: str) -> str:
        """
        Get field-specific instruction for clarification injection.

        Maps clarification field names to precise LLM instructions.
        Field names MUST match those defined in INSUFFICIENT_CONTENT_REQUIRED_FIELDS
        (see src/core/constants.py).

        Args:
            clarification_field: The field name (e.g., "subject", "body", "title")

        Returns:
            Precise instruction for the LLM
        """
        # Mapping from field name to specific instruction
        # This ensures the planner puts the user's response in the correct field
        # Field names MUST match INSUFFICIENT_CONTENT_REQUIRED_FIELDS in core/constants.py
        field_instructions = {
            # ===== Email fields (INSUFFICIENT_CONTENT_DOMAIN_EMAIL) =====
            "recipient": "Use this as the email recipient (TO field).",
            "subject": "Use this as the EMAIL SUBJECT. Do NOT put this in the email body.",
            "body": "Use this as the EMAIL BODY content.",
            "cc": "Use this/these as the CC recipients.",
            "bcc": "Use this/these as the BCC recipients.",
            # ===== Calendar/Event fields (INSUFFICIENT_CONTENT_DOMAIN_EVENT) =====
            "title": "Use this as the TITLE (summary). Do NOT put this in description or body.",
            "start_datetime": "Use this as the START DATE/TIME for the event.",
            "end_or_duration": "Use this as the END DATE/TIME or DURATION for the event.",
            "description": "Use this as the DESCRIPTION.",
            "location": "Use this as the LOCATION.",
            "attendees": "Use these as the ATTENDEES.",
            # ===== Task fields (INSUFFICIENT_CONTENT_DOMAIN_TASK) =====
            # "title" is shared with events (defined above)
            "priority": "Use this as the TASK PRIORITY (high/medium/low).",
            "due_date": "Use this as the TASK DUE DATE.",
            "notes": "Use this as the TASK NOTES.",
            # ===== Contact fields (INSUFFICIENT_CONTENT_DOMAIN_CONTACT) =====
            # Note: Tool uses single "name" field (Full Name)
            "name": "Use this as the CONTACT FULL NAME.",
            "email": "Use this as the CONTACT EMAIL.",
            "phone": "Use this as the CONTACT PHONE NUMBER.",
            # ===== Generic fallbacks =====
            "content": "Use this as the main content for the operation.",
            "query": "Use this as the search query.",
        }

        instruction = field_instructions.get(clarification_field)
        if instruction:
            return instruction

        # Fallback for unknown fields - still provides clear instruction
        logger.debug(
            "clarification_field_not_in_mapping",
            clarification_field=clarification_field,
            msg="Using generic fallback instruction",
        )
        return f"Use this as the {clarification_field.upper()} field for the operation."

    async def _build_prompt(
        self,
        intelligence: QueryIntelligence,
        catalogue: FilteredCatalogue,
        config: RunnableConfig,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "ExecutionPlan | None" = None,
        journal_context: str = "",
    ) -> str:
        """Build LLM prompt with filtered catalogue."""
        # Fallback: read from instance if not passed directly (strategy pattern)
        if not journal_context:
            journal_context = getattr(self, "_current_journal_context", "")
        from src.core.config import get_settings
        from src.core.constants import DEFAULT_TIMEZONE
        from src.domains.agents.services.plan_pattern_learner import (
            get_learned_patterns_prompt,
        )

        _settings = get_settings()

        # Extract user preferences from config
        configurable = config.get("configurable", {})
        user_timezone = configurable.get("user_timezone", DEFAULT_TIMEZONE)
        user_language = configurable.get("user_language", _settings.default_language)

        # Conditional semantic deps injection for single-domain queries
        # - Mutations may need cross-domain deps (e.g., send_email needs contact resolution)
        # - Read-only single-domain queries never need cross-domain semantic deps
        # - Saves ~150-300 tokens for simple queries like "contacts Dupont"
        if intelligence.is_mutation_intent:
            semantic_deps = generate_semantic_dependencies_for_prompt(intelligence.domains)
        else:
            semantic_deps = ""

        # Get learned patterns for this context (async, with timeout fallback)
        learned_patterns = await get_learned_patterns_prompt(
            domains=intelligence.domains,
            is_mutation=intelligence.is_mutation_intent,
        )

        # FIX 2026-03-23: Always use original_query (user's language) for content extraction.
        # english_enriched_query contains translated content (e.g., "merci" → "Thank you")
        # which causes the planner to extract English body/subject instead of the original.
        # Resolved references (e.g., "ma femme" → "Marie Dupond") are passed separately in context.
        resolved_query = intelligence.original_query

        # Build context with optional clarification response (DRY helper)
        context = self._build_context_with_clarification(
            intelligence, clarification_response, clarification_field, existing_plan
        )

        # Append enriched English query with resolved references.
        # All ordinal/pronoun references are ALREADY resolved here — the planner must use
        # these values directly and NEVER call resolve_reference or any lookup tool.
        # User-provided content (body, subject, title, description, notes) must be extracted
        # from the Original query (user's language), not from this English version.
        if intelligence.english_enriched_query:
            context += (
                f"\n\nResolved request (all references already resolved, use directly): "
                f"{intelligence.english_enriched_query}\n"
                f"CONTENT RULE: Extract user-provided content from Original query above (user's language)."
            )

        # MCP reference content (read_me) — only when MCP domains are selected
        mcp_reference = self._build_mcp_reference(intelligence.domains)

        # Skills L1 catalogue (agentskills.io standard)
        skills_catalog = self._build_skills_catalog(config)

        # F6: Sub-agents delegation section (empty if disabled)
        sub_agents_section = self._build_sub_agents_section()

        return get_smart_planner_prompt(
            user_goal=intelligence.user_goal.value,
            intent=intelligence.immediate_intent,
            domains=", ".join(intelligence.domains) if intelligence.domains else "",
            anticipated_needs=(
                ", ".join(intelligence.anticipated_needs) if intelligence.anticipated_needs else ""
            ),
            catalogue=catalogue.to_prompt_string(),
            original_query=resolved_query,
            context=context,
            references=(
                str(intelligence.resolved_references) if intelligence.resolved_references else ""
            ),
            user_timezone=user_timezone,
            user_language=user_language,
            validation_feedback=validation_feedback,
            semantic_dependencies=semantic_deps,
            learned_patterns=learned_patterns,
            mcp_reference=mcp_reference,
            # FOR_EACH detection from QueryIntelligence
            for_each_detected=intelligence.for_each_detected,
            for_each_collection_key=intelligence.for_each_collection_key,
            cardinality_magnitude=intelligence.cardinality_magnitude,
            skills_catalog=skills_catalog,
            sub_agents_section=sub_agents_section,
            journal_context=journal_context,  # Personal journal context
        )

    async def _build_multi_domain_prompt(
        self,
        intelligence: QueryIntelligence,
        catalogue: FilteredCatalogue,
        config: RunnableConfig,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "ExecutionPlan | None" = None,
        journal_context: str = "",
    ) -> str:
        """Build prompt for generative multi-domain planning."""
        # Fallback: read from instance if not passed directly (strategy pattern)
        if not journal_context:
            journal_context = getattr(self, "_current_journal_context", "")
        from src.core.config import get_settings
        from src.core.constants import DEFAULT_TIMEZONE
        from src.domains.agents.services.plan_pattern_learner import (
            get_learned_patterns_prompt,
        )

        _settings = get_settings()

        # Extract user preferences from config
        configurable = config.get("configurable", {})
        user_timezone = configurable.get("user_timezone", DEFAULT_TIMEZONE)
        user_language = configurable.get("user_language", _settings.default_language)

        # Generate dynamic semantic dependencies for cross-domain planning
        semantic_deps = generate_semantic_dependencies_for_prompt(intelligence.domains)

        # Get learned patterns for this context (async, with timeout fallback)
        learned_patterns = await get_learned_patterns_prompt(
            domains=intelligence.domains,
            is_mutation=intelligence.is_mutation_intent,
        )

        # FIX 2026-03-23: Always use original_query (user's language) for content extraction.
        # english_enriched_query contains translated content (e.g., "merci" → "Thank you")
        # which causes the planner to extract English body/subject instead of the original.
        # Resolved references (e.g., "ma femme" → "Marie Dupond") are passed separately in context.
        resolved_query = intelligence.original_query

        # Build context with optional clarification response (DRY helper)
        context = self._build_context_with_clarification(
            intelligence, clarification_response, clarification_field, existing_plan
        )

        # Append enriched English query with resolved references.
        # All ordinal/pronoun references are ALREADY resolved here — the planner must use
        # these values directly and NEVER call resolve_reference or any lookup tool.
        # User-provided content (body, subject, title, description, notes) must be extracted
        # from the Original query (user's language), not from this English version.
        if intelligence.english_enriched_query:
            context += (
                f"\n\nResolved request (all references already resolved, use directly): "
                f"{intelligence.english_enriched_query}\n"
                f"CONTENT RULE: Extract user-provided content from Original query above (user's language)."
            )

        # MCP reference content (read_me) — only when MCP domains are selected
        mcp_reference = self._build_mcp_reference(intelligence.domains)

        # Skills L1 catalogue (agentskills.io standard)
        skills_catalog = self._build_skills_catalog(config)

        # F6: Sub-agents delegation section (empty if disabled)
        sub_agents_section = self._build_sub_agents_section()

        return get_smart_planner_multi_domain_prompt(
            domains=", ".join(intelligence.domains) if intelligence.domains else "",
            primary_domain=intelligence.primary_domain,
            intent=intelligence.immediate_intent,
            user_goal=intelligence.user_goal.value,
            anticipated_needs=(
                ", ".join(intelligence.anticipated_needs) if intelligence.anticipated_needs else ""
            ),
            catalogue=catalogue.to_prompt_string(),
            original_query=resolved_query,
            context=context,
            references=(
                str(intelligence.resolved_references) if intelligence.resolved_references else ""
            ),
            user_timezone=user_timezone,
            user_language=user_language,
            validation_feedback=validation_feedback,
            semantic_dependencies=semantic_deps,
            learned_patterns=learned_patterns,
            mcp_reference=mcp_reference,
            # FOR_EACH detection from QueryIntelligence
            for_each_detected=intelligence.for_each_detected,
            for_each_collection_key=intelligence.for_each_collection_key,
            cardinality_magnitude=intelligence.cardinality_magnitude,
            skills_catalog=skills_catalog,
            sub_agents_section=sub_agents_section,
            journal_context=journal_context,  # Personal journal context
        )

    def _build_plan(
        self,
        plan_data: dict,
        intelligence: QueryIntelligence,
        config: RunnableConfig,
    ) -> "ExecutionPlan":
        """Build ExecutionPlan from LLM response."""
        from src.core.config import get_settings
        from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType

        settings = get_settings()

        steps = []
        for step_data in plan_data.get("steps", []):
            # Normalize tool name to ensure _tool suffix
            raw_tool_name = step_data.get("tool_name", "")
            normalized_tool_name = self._normalize_tool_name(
                raw_tool_name,
                intelligence.primary_domain,
                intelligence.original_query,
            )

            # ================================================================
            # FOR_EACH auto-correction (defensive programming)
            # LLMs may generate for_each_max values exceeding schema limits.
            # Instead of failing validation, auto-correct with warning log.
            # ================================================================
            raw_for_each_max = step_data.get("for_each_max", settings.for_each_max_default)
            for_each_max = raw_for_each_max

            if raw_for_each_max > settings.for_each_max_hard_limit:
                if settings.planner_auto_correct_for_each_max:
                    for_each_max = settings.for_each_max_hard_limit
                    logger.warning(
                        "planner_for_each_max_auto_corrected",
                        original_value=raw_for_each_max,
                        corrected_value=for_each_max,
                        step_id=step_data.get("id"),
                        tool_name=normalized_tool_name,
                    )
                    planner_for_each_auto_corrections.labels(correction_type="max_exceeded").inc()
                # If auto-correction disabled, let Pydantic validation fail

            # ================================================================
            # FOR_EACH MISPLACEMENT FIX (defensive programming - always enabled)
            # LLMs may incorrectly put for_each inside parameters instead of
            # as a step attribute. Extract and auto-correct with warning.
            # ================================================================
            raw_parameters = step_data.get("parameters", {})
            parameters = dict(raw_parameters)  # Copy to avoid mutation

            # Extract misplaced step attributes from parameters (DRY: use dict)
            extracted_attrs: dict[str, Any] = {}

            for key in FOR_EACH_STEP_ATTRIBUTES:
                if key in parameters:
                    extracted_attrs[key] = parameters.pop(key)
                    logger.warning(
                        "planner_for_each_attribute_misplaced",
                        step_id=step_data.get("id"),
                        tool_name=normalized_tool_name,
                        attribute=key,
                    )
                    planner_for_each_auto_corrections.labels(
                        correction_type="misplaced_attribute"
                    ).inc()

            # Resolve final values: step-level takes precedence over extracted
            # IMPORTANT: Use 'is not None' to handle empty strings correctly
            for_each_candidate = (
                step_data.get("for_each")
                if step_data.get("for_each") is not None
                else extracted_attrs.get("for_each")
            )

            # Validate for_each type: must be string reference, not list/dict
            if for_each_candidate is not None and not isinstance(for_each_candidate, str):
                logger.warning(
                    "planner_for_each_invalid_type",
                    step_id=step_data.get("id"),
                    tool_name=normalized_tool_name,
                    value_type=type(for_each_candidate).__name__,
                )
                planner_for_each_auto_corrections.labels(correction_type="invalid_type").inc()
                for_each_value = None
            else:
                for_each_value = for_each_candidate

            # Resolve other for_each attributes with proper precedence
            extracted_max = extracted_attrs.get("for_each_max")
            if extracted_max is not None and step_data.get("for_each_max") is None:
                for_each_max = min(extracted_max, settings.for_each_max_hard_limit)

            on_item_error_raw = (
                step_data.get("on_item_error") or extracted_attrs.get("on_item_error") or "continue"
            )
            # Cast to Literal type for MyPy compatibility
            on_item_error_value: Literal["continue", "stop", "collect_errors"] = cast(
                Literal["continue", "stop", "collect_errors"],
                (
                    on_item_error_raw
                    if on_item_error_raw in ("continue", "stop", "collect_errors")
                    else "continue"
                ),
            )
            delay_value = (
                step_data.get("delay_between_items_ms")
                or extracted_attrs.get("delay_between_items_ms")
                or 0
            )

            step_timeout = step_data.get("timeout_seconds")

            # ================================================================
            # Excalidraw timeout override (evolution F2 — Iterative Builder)
            # The iterative builder makes a single LLM call within the tool
            # execution, so the default 30s timeout is insufficient.
            # ================================================================
            from src.infrastructure.mcp.excalidraw.overrides import (
                EXCALIDRAW_CREATE_VIEW_NORMALIZED,
            )

            if step_timeout is None and normalized_tool_name == EXCALIDRAW_CREATE_VIEW_NORMALIZED:
                excalidraw_timeout = getattr(settings, "mcp_excalidraw_step_timeout_seconds", 90)
                step_timeout = excalidraw_timeout
                logger.info(
                    "excalidraw_step_timeout_override",
                    step_id=step_data.get("id"),
                    timeout_seconds=step_timeout,
                )

            step = ExecutionStep(
                step_id=step_data.get("id", "step_1"),
                step_type=StepType.TOOL,
                agent_name=step_data.get("agent_name", f"{intelligence.primary_domain}_agent"),
                tool_name=normalized_tool_name,
                parameters=parameters,
                depends_on=step_data.get("depends_on", []),
                timeout_seconds=step_timeout,
                # FOR_EACH pattern support (plan_planner.md Section 10)
                for_each=for_each_value,
                for_each_max=for_each_max,
                on_item_error=on_item_error_value,
                delay_between_items_ms=delay_value,
            )
            steps.append(step)

        # Extract execution_mode from LLM output (default: sequential for safety)
        execution_mode = plan_data.get("execution_mode", "sequential")

        plan = self._build_plan_from_steps(
            steps, intelligence, config, execution_mode=execution_mode
        )

        # Skills: propagate skill_name from LLM output to plan metadata
        skill_name = plan_data.get("skill_name")
        if skill_name:
            plan.metadata["skill_name"] = skill_name

        return plan

    def _normalize_tool_name(self, tool_name: str, domain: str, query: str = "") -> str:
        """
        Normalize tool name to match manifest naming convention.

        Handles common LLM mistakes:
        - Missing _tool suffix: "search_events" -> "search_events_tool"
        - Wrong verb: "list_events" -> "search_events_tool" (calendar search)
        - Partial names: "search" -> "search_events_tool" (based on domain)
        - Hallucinated tools: "resolve_reference_tool" -> raises ValueError

        Args:
            tool_name: Raw tool name from LLM
            domain: Primary domain for context
            query: Original query (for hallucination tracking)

        Returns:
            Normalized tool name with _tool suffix

        Raises:
            ValueError: If tool is hallucinated (doesn't exist in any manifest)
        """
        from src.domains.agents.registry.hallucinated_tools import (
            is_hallucinated_tool,
            record_hallucination,
        )

        if not tool_name:
            return ""

        # === DETECT HALLUCINATED TOOLS (using auto-enriching registry) ===
        is_hallucinated, pattern = is_hallucinated_tool(tool_name)
        if is_hallucinated:
            # Record to auto-enrich the registry
            record_hallucination(
                tool_name=tool_name,
                domain=domain,
                query=query,
            )
            logger.warning(
                "hallucinated_tool_detected",
                tool_name=tool_name,
                pattern=pattern,
                domain=domain,
            )
            raise ValueError(
                f"Hallucinated tool '{tool_name}' detected. "
                f"References are already resolved in CONTEXT - use values directly."
            )

        # Already has _tool suffix - return as is
        if tool_name.endswith("_tool"):
            return tool_name

        # MCP tools don't follow the _tool suffix convention
        if tool_name.startswith("mcp_"):
            return tool_name

        # Add _tool suffix if missing
        normalized = f"{tool_name}_tool"

        # Common corrections for LLM mistakes (2026-01 unified architecture)
        # All search/list/details tools are now unified under get_*_tool
        corrections = {
            # Calendar domain → get_events_tool (unified)
            "search_events_tool": "get_events_tool",
            "list_events_tool": "get_events_tool",
            "find_events_tool": "get_events_tool",
            "get_event_details_tool": "get_events_tool",
            # Contacts domain → get_contacts_tool (unified)
            "search_contacts_tool": "get_contacts_tool",
            "list_contacts_tool": "get_contacts_tool",
            "find_contacts_tool": "get_contacts_tool",
            "get_contact_details_tool": "get_contacts_tool",
            # Emails domain → get_emails_tool (unified)
            "search_emails_tool": "get_emails_tool",
            "list_emails_tool": "get_emails_tool",
            "find_emails_tool": "get_emails_tool",
            "get_email_details_tool": "get_emails_tool",
            # Tasks domain → get_tasks_tool (unified)
            "search_tasks_tool": "get_tasks_tool",
            "list_tasks_tool": "get_tasks_tool",
            "find_tasks_tool": "get_tasks_tool",
            "get_task_details_tool": "get_tasks_tool",
            # Drive domain → get_files_tool (unified)
            "search_files_tool": "get_files_tool",
            "list_files_tool": "get_files_tool",
            "find_files_tool": "get_files_tool",
            "get_file_details_tool": "get_files_tool",
            # Places domain → get_places_tool (unified)
            "search_places_tool": "get_places_tool",
            "list_places_tool": "get_places_tool",
            "find_places_tool": "get_places_tool",
            "get_place_details_tool": "get_places_tool",
        }

        if normalized in corrections:
            original = normalized
            normalized = corrections[normalized]
            logger.info(
                "tool_name_normalized",
                original=original,
                normalized=normalized,
                domain=domain,
            )

        return normalized

    def _build_plan_from_steps(
        self,
        steps: list["ExecutionStep"],
        intelligence: QueryIntelligence,
        config: RunnableConfig,
        execution_mode: str = "sequential",
    ) -> "ExecutionPlan":
        """Build ExecutionPlan from steps.

        Args:
            steps: List of execution steps.
            intelligence: Query intelligence from router.
            config: LangGraph runnable config.
            execution_mode: "sequential" or "parallel" (from LLM output).
        """
        from src.domains.agents.nodes.utils import extract_session_id_from_config
        from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

        configurable = config.get("configurable", {})

        # Validate execution_mode (LLM may produce unexpected values)
        if execution_mode not in ("sequential", "parallel"):
            execution_mode = "sequential"

        return ExecutionPlan(
            plan_id=f"smart_{configurable.get('run_id', 'unknown')}",
            user_id=str(configurable.get("user_id", "")),
            session_id=extract_session_id_from_config(config, required=False) or "",
            steps=steps,
            execution_mode=execution_mode,
            metadata={
                "smart_planner": True,
                "intent": intelligence.immediate_intent,
                "domains": intelligence.domains,
                "user_goal": intelligence.user_goal.value,
                "tokens_estimate": self.catalogue_service.get_metrics().tokens_saved,
                # FOR_EACH HITL: Propagate cardinality from query analysis for accurate count
                # This is the expected iteration count extracted from user query
                # (e.g., "mes 2 prochains rdv" → cardinality_magnitude=2)
                "cardinality_magnitude": intelligence.cardinality_magnitude,
                "for_each_detected": intelligence.for_each_detected,
            },
        )

    def _estimate_full_catalogue_tokens(self, domains: list[str]) -> int:
        """Estimate tokens for full catalogue (for comparison)."""
        return sum(self.DOMAIN_FULL_TOKENS.get(d, 3000) for d in domains)

    # ==========================================================================
    # NOTE: Reference bypass and cross-domain bypass logic has been extracted
    # to planner/strategies/ modules for better separation of concerns.
    # See: reference_bypass.py and cross_domain_bypass.py
    # Domain constants moved to: planner/domain_constants.py
    # ==========================================================================


# Singleton
_smart_planner: SmartPlannerService | None = None


def get_smart_planner_service() -> SmartPlannerService:
    """Get singleton SmartPlannerService instance."""
    global _smart_planner
    if _smart_planner is None:
        _smart_planner = SmartPlannerService()
    return _smart_planner
