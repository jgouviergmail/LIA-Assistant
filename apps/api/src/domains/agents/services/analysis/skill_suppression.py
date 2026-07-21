"""Skill-detection suppression on MCP-domain turns.

The defect this closes (proved in production, 2026-07-21 18:15-18:23): the
QueryAnalyzer LLM fills ``domains`` and ``skill_name`` in ONE structured
output, and nothing kept them coherent. Three consecutive diagram requests
were analyzed ``primary_domain=mcp_excalidraw`` at 0.95 confidence, yet
``skill_name`` came back as ``interactive-map`` (the user received the water
cycle **on a Google Maps embed**), then ``skill-generator`` (a failed skill
import dumping inline SVG into the chat), then the hallucinated
``"mcp_excalidraw"`` — which only reached the correct MCP task path because
that skill does not exist. The routing decider gives ``detected_skill_name``
absolute priority ("independently of the domains list"), so the contradiction
must be resolved BEFORE the name reaches it — and before it is stored on
``QueryIntelligence``, whose ``detected_skill_name`` is read again by the
planner bypass and the response node.

Scope decisions:

- **Primary domain only.** The proven defect had ``domains == ["mcp_<x>"]``;
  a secondary MCP domain describes a mixed request where a skill may be the
  legitimate main act. Narrower guard, fewer collateral suppressions.
- **ADR-118 exemption.** Mid-dialogue answers to a dialogue skill's own
  questions may legitimately mention an MCP surface ("un skill qui utilise
  excalidraw"). The exemption reuses the exact predicate the chat override
  already applies (``intent == "conversation"`` and the skill declares
  ``dialogue: true``) — a fresh imperative request (intent action/search)
  stays suppressed even for a dialogue skill, which is precisely the
  ``skill-generator`` production case.

Every suppression is logged and counted, so any collateral damage on
legitimate mixed requests is observable instead of silent.
"""

from __future__ import annotations

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _is_dialogue_skill(skill_name: str | None) -> bool:
    """Return True when ``skill_name`` declares the ``dialogue: true`` extension.

    Dialogue skills (ADR-118, e.g. skill-generator) run a multi-turn process:
    the user's answers to the skill's own questions are legitimately
    conversational, so the chat override must NOT clear the detected
    skill_name for them — clearing is what breaks the dialogue across turns.
    One-shot skills keep the anti-contamination behavior.

    Args:
        skill_name: Skill name detected by the analyzer LLM (may be None).

    Returns:
        True only when the skill exists in the cache and opts into dialogue.
    """
    if not skill_name:
        return False
    from src.domains.skills.cache import SkillsCache

    skill = SkillsCache.get_by_name(skill_name)
    return bool(skill and skill.get("dialogue"))


def effective_skill_name(
    skill_name: str | None,
    domains: list[str],
    intent: str,
) -> str | None:
    """Resolve the LLM's skill detection against its own domain verdict.

    Args:
        skill_name: ``skill_name`` from the analyzer's structured output.
        domains: Detected domains, primary first (post context-coherence).
        intent: ``immediate_intent`` from the same output — drives the
            ADR-118 dialogue exemption.

    Returns:
        The skill name to act on, or None when the detection is suppressed
        because the primary domain is an MCP domain (see module docstring).
    """
    from src.domains.agents.registry.domain_taxonomy import is_mcp_domain

    if not skill_name or not domains or not is_mcp_domain(domains[0]):
        return skill_name
    if intent == "conversation" and _is_dialogue_skill(skill_name):
        logger.info(
            "skill_detection_kept_dialogue_over_mcp",
            skill_name=skill_name,
            primary_domain=domains[0],
            intent=intent,
        )
        return skill_name

    from src.infrastructure.observability.metrics_registry import (
        skill_detection_suppressed_total,
    )

    logger.info(
        "skill_detection_suppressed_mcp_domain",
        skill_name=skill_name,
        primary_domain=domains[0],
        intent=intent,
        msg="LLM filled skill_name against its own MCP-domain verdict",
    )
    skill_detection_suppressed_total.labels(reason="mcp_domain").inc()
    return None
