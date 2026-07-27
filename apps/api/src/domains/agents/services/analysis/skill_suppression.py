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

from typing import Final

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Textual stand-ins an LLM writes when it means "no value". Kept local rather
# than in core/constants.py — like the parallel executor's timeout policy, this
# is an implementation detail of ONE output parser, not a domain-level default
# an operator would ever tune. Compared lowercase, after stripping.
_SENTINEL_SKILL_NAMES: Final[frozenset[str]] = frozenset(
    {"null", "none", "nil", "n/a", "na", "undefined", "false", "-"}
)


def normalize_skill_name(raw: str | None) -> str | None:
    """Strip a raw LLM ``skill_name`` and map textual "no value" to ``None``.

    Applied at the parsing boundary (``QueryAnalysisOutput``) so that every
    downstream ``if skill_name:`` sees a genuine detection, and again inside
    :func:`effective_skill_name` for callers that build the value themselves.

    Args:
        raw: Value as emitted by the analyzer LLM.

    Returns:
        The stripped name, or None when it is blank or a sentinel.
    """
    name = (raw or "").strip()
    if not name or name.lower() in _SENTINEL_SKILL_NAMES:
        return None
    return name


def metric_skill_label(name: str, user_id: str) -> str:
    """Map a skill name onto a bounded Prometheus label value.

    System skills are a closed, curated set, so their names are safe labels.
    User-imported names are user-controlled free text: labelling by them would
    grow the series count with every import, times every domain — the classic
    cardinality explosion, and a way to smuggle user data into metrics. They
    collapse to a single bucket; the log line beside the counter keeps the real
    name for diagnosis.

    Args:
        name: Normalised skill name.
        user_id: Owner scope used to resolve the skill.

    Returns:
        The name for a system skill, ``"_user"`` otherwise.
    """
    from src.domains.skills.cache import SkillsCache

    entry = SkillsCache.get_by_name_for_user(name, user_id)
    if entry is not None and SkillsCache.entry_is_system(entry):
        return name
    return "_user"


def _retained(name: str, domains: list[str], intent: str, user_id: str) -> str:
    """Record a detection that survived every filter, then return it.

    Single observable exit point. The suppression counters only describe what
    was discarded; without this one there is nothing to correlate a recurrence
    of the 2026-07-27 ``skill-generator`` hijack against — that trigger was
    never reproduced (0 hits in 104 probes vs 4 in 6 production turns), so the
    kept detections are the only remaining signal.

    Args:
        name: Normalised skill name being kept.
        domains: Detected domains, primary first.
        intent: ``immediate_intent`` from the analyzer.
        user_id: Owner scope, used to bound the metric label.

    Returns:
        ``name`` unchanged.
    """
    from src.infrastructure.observability.metrics_registry import skill_detection_retained_total

    primary_domain = domains[0] if domains else "none"
    logger.info(
        "skill_detection_retained",
        skill_name=name,
        primary_domain=primary_domain,
        intent=intent,
    )
    skill_detection_retained_total.labels(
        skill_name=metric_skill_label(name, user_id),
        primary_domain=primary_domain,
    ).inc()
    return name


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
    *,
    user_id: str = "",
) -> str | None:
    """Resolve the LLM's skill detection against reality, then against its own
    domain verdict.

    Three filters, in order of increasing cost:

    1. **Sentinel text.** The prompt asks the model to "leave it null"; a
       non-strict structured output writes the four characters ``null``, which
       is truthy. Measured 2026-07-27: 84-100% of analyses on a plain image
       request came back that way.
    2. **Existence.** A name matching no skill reachable by this user is a
       hallucination. The router gives ``detected_skill_name`` absolute
       priority, so an unreachable name steers the turn towards a skill that
       cannot run.
    3. **MCP-domain coherence** (the original guard, see module docstring).

    Note the ordering moved the hallucinated-name case: ``mcp_excalidraw`` on an
    MCP turn used to be counted ``reason="mcp_domain"``, and now lands on
    ``reason="unknown_skill"`` — the same suppression, attributed to the reason
    that actually applies. ``mcp_domain`` therefore counts only real skills
    fired against an MCP verdict, which is what makes it readable.

    Args:
        skill_name: ``skill_name`` from the analyzer's structured output.
        domains: Detected domains, primary first (post context-coherence).
        intent: ``immediate_intent`` from the same output — drives the
            ADR-118 dialogue exemption.
        user_id: Owner scope for the existence check. User skills override
            admin ones and are never reachable across users; the empty default
            resolves admin-scoped skills only.

    Returns:
        The normalised skill name to act on, or None when the detection is
        suppressed by any of the three filters.
    """
    from src.domains.agents.registry.domain_taxonomy import is_mcp_domain
    from src.infrastructure.observability.metrics_registry import (
        skill_detection_suppressed_total,
    )

    name = normalize_skill_name(skill_name)
    if name is None:
        if (skill_name or "").strip():
            logger.info(
                "skill_detection_suppressed_sentinel_name",
                skill_name=skill_name,
                msg="LLM wrote a textual null instead of an absent value",
            )
            skill_detection_suppressed_total.labels(reason="sentinel_name").inc()
        return None

    from src.domains.skills.cache import SkillsCache

    # Fail open on an unloaded cache: "no entries yet" is a boot-window state,
    # not evidence that the skill does not exist. Suppressing there would
    # disable every skill instead of surfacing the real problem.
    if SkillsCache.is_loaded() and SkillsCache.get_by_name_for_user(name, user_id) is None:
        logger.info(
            "skill_detection_suppressed_unknown_skill",
            skill_name=name,
            msg="LLM named a skill that does not exist for this user",
        )
        skill_detection_suppressed_total.labels(reason="unknown_skill").inc()
        return None

    if domains and is_mcp_domain(domains[0]):
        if not (intent == "conversation" and _is_dialogue_skill(name)):
            logger.info(
                "skill_detection_suppressed_mcp_domain",
                skill_name=name,
                primary_domain=domains[0],
                intent=intent,
                msg="LLM filled skill_name against its own MCP-domain verdict",
            )
            skill_detection_suppressed_total.labels(reason="mcp_domain").inc()
            return None
        logger.info(
            "skill_detection_kept_dialogue_over_mcp",
            skill_name=name,
            primary_domain=domains[0],
            intent=intent,
        )

    return _retained(name, domains, intent, user_id)
