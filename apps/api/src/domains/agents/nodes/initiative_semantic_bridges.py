"""Project available semantic pivots into initiative connection candidates."""

from collections.abc import Sequence

from src.core.context import get_request_tool_manifests, request_tool_manifests_ctx
from src.domains.agents.nodes.jev_initiative_context import (
    InitiativeSemanticContext,
    semantic_bridge_line,
)
from src.domains.agents.nodes.jev_initiative_evidence import InitiativeEvidence
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.semantic.expansion_service import (
    collect_manifest_output_providers,
    collect_manifest_param_consumers,
)
from src.domains.agents.semantic.semantic_type import is_semantic_pivot
from src.domains.agents.semantic.type_registry import TypeRegistry


def build_semantic_candidate_lines(
    registry: TypeRegistry,
    executed_domains: Sequence[str],
    adjacent_manifests: Sequence[ToolManifest],
    evidence: InitiativeEvidence,
    native: InitiativeSemanticContext,
) -> list[str]:
    """Keep directional data links while rejecting generic text/number matches.

    Annotation describes a value's meaning; an unqualified text or quantity
    cannot identify a useful connection between two domains. Native context
    retains every genuine candidate before the prompt's rendering caps apply.
    """
    adjacent_tool_names = {manifest.name for manifest in adjacent_manifests}
    executed_set = set(executed_domains)
    manifest_consumers = collect_manifest_param_consumers(list(adjacent_manifests))
    manifest_providers = collect_manifest_output_providers(get_request_tool_manifests())
    request_scoped = request_tool_manifests_ctx.get() is not None
    produced_types: set[str] = set()
    if not request_scoped:
        for domain in executed_domains:
            produced_types |= registry.get_by_domain(domain)
    produced_types.update(
        type_name for type_name, providers in manifest_providers.items() if providers & executed_set
    )
    lines: list[str] = []
    for type_name in sorted(produced_types):
        if not is_semantic_pivot(type_name):
            continue
        type_def = registry.get(type_name)
        if not type_def:
            native.complete = False
            continue
        consumers = sorted(
            (
                (set() if request_scoped else set(type_def.used_in_tools))
                | manifest_consumers.get(type_name, set())
            )
            & adjacent_tool_names
        )
        if not consumers:
            continue
        providers = sorted(
            (
                (set() if request_scoped else set(type_def.source_domains))
                | manifest_providers.get(type_name, set())
            )
            & executed_set
        )
        lines.append(semantic_bridge_line(type_name, providers, consumers, evidence, native))
    return lines
