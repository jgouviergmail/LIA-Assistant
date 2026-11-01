"""How a tool's output becomes a pipeline step's result (spec 2026-10-29 D5, D7).

Moved verbatim out of ``parallel_executor._execute_tool`` — the registry ids
re-identified per FOR_EACH parent, the structured data exposed for Jinja, the
data a READ tool carries beyond its items (ADR-347) — so a resumed plan projects a
replayed draft's result the way a step's own call is projected. The golden test
``test_step_results.py`` pinned the inline block's output before the move.

The one change is the draft reader: an output may ask the person to confirm
SEVERAL calls (an iterative MCP task hands up every confirmation its sub-loop
queued), so ``drafts_of`` returns a list — and it is the one reader both modes
use: the ReAct loop reads a call's drafts through it too (``react_drafts``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, Field

from src.core.field_names import (
    FIELD_CORRELATED_TO,
    FIELD_ERROR_CODE,
    FIELD_REGISTRY_ID,
    FIELD_RESULT,
    FIELD_STEP_ID,
)
from src.domains.agents.data_registry.models import RegistryItemType, generate_registry_id
from src.domains.agents.orchestration.tool_data_projection import tool_data_fields
from src.domains.agents.tools.output import StandardToolOutput, UnifiedToolOutput

if TYPE_CHECKING:
    from src.domains.agents.registry.catalogue import ToolManifest

logger = structlog.get_logger(__name__)

#: Where an output that asks for several confirmations lists them.
PENDING_DRAFTS_KEY = "pending_drafts"


class ToolExecutionResult(BaseModel):
    """
    Internal result type for tool execution with data registry support.

    Data Registry LOT 5.2: Captures both the tool result and any registry updates
    from StandardToolOutput returned by registry-enabled tools.

    Data Registry LOT 4.3: Captures draft info when requires_confirmation=True.

    Attributes:
        result: Tool result dict (ToolResponse format)
        registry_updates: Optional data registry items from StandardToolOutput
        draft_infos: Every draft the output asks the person to confirm (spec D5)
    """

    result: dict[str, Any]
    registry_updates: dict[str, Any] | None = None
    draft_infos: list[dict[str, Any]] = Field(default_factory=list)


def drafts_of(result: object, tool_name: str, step_id: str | None) -> list[dict[str, Any]]:
    """Every draft an output asks the person to confirm, in its order.

    A mutation tool's output carries ONE draft (``draft_id`` and its registry
    item); an iterative MCP task's carries the list its sub-loop queued under
    ``pending_drafts``. Each entry has the ``PendingDraftInfo`` fields and names
    the step it belongs to.

    Args:
        result: The tool's output, of any shape.
        tool_name: The tool that produced it — a single draft is that tool's.
        step_id: The pipeline step, None in the ReAct loop.

    Returns:
        The drafts; empty when the output asks nothing.
    """
    metadata = getattr(result, "tool_metadata", None)
    if not isinstance(metadata, dict) or not metadata.get("requires_confirmation"):
        return []
    listed = metadata.get(PENDING_DRAFTS_KEY)
    if isinstance(listed, list):
        return [
            {**draft, "step_id": step_id}
            for draft in listed
            if isinstance(draft, dict) and draft.get("draft_id")
        ]
    draft_id = metadata.get("draft_id")
    if not draft_id:
        # Nothing could answer it: a draft without an identity would fail the
        # confirmation queue's validation. Said, never silently dropped.
        logger.warning("draft_output_without_id", tool_name=tool_name)
        return []
    registry: dict[str, Any] = getattr(result, "registry_updates", None) or {}
    return [
        {
            "draft_id": draft_id,
            "draft_type": metadata.get("draft_type"),
            "draft_content": _draft_content(registry.get(draft_id)),
            "draft_summary": getattr(result, "summary_for_llm", "") or "",
            "registry_ids": list(registry.keys()),
            "tool_name": tool_name,
            "step_id": step_id,
        }
    ]


def draft_ids(drafts: list[dict[str, Any]]) -> list[Any]:
    """The ids of the drafts ``drafts_of`` returned, for the logs."""
    return [draft.get("draft_id") for draft in drafts]


def _draft_content(item: object) -> dict[str, Any]:
    """The executable content a draft's registry item carries (object or dict)."""
    payload = getattr(item, "payload", None)
    if payload is None and isinstance(item, dict):
        payload = item.get("payload")
    content = payload.get("content") if isinstance(payload, dict) else None
    return content if isinstance(content, dict) else {}


