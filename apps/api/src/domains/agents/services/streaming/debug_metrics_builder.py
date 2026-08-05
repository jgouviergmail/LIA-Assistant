"""Debug-metrics assembly for the streaming service.

``DebugMetricsBuilder`` builds every section of the debug panel payload from the
final graph ``state``, the run-level tracking context and the cached semantic
selection artefacts. It is extracted verbatim from
``StreamingService._add_debug_metrics_sections`` (behavior-preserving split):
each section remains independently guarded so a failure in one never prevents
the others from being built, and the sections are assembled in the SAME order
as before because several of them read/enrich values written by earlier ones
(``token_budget`` enriched by ``llm_calls``; ``request_lifecycle`` /
``llm_pipeline`` derived from ``llm_calls`` after ``image_generation`` injects
its synthetic entries).
"""

from collections.abc import Callable
from typing import Any

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _chrono_key(call: dict[str, Any]) -> tuple[float, int]:
    """Chronological sort key for an LLM call dict.

    The run-anchored ``started_offset_ms`` leads; ``sequence`` breaks ties
    (parallel same-instant starts, and legacy records without offsets).
    """
    return (float(call.get("started_offset_ms") or 0.0), int(call.get("sequence") or 0))


class DebugMetricsBuilder:
    """Assemble the debug-panel sections into a debug_metrics dict in place.

    Args:
        tracker: Run-level tracking context (LLM / Google API / image-gen breakdowns).
        cached_filtered_catalogue: Cached filtered tool catalogue (SemanticToolSelector).
        cached_tool_scores: Cached per-tool semantic scores (SemanticToolSelector).
        skill_name_resolver: Callable resolving the activated skill name from state
            (``StreamingService.resolve_activated_skill_name``).
    """

    def __init__(
        self,
        *,
        tracker: Any | None,
        cached_filtered_catalogue: Any | None,
        cached_tool_scores: dict[str, Any] | None,
        skill_name_resolver: Callable[[dict[str, Any]], str | None],
    ) -> None:
        self.tracker = tracker
        self._cached_filtered_catalogue = cached_filtered_catalogue
        self._cached_tool_scores = cached_tool_scores
        self._resolve_skill_name = skill_name_resolver

    def build(
        self,
        debug_metrics: dict[str, Any],
        state: dict[str, Any],
        run_id: str,
        db_aggregated: Any | None = None,
        hitl_interrupt: dict[str, Any] | None = None,
    ) -> None:
        """Add all debug metrics sections to ``debug_metrics`` (in place).

        Called at the END of streaming when ALL data is available. Builds
        token_budget, planner_intelligence, tool_selection, execution_timeline,
        llm_calls and the remaining panel sections.

        Args:
            debug_metrics: Base debug metrics dict (from query_intelligence.to_debug_metrics()).
            state: Final state dict with all data.
            run_id: Run ID for logging.
            db_aggregated: Optional DB-aggregated token summary (includes prior HITL requests).
            hitl_interrupt: ``{action_type, tool_name}`` when THIS run ended on
                a HITL interrupt, else None (see ``debug_metrics_stages.build_hitl``).
        """
        from src.core.config import get_settings
        from src.domains.agents.services.streaming import debug_metrics_stages as stages

        settings = get_settings()

        stages.build_execution_mode(debug_metrics, state)
        self._build_token_budget(debug_metrics, state, settings)
        self._build_planner_intelligence(debug_metrics, state)
        self._build_execution_timeline(debug_metrics, state, run_id)
        self._build_tool_selection(debug_metrics, run_id)
        self._build_llm_calls(debug_metrics, run_id, db_aggregated)
        self._build_google_api_calls(debug_metrics, run_id)
        self._build_image_generation_calls(debug_metrics, run_id)
        self._build_execution_waves(debug_metrics, state, run_id)
        self._build_request_lifecycle(debug_metrics, run_id)
        self._build_llm_pipeline(debug_metrics, run_id)
        self._build_knowledge_enrichment(debug_metrics, state, run_id, settings)
        self._build_memory_injection(debug_metrics, state, run_id)
        self._build_rag_injection(debug_metrics, state, run_id)
        self._build_journal_injection(debug_metrics, state, run_id)
        self._build_journal_planner_injection(debug_metrics, state, run_id)
        self._build_skills(debug_metrics, state, run_id)
        stages.build_semantic_validation(debug_metrics, state)
        stages.build_react_execution(debug_metrics, state)
        stages.build_hitl(debug_metrics, state, hitl_interrupt)
        stages.build_compaction(debug_metrics, state)

    def _build_token_budget(
        self, debug_metrics: dict[str, Any], state: dict[str, Any], settings: Any
    ) -> None:
        # =================================================================
        # Token Budget: Calculate context size and determine zone
        # =================================================================
        try:
            from src.domains.agents.services.token_counter_service import (
                FallbackLevel,
                TokenCounterService,
            )

            token_counter = TokenCounterService(settings=settings)
            messages = state.get("messages", [])

            # Count tokens in messages
            message_tokens = token_counter.count_messages_tokens(messages)

            # Determine zone and strategy
            fallback_level = token_counter.get_fallback_level(message_tokens)

            # Map fallback level to zone
            zone_mapping = {
                FallbackLevel.FULL_CATALOGUE: "safe",
                FallbackLevel.FILTERED_CATALOGUE: "warning",
                FallbackLevel.REDUCED_DESCRIPTIONS: "warning",
                FallbackLevel.PRIMARY_DOMAIN_ONLY: "critical",
                FallbackLevel.SIMPLE_SEARCH: "emergency",
            }
            zone = zone_mapping.get(fallback_level, "safe")

            debug_metrics["token_budget"] = {
                "current_tokens": message_tokens,
                "thresholds": {
                    "safe": token_counter.threshold_safe,
                    "warning": token_counter.threshold_warning,
                    "critical": token_counter.threshold_critical,
                    "max": token_counter.threshold_max,
                },
                "zone": zone,
                "strategy": fallback_level,
                "fallback_active": fallback_level != FallbackLevel.FULL_CATALOGUE,
            }
        except (ImportError, ValueError, RuntimeError, AttributeError) as token_err:
            logger.debug(
                "debug_metrics_token_budget_failed",
                error=str(token_err),
                error_type=type(token_err).__name__,
            )

    def _build_planner_intelligence(
        self, debug_metrics: dict[str, Any], state: dict[str, Any]
    ) -> None:
        # =================================================================
        # Planner Intelligence: Strategy, tokens, corrections
        # =================================================================
        planning_result = state.get("planning_result")
        if planning_result is not None:
            # Determine strategy name
            if planning_result.used_template:
                strategy = "template_bypass"
            elif planning_result.used_panic_mode:
                strategy = "panic_mode"
            elif planning_result.used_generative:
                strategy = "generative"
            else:
                strategy = "filtered_catalogue"

            # Calculate token reduction percentage
            tokens_used = planning_result.tokens_used
            tokens_saved = planning_result.tokens_saved
            total_would_be = tokens_used + tokens_saved
            reduction_pct = (
                round((tokens_saved / total_would_be) * 100, 1) if total_would_be > 0 else 0
            )

            # Get plan details
            plan_details = {}
            if planning_result.plan:
                plan_details = {
                    "steps_count": len(planning_result.plan.steps),
                    "tools_used": [
                        step.tool_name
                        for step in planning_result.plan.steps
                        if hasattr(step, "tool_name")
                    ],
                    "estimated_cost_usd": (
                        planning_result.plan.estimated_cost
                        if hasattr(planning_result.plan, "estimated_cost")
                        else None
                    ),
                }

            debug_metrics["planner_intelligence"] = {
                "strategy": strategy,
                "tokens": {
                    "used": tokens_used,
                    "saved": tokens_saved,
                    "full_catalogue_estimate": total_would_be,
                    "reduction_percentage": reduction_pct,
                },
                "plan": plan_details,
                "flags": {
                    "used_template": planning_result.used_template,
                    "used_panic_mode": planning_result.used_panic_mode,
                    "used_generative": planning_result.used_generative,
                },
                "success": planning_result.success,
                "error": planning_result.error,
            }

    def _build_execution_timeline(
        self, debug_metrics: dict[str, Any], state: dict[str, Any], run_id: str
    ) -> None:
        # =================================================================
        # Execution Timeline: Collect step information from plan and results
        # =================================================================
        execution_plan = state.get("execution_plan")
        completed_steps = state.get("completed_steps", {})
        if execution_plan:
            try:
                timeline_steps = []
                for step in execution_plan.steps:
                    step_id = step.step_id if hasattr(step, "step_id") else str(id(step))
                    step_result = completed_steps.get(step_id, {})

                    # Extract domain from agent_name (e.g., "contacts_agent" → "contacts")
                    agent_name = getattr(step, "agent_name", None) or "unknown"
                    domain = (
                        agent_name.removesuffix("_agent") if agent_name != "unknown" else "unknown"
                    )

                    timeline_steps.append(
                        {
                            "step_id": step_id,
                            "tool_name": (
                                step.tool_name if hasattr(step, "tool_name") else "unknown"
                            ),
                            "domain": domain,
                            "status": "completed" if step_id in completed_steps else "pending",
                            "success": step_result.get("success", None),
                            "duration_ms": step_result.get("duration_ms", None),
                        }
                    )

                debug_metrics["execution_timeline"] = {
                    "steps": timeline_steps,
                    "total_steps": len(timeline_steps),
                    "completed_steps": len(completed_steps),
                }
            except (AttributeError, KeyError, ValueError, TypeError) as timeline_err:
                logger.debug(
                    "debug_metrics_execution_timeline_failed",
                    error=str(timeline_err),
                    error_type=type(timeline_err).__name__,
                )

    def _build_tool_selection(self, debug_metrics: dict[str, Any], run_id: str) -> None:
        # =================================================================
        # Tool Selection: Merge semantic scores + filtered catalogue
        # =================================================================
        # Like domain_selection: show ALL tools from domains (with scores)
        # + highlight which ones are actually selected (filtered catalogue)
        from src.core.config.agents import get_debug_thresholds

        filtered_catalogue = self._cached_filtered_catalogue
        tool_scores = self._cached_tool_scores

        logger.debug(
            "debug_metrics_tool_selection_check",
            run_id=run_id,
            has_filtered_catalogue=filtered_catalogue is not None,
            filtered_catalogue_tools_count=(
                len(filtered_catalogue.tools) if filtered_catalogue else 0
            ),
            has_tool_scores=tool_scores is not None,
            tool_scores_count=len(tool_scores.get("all_scores", {})) if tool_scores else 0,
        )

        if tool_scores:
            # Use selected_tools from tool_scores (tools that passed the > threshold filter)
            # This is the authoritative source from SemanticToolSelector
            selected_tools = tool_scores.get("selected_tools", [])

            # Fallback: if selected_tools not available, build from filtered_catalogue (legacy)
            if not selected_tools and filtered_catalogue:
                selected_tool_names = {t.get("name") for t in filtered_catalogue.tools}
                selected_tools = []
                for tool_name in selected_tool_names:
                    score = tool_scores["all_scores"].get(tool_name, 0.0)
                    selected_tools.append(
                        {
                            "tool_name": tool_name,
                            "score": round(score, 3),
                            "confidence": (
                                "high" if score >= 0.40 else ("medium" if score >= 0.15 else "low")
                            ),
                        }
                    )
                # Sort by score descending
                selected_tools.sort(key=lambda t: t["score"], reverse=True)

            thresholds = get_debug_thresholds()
            tool_th = thresholds.get("tool_selection", {})

            # Frontend-compatible format (like domain_selection)
            debug_metrics["tool_selection"] = {
                "selected_tools": selected_tools,
                "top_score": round(tool_scores["top_score"], 3),
                "has_uncertainty": tool_scores["has_uncertainty"],
                "all_scores": {
                    name: round(score, 3)
                    for name, score in sorted(
                        tool_scores["all_scores"].items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )
                },
                "thresholds": {
                    "softmax_temperature": {
                        "value": tool_th.get("softmax_temperature", 0.1),
                        "info": "Lower = sharper discrimination",
                    },
                    "primary_min": {
                        "value": tool_th.get("primary_min", 0.15),
                        "actual": round(tool_scores["top_score"], 3),
                        "passed": tool_scores["top_score"] >= tool_th.get("primary_min", 0.15),
                    },
                    "max_tools": {
                        "value": tool_th.get("max_tools", 8),
                        "info": f"Selected: {len(selected_tools)} from catalogue (filtered by intent), Scored: {len(tool_scores['all_scores'])} from domains",
                    },
                },
            }

            logger.debug(
                "debug_metrics_tool_selection_built",
                run_id=run_id,
                selected_count=len(selected_tools),
                scored_count=len(tool_scores["all_scores"]),
                top_score=tool_scores["top_score"],
            )

    def _build_llm_calls(
        self, debug_metrics: dict[str, Any], run_id: str, db_aggregated: Any | None
    ) -> None:
        # =================================================================
        # LLM Calls Breakdown: Per-node token consumption
        # =================================================================
        if self.tracker and hasattr(self.tracker, "get_llm_calls_breakdown"):
            try:
                llm_calls = self.tracker.get_llm_calls_breakdown()
                if llm_calls:
                    debug_metrics["llm_calls"] = llm_calls
                    debug_metrics["llm_summary"] = {
                        "total_calls": len(llm_calls),
                        "total_tokens_in": sum(c.get("tokens_in", 0) for c in llm_calls),
                        "total_tokens_out": sum(c.get("tokens_out", 0) for c in llm_calls),
                        "total_tokens_cache": sum(c.get("tokens_cache", 0) for c in llm_calls),
                        "total_cost_eur": round(sum(c.get("cost_eur", 0) for c in llm_calls), 6),
                    }
                    # v3.1: Update token_budget with REAL total from LLM calls
                    # v3.3: For HITL flows, the DB-aggregated summary includes
                    # ALL committed data (HITL request + post-approval + sub-agents).
                    # Use it when available as it's the most complete source.
                    # Fall back to in-memory run-level data for non-HITL flows.
                    if "token_budget" in debug_metrics:
                        tokens_in = debug_metrics["llm_summary"]["total_tokens_in"]
                        tokens_out = debug_metrics["llm_summary"]["total_tokens_out"]
                        tokens_cache = debug_metrics["llm_summary"]["total_tokens_cache"]
                        cost_eur = debug_metrics["llm_summary"]["total_cost_eur"]

                        # Use DB-aggregated totals if available and more complete
                        # The DB summary includes all committed data across HITL
                        # requests sharing the same run_id (UPSERT aggregation).
                        if db_aggregated:
                            db_total_in = getattr(db_aggregated, "tokens_in", 0)
                            db_total_out = getattr(db_aggregated, "tokens_out", 0)
                            db_total_cache = getattr(db_aggregated, "tokens_cache", 0)
                            db_cost_eur = float(getattr(db_aggregated, "cost_eur", 0.0))
                            db_total = db_total_in + db_total_out
                            mem_total = tokens_in + tokens_out
                            # Use DB if it has more data (includes prior HITL requests)
                            if db_total > mem_total:
                                tokens_in = db_total_in
                                tokens_out = db_total_out
                                tokens_cache = db_total_cache
                                cost_eur = round(db_cost_eur, 6)

                        debug_metrics["token_budget"]["total_consumed"] = tokens_in + tokens_out
                        debug_metrics["token_budget"]["tokens_input"] = tokens_in
                        debug_metrics["token_budget"]["tokens_output"] = tokens_out
                        debug_metrics["token_budget"]["tokens_cache"] = tokens_cache
                        debug_metrics["token_budget"]["total_cost_eur"] = cost_eur
            except (AttributeError, ValueError, RuntimeError) as llm_err:
                logger.debug(
                    "debug_metrics_llm_calls_failed",
                    run_id=run_id,
                    error=str(llm_err),
                    error_type=type(llm_err).__name__,
                )

    def _build_google_api_calls(self, debug_metrics: dict[str, Any], run_id: str) -> None:
        # =================================================================
        # Google API Calls Breakdown: Per-call details
        # =================================================================
        if self.tracker and hasattr(self.tracker, "get_google_api_calls_breakdown"):
            try:
                google_api_calls = self.tracker.get_google_api_calls_breakdown()
                if google_api_calls:
                    debug_metrics["google_api_calls"] = google_api_calls
                    # Summary stats
                    billable_calls = [c for c in google_api_calls if not c.get("cached", False)]
                    debug_metrics["google_api_summary"] = {
                        "total_calls": len(google_api_calls),
                        "billable_calls": len(billable_calls),
                        "cached_calls": len(google_api_calls) - len(billable_calls),
                        "total_cost_usd": round(
                            sum(c.get("cost_usd", 0) for c in billable_calls), 6
                        ),
                        "total_cost_eur": round(
                            sum(c.get("cost_eur", 0) for c in billable_calls), 6
                        ),
                    }
                    logger.debug(
                        "debug_metrics_google_api_calls_added",
                        run_id=run_id,
                        total_calls=len(google_api_calls),
                        billable_calls=len(billable_calls),
                    )
            except (AttributeError, ValueError, RuntimeError) as gapi_err:
                logger.debug(
                    "debug_metrics_google_api_calls_failed",
                    run_id=run_id,
                    error=str(gapi_err),
                    error_type=type(gapi_err).__name__,
                )

    def _build_image_generation_calls(self, debug_metrics: dict[str, Any], run_id: str) -> None:
        # =================================================================
        # Image Generation Calls Breakdown: Per-call details
        # =================================================================
        if self.tracker and hasattr(self.tracker, "get_image_generation_calls_breakdown"):
            try:
                image_gen_calls = self.tracker.get_image_generation_calls_breakdown()
                if image_gen_calls:
                    debug_metrics["image_generation_calls"] = image_gen_calls
                    debug_metrics["image_generation_summary"] = {
                        "total_calls": len(image_gen_calls),
                        "total_images": sum(c.get("image_count", 0) for c in image_gen_calls),
                        "total_cost_usd": round(
                            sum(c.get("cost_usd", 0) for c in image_gen_calls), 6
                        ),
                        "total_cost_eur": round(
                            sum(c.get("cost_eur", 0) for c in image_gen_calls), 6
                        ),
                    }

                    # Inject into llm_calls as a synthetic entry so it appears
                    # in LLM Pipeline and Execution Times in the debug panel
                    if "llm_calls" not in debug_metrics:
                        debug_metrics["llm_calls"] = []
                    for ig_call in image_gen_calls:
                        debug_metrics["llm_calls"].append(
                            {
                                "node_name": "image_generation",
                                "model_name": ig_call["model"],
                                "tokens_in": 0,
                                "tokens_out": 0,
                                "tokens_cache": 0,
                                "cost_eur": ig_call["cost_eur"],
                                "duration_ms": ig_call.get("duration_ms", 0),
                                "call_type": "image_generation",
                                # v3.4: real position on the run timeline; the
                                # sequence sentinel only orders legacy records
                                # that carry no offset.
                                "started_offset_ms": ig_call.get("started_offset_ms", 0.0),
                                "sequence": 9999,
                            }
                        )

                    logger.debug(
                        "debug_metrics_image_generation_calls_added",
                        run_id=run_id,
                        total_calls=len(image_gen_calls),
                    )
            except (AttributeError, ValueError, RuntimeError) as img_err:
                logger.debug(
                    "debug_metrics_image_generation_calls_failed",
                    run_id=run_id,
                    error=str(img_err),
                    error_type=type(img_err).__name__,
                )

    def _build_execution_waves(
        self, debug_metrics: dict[str, Any], state: dict[str, Any], run_id: str
    ) -> None:
        # =================================================================
        # Execution Waves: Parallel visualization (v3.1)
        # SYNC: DependencyGraph.get_wave_info() is pure computation, no I/O
        # =================================================================
        execution_plan = state.get("execution_plan")
        if execution_plan:
            try:
                from src.domains.agents.orchestration.dependency_graph import DependencyGraph

                graph = DependencyGraph(execution_plan)
                debug_metrics["execution_waves"] = graph.get_wave_info()
            except (ImportError, AttributeError, ValueError, RuntimeError) as wave_err:
                logger.debug(
                    "debug_metrics_execution_waves_failed",
                    run_id=run_id,
                    error=str(wave_err),
                    error_type=type(wave_err).__name__,
                )

    def _build_request_lifecycle(self, debug_metrics: dict[str, Any], run_id: str) -> None:
        # =================================================================
        # Request Lifecycle: Pipeline node progression (v3.2)
        # SYNC: Pure data transformation from already-collected llm_calls
        # Now includes duration_ms per node for execution time tracking
        # v3.4: nodes are ordered by their FIRST chronological appearance
        # (run-anchored started_offset_ms, sequence as legacy fallback) —
        # the old hardcoded node list appended react_*/compaction/extraction
        # nodes AFTER response, a false chronology.
        # =================================================================
        if "llm_calls" in debug_metrics:
            try:
                llm_calls_data = debug_metrics["llm_calls"]
                nodes_data: dict[str, dict[str, Any]] = {}
                first_seen: dict[str, tuple[float, int]] = {}

                for call in llm_calls_data:
                    node_name = call.get("node_name", "unknown")
                    if node_name not in nodes_data:
                        nodes_data[node_name] = {
                            "name": node_name,
                            "status": "completed",
                            "tokens_in": 0,
                            "tokens_out": 0,
                            "tokens_cache": 0,
                            "cost_eur": 0.0,
                            "calls_count": 0,
                            "duration_ms": 0.0,  # v3.2: Track execution time
                        }
                    nodes_data[node_name]["tokens_in"] += call.get("tokens_in", 0)
                    nodes_data[node_name]["tokens_out"] += call.get("tokens_out", 0)
                    nodes_data[node_name]["tokens_cache"] += call.get("tokens_cache", 0)
                    nodes_data[node_name]["cost_eur"] += call.get("cost_eur", 0.0)
                    nodes_data[node_name]["calls_count"] += 1
                    nodes_data[node_name]["duration_ms"] += call.get("duration_ms", 0.0)
                    key = _chrono_key(call)
                    if node_name not in first_seen or key < first_seen[node_name]:
                        first_seen[node_name] = key

                ordered_nodes: list[dict[str, Any]] = [
                    nodes_data[name] for name in sorted(nodes_data, key=lambda n: first_seen[n])
                ]

                # v3.2: Calculate total duration across all nodes
                total_duration_ms = sum(node.get("duration_ms", 0.0) for node in ordered_nodes)

                debug_metrics["request_lifecycle"] = {
                    "nodes": ordered_nodes,
                    "total_nodes": len(ordered_nodes),
                    "total_duration_ms": total_duration_ms,  # v3.2: Total LLM execution time
                }
            except (KeyError, TypeError, ValueError) as lifecycle_err:
                logger.debug(
                    "debug_metrics_request_lifecycle_failed",
                    run_id=run_id,
                    error=str(lifecycle_err),
                    error_type=type(lifecycle_err).__name__,
                )

    def _build_llm_pipeline(self, debug_metrics: dict[str, Any], run_id: str) -> None:
        # =================================================================
        # LLM Pipeline: Chronological reconciliation of ALL LLM calls (v3.3)
        # Provides a unified view of all LLM calls (chat + embedding) sorted
        # by execution order, with per-type breakdowns for the debug panel.
        # =================================================================
        if "llm_calls" in debug_metrics:
            try:
                # v3.4: run-anchored chronology. `sequence` alone collides
                # across the TrackingContexts sharing the run (each context
                # restarts at 1), so the offset leads and sequence only
                # breaks ties within one context (and legacy records).
                sorted_calls = sorted(debug_metrics["llm_calls"], key=_chrono_key)
                chat_calls = [c for c in sorted_calls if c.get("call_type", "chat") == "chat"]
                embedding_calls = [c for c in sorted_calls if c.get("call_type") == "embedding"]
                debug_metrics["llm_pipeline"] = {
                    "calls": sorted_calls,
                    "total_calls": len(sorted_calls),
                    "total_chat_calls": len(chat_calls),
                    "total_embedding_calls": len(embedding_calls),
                    "total_duration_ms": round(
                        sum(c.get("duration_ms", 0) for c in sorted_calls), 1
                    ),
                    "total_tokens_in": sum(c.get("tokens_in", 0) for c in sorted_calls),
                    "total_tokens_out": sum(c.get("tokens_out", 0) for c in sorted_calls),
                    "total_tokens_cache": sum(c.get("tokens_cache", 0) for c in sorted_calls),
                    "total_cost_eur": round(sum(c.get("cost_eur", 0) for c in sorted_calls), 6),
                }
            except (KeyError, TypeError, ValueError) as pipeline_err:
                logger.debug(
                    "debug_metrics_llm_pipeline_failed",
                    run_id=run_id,
                    error=str(pipeline_err),
                    error_type=type(pipeline_err).__name__,
                )

    def _build_knowledge_enrichment(
        self, debug_metrics: dict[str, Any], state: dict[str, Any], run_id: str, settings: Any
    ) -> None:
        # =================================================================
        # Knowledge Enrichment (Brave Search): Merge execution results
        # =================================================================
        # Base structure already created by QueryIntelligence.to_debug_metrics()
        # with encyclopedia_keywords and is_news_query. Here we enrich with
        # actual execution results from response_node.
        try:
            # Defensive check: ensure knowledge_enrichment section exists
            # (may not exist if query_intelligence was None during to_debug_metrics())
            if "knowledge_enrichment" not in debug_metrics:
                debug_metrics["knowledge_enrichment"] = {
                    "enabled": settings.knowledge_enrichment_enabled,
                    "executed": False,
                    "encyclopedia_keywords": [],
                    "is_news_query": False,
                }

            # Get knowledge_enrichment_result from state (set by response_node)
            enrichment_result = state.get("knowledge_enrichment_result") if state else None

            # Update the enabled field with actual settings value
            debug_metrics["knowledge_enrichment"]["enabled"] = settings.knowledge_enrichment_enabled

            if enrichment_result:
                # Determine if enrichment was actually executed (API called)
                # vs skipped (skip_reason present without endpoint/error)
                has_api_result = enrichment_result.get("endpoint") is not None
                has_api_error = enrichment_result.get("error") is not None
                was_executed = has_api_result or has_api_error

                debug_metrics["knowledge_enrichment"]["executed"] = was_executed
                debug_metrics["knowledge_enrichment"]["endpoint"] = enrichment_result.get(
                    "endpoint"
                )
                debug_metrics["knowledge_enrichment"]["keyword_used"] = enrichment_result.get(
                    "keyword_used"
                )
                debug_metrics["knowledge_enrichment"]["results_count"] = enrichment_result.get(
                    "results_count"
                )
                debug_metrics["knowledge_enrichment"]["from_cache"] = enrichment_result.get(
                    "from_cache"
                )
                debug_metrics["knowledge_enrichment"]["skip_reason"] = enrichment_result.get(
                    "skip_reason"
                )
                debug_metrics["knowledge_enrichment"]["error"] = enrichment_result.get("error")
                # Include actual results for debugging (title, description, url)
                debug_metrics["knowledge_enrichment"]["results"] = enrichment_result.get("results")
                # Include the formatted context that was injected into the LLM prompt
                debug_metrics["knowledge_enrichment"]["prompt_context"] = enrichment_result.get(
                    "prompt_context"
                )
            else:
                # Enrichment was not executed (feature disabled, no keywords, etc.)
                debug_metrics["knowledge_enrichment"]["executed"] = False
                if not settings.knowledge_enrichment_enabled:
                    debug_metrics["knowledge_enrichment"]["skip_reason"] = "feature_disabled"
                elif not debug_metrics["knowledge_enrichment"].get("encyclopedia_keywords"):
                    debug_metrics["knowledge_enrichment"]["skip_reason"] = "no_keywords"

            logger.debug(
                "debug_metrics_knowledge_enrichment_built",
                run_id=run_id,
                executed=debug_metrics["knowledge_enrichment"]["executed"],
                endpoint=debug_metrics["knowledge_enrichment"].get("endpoint"),
                results_count=debug_metrics["knowledge_enrichment"].get("results_count"),
            )
        except (KeyError, TypeError, AttributeError) as ke_err:
            logger.debug(
                "debug_metrics_knowledge_enrichment_failed",
                run_id=run_id,
                error=str(ke_err),
                error_type=type(ke_err).__name__,
            )

    def _build_memory_injection(
        self, debug_metrics: dict[str, Any], state: dict[str, Any], run_id: str
    ) -> None:
        # =================================================================
        # Memory Injection: Injected memories with scores for tuning
        # =================================================================
        try:
            memory_debug = state.get("memory_injection_debug") if state else None
            if memory_debug:
                debug_metrics["memory_injection"] = memory_debug
                logger.debug(
                    "debug_metrics_memory_injection_added",
                    run_id=run_id,
                    memory_count=memory_debug.get("memory_count", 0),
                    emotional_state=memory_debug.get("emotional_state"),
                )
        except (KeyError, TypeError, AttributeError) as mem_err:
            logger.debug(
                "debug_metrics_memory_injection_failed",
                run_id=run_id,
                error=str(mem_err),
                error_type=type(mem_err).__name__,
            )

    def _build_rag_injection(
        self, debug_metrics: dict[str, Any], state: dict[str, Any], run_id: str
    ) -> None:
        # =================================================================
        # RAG Injection: Injected RAG chunks with scores for debug panel
        # =================================================================
        try:
            rag_debug = state.get("rag_injection_debug") if state else None
            if rag_debug:
                debug_metrics["rag_injection"] = rag_debug
                logger.debug(
                    "debug_metrics_rag_injection_added",
                    run_id=run_id,
                    spaces_searched=rag_debug.get("spaces_searched", 0),
                    chunks_injected=rag_debug.get("chunks_injected", 0),
                )
        except (KeyError, TypeError, AttributeError) as rag_err:
            logger.debug(
                "debug_metrics_rag_injection_failed",
                run_id=run_id,
                error=str(rag_err),
                error_type=type(rag_err).__name__,
            )

    def _build_journal_injection(
        self, debug_metrics: dict[str, Any], state: dict[str, Any], run_id: str
    ) -> None:
        # =================================================================
        # Journal Injection (Response): Journal entries with scores for debug panel
        # =================================================================
        try:
            journal_debug = state.get("journal_injection_debug") if state else None
            if journal_debug:
                debug_metrics["journal_injection"] = journal_debug
                logger.info(
                    "debug_metrics_journal_injection_added",
                    run_id=run_id,
                    entries_found=journal_debug.get("entries_found", 0),
                    entries_injected=journal_debug.get("entries_injected", 0),
                    entries_count=len(journal_debug.get("entries", [])),
                )
            else:
                logger.info(
                    "debug_metrics_journal_injection_missing",
                    run_id=run_id,
                    state_keys=list(state.keys()) if state else [],
                )
        except (KeyError, TypeError, AttributeError) as journal_err:
            logger.debug(
                "debug_metrics_journal_injection_failed",
                run_id=run_id,
                error=str(journal_err),
                error_type=type(journal_err).__name__,
            )

    def _build_journal_planner_injection(
        self, debug_metrics: dict[str, Any], state: dict[str, Any], run_id: str
    ) -> None:
        # =================================================================
        # Journal Injection (Planner): Journal entries injected into planner context
        # =================================================================
        try:
            journal_planner_debug = state.get("journal_planner_injection_debug") if state else None
            if journal_planner_debug:
                debug_metrics["journal_planner_injection"] = journal_planner_debug
                logger.info(
                    "debug_metrics_journal_planner_injection_added",
                    run_id=run_id,
                    entries_found=journal_planner_debug.get("entries_found", 0),
                    entries_injected=journal_planner_debug.get("entries_injected", 0),
                    entries_count=len(journal_planner_debug.get("entries", [])),
                )
        except (KeyError, TypeError, AttributeError) as journal_planner_err:
            logger.debug(
                "debug_metrics_journal_planner_injection_failed",
                run_id=run_id,
                error=str(journal_planner_err),
                error_type=type(journal_planner_err).__name__,
            )

    def _build_skills(
        self, debug_metrics: dict[str, Any], state: dict[str, Any], run_id: str
    ) -> None:
        # =================================================================
        # Skills: Skill activation details for debug panel
        # =================================================================
        planning_result = state.get("planning_result")
        try:
            # Route 3 (conversation fallback): detect activate_skill_tool calls
            # from messages (shared helper — also used for the done metadata).
            effective_skill_name = self._resolve_skill_name(state)

            if effective_skill_name:
                from src.domains.skills.cache import SkillsCache

                skill_data = SkillsCache.get_by_name(effective_skill_name)
                is_deterministic = False

                # Determine activation mode (every branch below assigns it)
                if planning_result and planning_result.plan and planning_result.plan.metadata:
                    if planning_result.plan.metadata.get("skill_bypass"):
                        activation_mode = "bypass"
                    elif planning_result.plan.metadata.get("skill_name"):
                        activation_mode = "planner"
                    else:
                        # Route 3: LLM called activate_skill_tool directly
                        activation_mode = "tool"
                    is_deterministic = bool(planning_result.plan.metadata.get("skill_bypass"))
                else:
                    # Route 3: no plan → LLM called activate_skill_tool
                    activation_mode = "tool"

                skills_debug: dict[str, Any] = {
                    "activated": True,
                    "skill_name": effective_skill_name,
                    "activation_mode": activation_mode,
                    "is_deterministic": is_deterministic,
                }
                if skill_data:
                    skills_debug["category"] = skill_data.get("category")
                    skills_debug["priority"] = skill_data.get("priority", 50)
                    skills_debug["has_scripts"] = bool(skill_data.get("scripts"))
                    skills_debug["has_references"] = bool(skill_data.get("references"))
                    skills_debug["scope"] = skill_data.get("scope", "admin")

                debug_metrics["skills"] = skills_debug
                logger.debug(
                    "debug_metrics_skills_added",
                    run_id=run_id,
                    skill_name=effective_skill_name,
                    activation_mode=activation_mode,
                )
        except (KeyError, TypeError, AttributeError) as skill_err:
            logger.debug(
                "debug_metrics_skills_failed",
                run_id=run_id,
                error=str(skill_err),
                error_type=type(skill_err).__name__,
            )
