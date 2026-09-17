"""Semantic tool scoring of a turn — ONE embedding, two readers.

The router pays one query embedding per actionable turn. It used to feed the
planner alone: calibrated scores over the DETECTED domains' tools, which the
catalogue thresholds and caps. The ReAct loop, which binds many tools, had no
ranking at all and cut its cap in registration order — on any account with
more tools than the cap, the same tools were invisible on every turn,
whatever the question (measured on a dev instance, 2026-09-17).

This module keeps the planner's scores exactly as they were and adds, from the
SAME embedding, the global order of every available manifest — user MCP tools
included through their per-request vectors. Both live in the turn's
``tool_selection_result`` (a dict of ``MessagesState``, no new key).
"""

from __future__ import annotations

from typing import Any

from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: The key under which the global relevance order travels in ``tool_selection_result``.
GLOBAL_RANKING_KEY = "global_ranking"


def _domain_manifests(manifests: list[Any], domains: list[str]) -> list[Any]:
    """The manifests whose agent owns one of the detected domains (the planner's view)."""
    return [
        m
        for m in manifests
        if (m.agent.removesuffix("_agent") if hasattr(m, "agent") else "") in domains
    ]


def _mcp_vectors(domains: list[str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """The user's per-request MCP vectors: all of them for the ranking, gated for the planner.

    Returns:
        ``(every_vector, planner_view)`` — the planner reads them only when an
        MCP domain was detected, exactly as before; the global ranking reads
        them always, or those tools could never rank.
    """
    from src.core.context import user_mcp_tools_ctx
    from src.domains.agents.registry.domain_taxonomy import is_mcp_domain

    user_ctx = user_mcp_tools_ctx.get()
    vectors = user_ctx.tool_embeddings if user_ctx and user_ctx.tool_embeddings else None
    gated = vectors if vectors and any(is_mcp_domain(d) for d in domains) else None
    return vectors, gated


async def score_tools_for_turn(
    intelligence: QueryIntelligence, run_id: str
) -> dict[str, Any] | None:
    """Score the turn's tools once: the planner's domain scores and the global order.

    Args:
        intelligence: The router's query intelligence (domains, English pivot).
        run_id: Correlation id for the logs.

    Returns:
        The ``tool_selection_result`` dict, or None when the turn is not
        actionable, carries no English pivot, the selector is not initialized,
        or the scoring failed — every reader treats None as « no scores »,
        exactly as before this module existed. The planner's domain scores
        need detected domains; the global order needs only the question, so
        an actionable turn the router could not place in a domain — where the
        loop used to bind everything — is ranked all the same.
    """
    if intelligence.route_to != "planner" or not intelligence.english_query:
        return None
    try:
        from src.core.context import get_request_tool_manifests
        from src.domains.agents.services.tool_selector import get_tool_selector

        selector = await get_tool_selector()
        if not selector.is_initialized():
            return None
        all_manifests = get_request_tool_manifests()
        domain_tool_manifests = _domain_manifests(all_manifests, intelligence.domains)
        # The per-request vectors of the user's MCP tools: the planner's domain
        # scores read them only when an MCP domain was detected (unchanged);
        # the global order reads them always, or those tools could never rank.
        mcp_embeddings, domain_extra = _mcp_vectors(intelligence.domains)
        embedding = await selector.embed_query(intelligence.english_query)
        scores: dict[str, Any] = {
            GLOBAL_RANKING_KEY: selector.rank_tools(
                embedding, all_manifests, extra_embeddings=mcp_embeddings
            )
        }
        if domain_tool_manifests:
            result = await selector.select_tools(
                query=intelligence.english_query,
                available_tools=domain_tool_manifests,
                extra_embeddings=domain_extra,
                query_embedding=embedding,
            )
            scores.update(
                {
                    "all_scores": result.all_scores,  # For debug panel (all calibrated scores)
                    "selected_tools": [  # Only tools that passed the > threshold filter
                        {
                            "tool_name": t.tool_name,
                            "score": round(t.score, 3),
                            "confidence": t.confidence,
                        }
                        for t in result.selected_tools
                    ],
                    "top_score": result.top_score,
                    "has_uncertainty": result.has_uncertainty,
                }
            )
        logger.info(
            "router_v3_tool_scores_computed",
            run_id=run_id,
            domains=intelligence.domains,
            tools_scored=len(domain_tool_manifests),
            tools_ranked=len(scores[GLOBAL_RANKING_KEY]),
            top_score=round(float(scores.get("top_score", 0.0)), 3),
        )
        return scores
    except Exception as e:
        logger.warning("router_v3_tool_scoring_failed", run_id=run_id, error=str(e))
        return None


__all__ = ["GLOBAL_RANKING_KEY", "score_tools_for_turn"]