def _correlated_item_id(item_id: str, item_dict: dict[str, Any], parent_id: str) -> str:
    """Derive a registry id unique to the (item, correlation parent) pair.

    Tools build their registry id from the payload alone — the weather tools key
    on place + day, the route tools on origin + destination. Under FOR_EACH that
    is not enough: two parents sharing those attributes (two appointments on the
    same day at the same place) yield the SAME id, and since the accumulator is a
    plain ``dict.update()`` the second branch overwrites the first. The first
    parent then has no correlated child at all, so its card renders without the
    data that was fetched for it.

    Deterministic (SHA-256 over ``"{item_id}@{parent_id}"``), so a replayed run
    or a resumed checkpoint recomputes the same id. Keeps the ``{type}_{hash}``
    shape that ``filter_registry_by_relevant_ids`` relies on for suffix matching.

    Args:
        item_id: Id produced by the tool.
        item_dict: Serialized registry item (used to recover its type).
        parent_id: Registry id of the FOR_EACH parent this item belongs to.

    Returns:
        A per-parent id, or ``item_id`` unchanged when the item IS its parent or
        when the type is unknown (never break the id shape to fix a collision).
    """
    if item_id == parent_id:
        # Self-enrichment, not derivation: a FOR_EACH over a collection whose
        # tool re-emits the same entity (update_event / get_*_details) rebuilds
        # the parent's own id — `generate_registry_id(type, entity_id)` is a pure
        # hash of the business id. Re-identifying here would turn an UPDATE into
        # a duplicate, leaving the stale version alive next to the fresh one.
        return item_id
    try:
        item_type = RegistryItemType(item_dict.get("type"))
    except ValueError:
        logger.warning(
            "correlated_item_id_unknown_type",
            item_id=item_id,
            item_type=item_dict.get("type"),
        )
        return item_id
    return generate_registry_id(item_type, f"{item_id}@{parent_id}")


def project_tool_result(
    result: StandardToolOutput | UnifiedToolOutput,
    *,
    tool_name: str,
    step_id: str | None,
    turn_id: int | None,
    correlation_parent_id: str | None,
    manifest: ToolManifest | None,
    data_share: int,
) -> ToolExecutionResult:
    """Project a registry-aware tool output into a step's result.

    Args:
        result: The tool's output.
        tool_name: The tool that produced it.
        step_id: Execution plan step ID, injected into each item's meta.
        turn_id: Current turn ID, injected into each item's meta.
        correlation_parent_id: The FOR_EACH parent this output belongs to, if any.
        manifest: The tool's manifest, which decides whether its data is projected.
        data_share: How many results share this step's data budget.

    Returns:
        The step's result, its registry items and the drafts it asks to confirm.
    """
    registry_updates = _projected_registry(
        result,
        tool_name=tool_name,
        step_id=step_id,
        turn_id=turn_id,
        correlation_parent_id=correlation_parent_id,
    )

    # Data Registry LOT 4.3: every draft the output asks the person to confirm —
    # one for a mutation tool, several for an iterative MCP task (spec D5).
    draft_infos = drafts_of(result, tool_name, step_id)
    if draft_infos:
        logger.info(
            "registry_draft_detected_requires_confirmation",
            tool_name=tool_name,
            draft_ids=[draft["draft_id"] for draft in draft_infos],
            draft_types=sorted({str(draft["draft_type"]) for draft in draft_infos}),
            registry_items_count=len(registry_updates),
        )
    else:
        logger.info(
            "registry_tool_output_detected",
            tool_name=tool_name,
            registry_items_count=len(registry_updates),
            summary_length=len(result.summary_for_llm),
        )

    structured_data = _jinja_data(result, registry_updates, tool_name)
    structured_data.update(_query_engine_data(result.tool_metadata, tool_name))

    # ADR-347: what a READ tool's structured_data carries beyond its
    # registry items, projected for the pipeline's response model.
    structured_data.update(
        tool_data_fields(result, manifest=manifest, tool_name=tool_name, share=data_share)
    )

    return ToolExecutionResult(
        result=_result_payload(result, structured_data),
        registry_updates=registry_updates,
        draft_infos=draft_infos,
    )


