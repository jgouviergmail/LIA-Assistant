"""Complete model-authorized initiative evidence, scoped to results retrieved this turn."""

import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, cast

from pydantic import JsonValue

from src.core.constants import SEMANTIC_CANDIDATES_MAX_TOOLS_PER_TYPE
from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemType
from src.domains.agents.display.model_history import _json_default
from src.domains.agents.nodes.jev_initiative_evidence import InitiativeEvidence
from src.domains.agents.orchestration.schemas import AgentResult
from src.domains.agents.registry.catalogue import ToolManifest


@dataclass
class InitiativeSemanticContext:
    """Directional bridges before the generative prompt's presentation caps."""

    bridges: list[dict[str, JsonValue]] = field(default_factory=list)
    complete: bool = True
    enabled: bool = True


def semantic_bridge_line(
    type_name: str,
    providers: list[str],
    consumers: list[str],
    evidence: InitiativeEvidence,
    native: InitiativeSemanticContext,
) -> str:
    native.bridges.append(
        {"semantic_type": type_name, "source_domains": providers, "consumer_tools": consumers}
    )
    providers_str = ", ".join(providers) if providers else "execution"
    tools_str = ", ".join(consumers[:SEMANTIC_CANDIDATES_MAX_TOOLS_PER_TYPE])
    omitted = len(consumers) - SEMANTIC_CANDIDATES_MAX_TOOLS_PER_TYPE
    if omitted > 0:
        evidence.omit("semantic_bridges_omitted", omitted)
        tools_str += f" (+{omitted} more)"
    return f"- {type_name} (from {providers_str} results) → consumable by: {tools_str}"


def _is_registry_representation(value: dict[str, Any]) -> bool:
    """Recognize the application envelope, not arbitrary provider payload/meta objects."""
    meta = value.get("meta")
    item_type = value.get("type")
    return (
        isinstance(value.get("id"), str)
        and isinstance(item_type, str)
        and item_type in {kind.value for kind in RegistryItemType}
        and isinstance(value.get("payload"), dict)
        and isinstance(meta, dict)
        and isinstance(meta.get("source"), str)
    )


def _without_card_fields(value: dict[str, Any]) -> dict[str, Any]:
    projected = {key: item for key, item in value.items() if key != FIELD_DISPLAY_ONLY}
    meta = projected.get("meta")
    if _is_registry_representation(projected) and isinstance(meta, dict):
        projected["meta"] = {key: item for key, item in meta.items() if key != "display"}
    return projected


def _authorized_tree(value: Any, evidence: InitiativeEvidence) -> Any:
    """Card-only fields remain inaccessible even inside nested registry_updates."""
    if isinstance(value, RegistryItem | AgentResult):
        # Remove card-only subtrees, including opaque values, before strict JSON encoding.
        value = value.model_dump(mode="python")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("Nonfinite numeric evidence")
    if isinstance(value, list | tuple):
        return [_authorized_tree(item, evidence) for item in value]
    if not isinstance(value, dict):
        return value
    projected = _without_card_fields(value)
    if projected.get("truncated") is True:
        evidence.omit("source_truncated")
    return {key: _authorized_tree(item, evidence) for key, item in projected.items()}


def _tool_contract(manifest: ToolManifest) -> dict[str, object]:
    return {
        "name": manifest.name,
        "agent": manifest.agent,
        "description": manifest.description,
        "parameters": [asdict(parameter) for parameter in manifest.parameters],
        "outputs": [asdict(output) for output in manifest.outputs],
        "permissions": asdict(manifest.permissions),
    }


def _current_registry(
    registry: dict[str, Any], turn_id: int | None, is_current: bool, evidence: InitiativeEvidence
) -> dict[str, Any]:
    selected = {}
    for key, item in registry.items():
        meta = item.meta if isinstance(item, RegistryItem) else item.get("meta", {})
        source_turn = meta.turn_id if hasattr(meta, "turn_id") else meta.get("turn_id")
        if source_turn is not None and turn_id is not None:
            if source_turn == turn_id:
                selected[key] = item
        elif is_current:
            selected[key] = item
        else:
            evidence.omit("context_unavailable")
    return selected


def canonical_initiative_context(
    *,
    arguments: dict[str, JsonValue],
    registry: dict[str, Any],
    agent_results: dict[str, Any],
    current_turn_id: int | None,
    memory_facts: list[str] | None,
    interest_profile: dict[str, Any],
    manifests: list[ToolManifest],
    evidence: InitiativeEvidence,
    registry_is_current: bool = False,
    semantic_context: InitiativeSemanticContext | None = None,
) -> dict[str, JsonValue]:
    """No item/field/text cap, opaque stringification, extra retrieval, or card restoration."""
    current_results = {
        key: result
        for key, result in agent_results.items()
        if current_turn_id is not None and key.startswith(f"{current_turn_id}:")
    }
    context: dict[str, object] = {
        key: value
        for key, value in arguments.items()
        if key not in {"max_actions", "execution_summary"}
    }
    context.update(
        {
            "memory_facts": memory_facts,
            "user_interests": interest_profile,
        }
    )
    try:
        if semantic_context is not None:
            if not semantic_context.complete:
                evidence.omit("context_unavailable")
            context["connection_candidates"] = semantic_context.bridges
            context["semantic_dependencies"] = {
                "enabled": semantic_context.enabled,
                "bridges_path": "context.connection_candidates",
                "scope": "available_read_only_tools",
            }
        if current_turn_id is None and agent_results:
            evidence.omit("context_unavailable")
        context["retrieved_turn_results"] = {
            "registry": _current_registry(registry, current_turn_id, registry_is_current, evidence),
            "agent_results": current_results,
        }
        context["available_tools"] = [_tool_contract(manifest) for manifest in manifests]
        projected = _authorized_tree(context, evidence)
        encoded = json.dumps(projected, ensure_ascii=False, allow_nan=False, default=_json_default)
        return cast(dict[str, JsonValue], json.loads(encoded))
    except TypeError, ValueError, AttributeError, RecursionError:
        evidence.omit("not_serializable")
        return {"retrieved_turn_results": {"unavailable": True}}
