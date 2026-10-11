"""Request-scoped semantic domain expansion used by the query analyzer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from structlog.stdlib import BoundLogger

from src.core.config import Settings

if TYPE_CHECKING:
    from src.domains.agents.semantic.expansion_service import SemanticExpansionService


def _required_semantic_types(domains: list[str]) -> set[str]:
    """Read required types from the request catalogue, then the global fallback."""
    from src.core.context import get_request_tool_manifests, request_tool_manifests_ctx
    from src.domains.agents.registry.agent_registry import get_global_registry
    from src.domains.agents.semantic.manifest_semantics import parameter_semantic_types

    if request_tool_manifests_ctx.get() is not None:
        return {
            type_name
            for manifest in get_request_tool_manifests()
            if manifest.agent.removesuffix("_agent") in domains
            for param in manifest.parameters
            for type_name in parameter_semantic_types(param)
        }
    return set(get_global_registry().get_required_semantic_types_for_domains(domains))


async def _expand_with_evidence(
    service: SemanticExpansionService,
    domains: list[str],
    required_types: set[str],
    has_person_reference: bool,
    evidence_entities: set[str] | None,
    configuration: Settings,
) -> list[str]:
    if configuration.semantic_expansion_evidence_driven_enabled:
        return await service.expand_domains_evidence_driven(
            domains=domains,
            evidence_entities=evidence_entities or set(),
            required_semantic_types=required_types,
            max_added_domains=configuration.semantic_expansion_max_added_domains,
            query="",
        )
    return await service.expand_domains_iso_functional(
        domains=domains,
        has_person_reference=has_person_reference,
        required_semantic_types=required_types,
        query="",
    )


def _append_expansion_reasons(
    service: SemanticExpansionService,
    domains: list[str],
    expanded_domains: list[str],
    required_types: set[str],
    reasons: list[str],
) -> list[str]:
    added_domains = [domain for domain in expanded_domains if domain not in domains]
    for added_domain in added_domains:
        provided_types = sorted(
            type_name
            for type_name in required_types
            if added_domain in service.get_providers_for_type(type_name)
        )
        if provided_types:
            reasons.append(
                f"{added_domain} (provides {', '.join(provided_types)} for referenced entity)"
            )
    return added_domains


async def expand_domains_for_semantic_types(
    domains: list[str],
    has_person_reference: bool,
    reasoning_trace: list[str],
    all_scores: dict[str, float] | None = None,
    expansion_reasons: list[str] | None = None,
    evidence_entities: set[str] | None = None,
    *,
    configuration: Settings,
    logger: BoundLogger,
) -> list[str]:
    """
    Expand domains based on semantic type requirements.

    Example: "route to my brother's" → route requires physical_address +
    person evidence (memory resolver or analyzer LLM) → add contact.

    Two modes (SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED):
    - OFF (default): historical iso-functional person→contact expansion.
    - ON: evidence-driven expansion — every referenced entity (person,
      event, place) whose ontology properties provide a required type
      adds its source domains (capped). For person-only evidence the
      outcome is identical to the iso path (Contact → contact).
    """
    if not domains:
        return domains

    try:
        from src.domains.agents.semantic.expansion_service import (
            get_expansion_service,
        )

        required_type_names = _required_semantic_types(domains)
        if not required_type_names:
            return domains

        expansion_service = get_expansion_service()

        expanded_domains = await _expand_with_evidence(
            expansion_service,
            domains,
            required_type_names,
            has_person_reference,
            evidence_entities,
            configuration,
        )

        # Build reasons list for logging
        reasons = expansion_reasons if expansion_reasons is not None else []
        added_domains = _append_expansion_reasons(
            expansion_service,
            domains,
            expanded_domains,
            required_type_names,
            reasons,
        )

        if added_domains:
            logger.info(
                "semantic_type_domain_expansion",
                original_domains=domains,
                expanded_domains=expanded_domains,
                added_domains=added_domains,
                reasons=reasons,
                has_person_reference=has_person_reference,
            )
            reasoning_trace.append(f"Semantic type expansion: +{reasons}")

        return expanded_domains

    except Exception as e:
        logger.warning(
            "semantic_type_expansion_failed",
            error=str(e),
            domains=domains,
        )
        return domains