def _projected_registry(
    result: StandardToolOutput | UnifiedToolOutput,
    *,
    tool_name: str,
    step_id: str | None,
    turn_id: int | None,
    correlation_parent_id: str | None,
) -> dict[str, Any]:
    """The output's registry items, serialized, stamped and re-identified per parent."""
    # Registry-enabled tool: Extract registry and use summary_for_llm
    # BugFix 2025-12-19: Inject turn_id into each item's meta for context resolution
    # Correlated Display: Inject step_id and correlated_to into each item's meta
    registry_updates = {}
    for item_id, item in result.registry_updates.items():
        item_dict = item.model_dump(mode="json")
        if isinstance(item_dict.get("meta"), dict):
            # Inject turn_id if not already set
            if turn_id is not None and item_dict["meta"].get("turn_id") is None:
                item_dict["meta"]["turn_id"] = turn_id
            # Inject step_id if not already set
            if step_id is not None and item_dict["meta"].get(FIELD_STEP_ID) is None:
                item_dict["meta"][FIELD_STEP_ID] = step_id
            # Inject correlated_to if parent ID available (from FOR_EACH expansion)
            if correlation_parent_id and item_dict["meta"].get(FIELD_CORRELATED_TO) is None:
                item_dict["meta"][FIELD_CORRELATED_TO] = correlation_parent_id
                # A correlated item belongs to ONE parent, so its identity
                # must include that parent. Tools derive their id from the
                # content alone (weather -> place+day), so two FOR_EACH
                # branches over parents that share it produce the SAME id;
                # the accumulator is a plain dict.update(), so the second
                # branch silently overwrote the first and its parent lost
                # its child entirely. Measured in prod (2026-07-23): two
                # appointments -> both branches emitted "weather_fee011",
                # registry size stayed at 4 instead of 5.
                correlated_id = _correlated_item_id(item_id, item_dict, correlation_parent_id)
                logger.info(
                    "correlated_to_injected",
                    item_id=item_id,
                    correlated_item_id=correlated_id,
                    correlation_parent_id=correlation_parent_id,
                    tool_name=tool_name,
                )
                item_dict["id"] = correlated_id
                item_id = correlated_id
        registry_updates[item_id] = item_dict
    return registry_updates


def _jinja_data(
    result: StandardToolOutput | UnifiedToolOutput,
    registry_updates: dict[str, Any],
    tool_name: str,
) -> dict[str, Any]:
    """The step's data for Jinja templates: its summary, items by domain, the tool's own keys."""
    # =================================================================
    # Data Registry LOT 5.3 FIX: Expose structured data for Jinja templates
    # =================================================================
    # Problem: completed_steps only contained summary_for_llm (string).
    # Jinja templates like `{% for c in steps.search.contacts %}` failed
    # because there was no `.contacts` array - just `.result` string.
    #
    # Solution: Extract contacts/emails from registry_updates and expose
    # them in the result data. This allows Jinja templates to iterate
    # over structured data while LLM still sees the summary.
    # =================================================================
    structured_data: dict[str, Any] = {
        FIELD_RESULT: result.summary_for_llm,
    }

    # =================================================================
    # GENERIC: Extract ALL registry item types for Jinja access
    # =================================================================
    # Design: Group items by meta.domain (the canonical result_key).
    # The meta.domain value comes from CONTEXT_DOMAIN_* constants which
    # are aligned with DomainConfig.result_key in domain_taxonomy.py.
    #
    # This is the SINGLE source of truth for naming - no more conversions!
    # Examples: meta.domain="contacts" → structured_data["contacts"]
    #           meta.domain="weathers" → structured_data["weathers"]
    # =================================================================
    items_by_domain: dict[str, list[dict[str, Any]]] = {}

    for item_id, item_dict in registry_updates.items():
        payload = item_dict.get("payload", {})
        meta = item_dict.get("meta", {})
        # Use meta.domain as the canonical key (aligned with result_key)
        # Fallback to item_type.lower() + "s" for legacy items without meta.domain
        item_type = item_dict.get("type", "")
        key = meta.get("domain") or (item_type.lower() + "s" if item_type else "unknown")

        if payload:
            if key not in items_by_domain:
                items_by_domain[key] = []

            # Add registry_id to payload for Jinja reference
            enriched_payload = {**payload, FIELD_REGISTRY_ID: item_id}
            items_by_domain[key].append(enriched_payload)

    # Expose all domains in structured_data for Jinja templates
    for key, items in items_by_domain.items():
        structured_data[key] = items
        logger.debug(
            "registry_exposed_items_for_jinja",
            tool_name=tool_name,
            domain_key=key,
            count=len(items),
        )

    # =================================================================
    # evolution F2.4: Gentle merge of tool-provided structured_data
    # =================================================================
    # Tools (notably UserMCPToolAdapter) can set structured_data with
    # additional keys (e.g. "repositories") that the registry derivation
    # above does not produce.  We merge them here **without overwriting**
    # any registry-derived key, preserving the enriched payloads
    # (which carry _registry_id for parent correlation in for_each).
    #
    # Verified safe: no existing native tool has key conflicts with
    # registry-derived domain keys.
    # =================================================================
    if isinstance(result, UnifiedToolOutput) and result.structured_data:
        for key, value in result.structured_data.items():
            if key not in structured_data:
                structured_data[key] = value
    return structured_data


def _query_engine_data(metadata: dict[str, Any] | None, tool_name: str) -> dict[str, Any]:
    """A LocalQueryEngine GROUP or AGGREGATE answer, exposed for Jinja (it overrides).

    FIX Issue #dupond-15h55: the planner generates templates such as
    ``{% for group in steps.group_by_address.query_result %}``, but the groups
    were not exposed. They come from ``tool_metadata`` (set by local_query_tool).
    FIX Issue #dupond-16h57: the planner writes ``query_result``, not
    ``groups`` — both names are exposed.
    """
    exposed: dict[str, Any] = {}
    if not metadata:
        return exposed
    # GROUP operation: expose groups list
    if "groups" in metadata:
        transformed_groups = [_jinja_group(group) for group in metadata["groups"]]
        exposed["groups"] = transformed_groups
        # CRITICAL: Planner generates templates with .query_result, not .groups
        exposed["query_result"] = transformed_groups
        logger.debug(
            "registry_exposed_groups_for_jinja",
            tool_name=tool_name,
            groups_count=len(transformed_groups),
            aliases=["groups", "query_result"],
            sample_group_keys=[g["key"] for g in transformed_groups[:3]],
        )
    # AGGREGATE operation: expose distinct_values
    if "distinct_values" in metadata:
        exposed["distinct_values"] = metadata["distinct_values"]
        logger.debug(
            "registry_exposed_distinct_values_for_jinja",
            tool_name=tool_name,
            distinct_count=len(metadata["distinct_values"]),
        )
    return exposed


def _jinja_group(group: dict[str, Any]) -> dict[str, Any]:
    """One group with its members' payloads at top level.

    ``{{ item.resource_name }}`` fails when the field sits inside ``payload``:
    members are RegistryItem objects, serialized items, or payloads already.
    """
    transformed_members = []
    for item in group.get("members", []):
        member = _jinja_member(item)
        if member is not None:
            transformed_members.append(member)
    return {
        "key": group.get("key", ""),
        "members": transformed_members,
        "count": len(transformed_members),
    }


def _jinja_member(item: Any) -> dict[str, Any] | None:
    """A group member's payload with its registry id, or None when it has none."""
    # Extract payload from RegistryItem (object or dict)
    if hasattr(item, "payload"):
        # Pydantic RegistryItem object
        payload = item.payload
        item_id = item.id
    elif isinstance(item, dict) and "payload" in item:
        # Serialized RegistryItem dict
        payload = item["payload"]
        item_id = item.get("id", "")
    else:
        # Already a payload dict (fallback)
        payload = item
        item_id = item.get(FIELD_REGISTRY_ID, "")
    if not payload:
        return None
    # Add registry_id for reference (consistent with the domain lists)
    return {**payload, FIELD_REGISTRY_ID: item_id}


def _result_payload(
    result: StandardToolOutput | UnifiedToolOutput, structured_data: dict[str, Any]
) -> dict[str, Any]:
    """The step's result: its verdict, its data, and what the context save reads."""
    # Propagate TCM flag and save mode so _auto_save_wave_contexts can
    # detect decorator-saved tools and skip the duplicate save path.
    # getattr: StandardToolOutput has no context_save_mode field.
    tcm_saved = result.tool_metadata.get("_tcm_saved", False) if result.tool_metadata else False
    save_mode = getattr(result, "context_save_mode", None)
    save_mode_value = (
        save_mode.value if save_mode is not None and hasattr(save_mode, "value") else save_mode
    )

    # UnifiedToolOutput carries an explicit verdict; the legacy
    # StandardToolOutput has none (implicit success). A typed failure
    # must keep saying so: hardcoding True here reported a refused
    # peer relay as delivered (prod 2026-08-17, request 2ecc670c), and
    # the runtime failures directive — the one channel that tells a
    # failure of a step that ran (RC1.2) — reads this flag.
    succeeded = result.success if isinstance(result, UnifiedToolOutput) else True
    result_payload: dict[str, Any] = {
        "success": succeeded,
        "data": structured_data,
        "message": result.summary_for_llm,
        "_tcm_saved": tcm_saved,
        "context_save_mode": save_mode_value,
    }
    if not succeeded and isinstance(result, UnifiedToolOutput):
        result_payload["error"] = result.error_message or result.summary_for_llm
        if result.error_code:
            result_payload[FIELD_ERROR_CODE] = result.error_code
    return result_payload
