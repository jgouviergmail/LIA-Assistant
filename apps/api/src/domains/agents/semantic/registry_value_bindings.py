"""Observe typed registry leaves and bind arguments without rewriting either value."""

import re
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig

from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.registry.catalogue import OutputFieldSchema, ToolManifest
from src.domains.agents.semantic.manifest_semantics import available_manifest
from src.domains.agents.semantic.plan_proof_scope import effective_source_cutoff
from src.domains.agents.semantic.value_bindings import (
    SEMANTIC_SOURCE_OBSERVATIONS_KEY,
    SEMANTIC_SOURCE_VALID_AFTER_KEY,
    SEMANTIC_VALUE_BINDINGS_KEY,
    ScalarValue,
    SemanticValueBinding,
    binding_matches_role,
    binding_scope_from_config,
    source_observation,
)

_ENTITY_TYPES = {
    "CONTACT": "Contact",
    "PLACE": "Place",
    "LOCATION": "Place",
    "EVENT": "CalendarEvent",
}
_PART = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)(\[\])?")


def _item_dict(value: object) -> Mapping[str, object]:
    if isinstance(value, RegistryItem):
        item: dict[str, object] = value.model_dump(mode="python")
        return item
    return value if isinstance(value, dict) else {}


def _walk_leaf(
    payload: object, parts: tuple[str, ...], path: str = ""
) -> Iterator[tuple[str, ScalarValue]]:
    if not parts:
        if payload is None or isinstance(payload, str | int | float | bool):
            yield path, payload
        return
    part = _PART.fullmatch(parts[0])
    if part is None or not isinstance(payload, dict) or part[1] not in payload:
        return
    value = payload[part[1]]
    field_path = f"{path}.{part[1]}" if path else part[1]
    if part[2] and isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_leaf(child, parts[1:], f"{field_path}[{index}]")
    elif not part[2]:
        yield from _walk_leaf(value, parts[1:], field_path)


def _payload_path(output: OutputFieldSchema) -> tuple[str, ...]:
    root, _, leaf = output.path.partition(".")
    return tuple(leaf.split(".")) if root.endswith("[]") and leaf else ()


def _unusable_paths(payload: Mapping[str, object]) -> tuple[set[str], bool]:
    observations = payload.get("mcp_semantic_observations")
    if not isinstance(observations, dict):
        return set(), True
    entries = observations.get("unusable_paths")
    paths = (
        {
            item["path"]
            for item in entries
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        if isinstance(entries, list)
        else set()
    )
    return paths, not bool(observations.get("paths_truncated"))


def _item_is_current(meta: Mapping[str, object]) -> bool:
    ttl, timestamp = meta.get("ttl_seconds"), meta.get("timestamp")
    if not isinstance(ttl, int):
        return True
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except ValueError:
            return False
    return (
        isinstance(timestamp, datetime)
        and timestamp.tzinfo is not None
        and (datetime.now(UTC) - timestamp).total_seconds() <= ttl
    )


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    return value if isinstance(value, datetime) and value.tzinfo is not None else None


def _item_is_after_mutation(meta: Mapping[str, object], valid_after: str | None) -> bool:
    """Historical cards stay intact but cannot resurrect pre-mutation proof."""
    if valid_after is None:
        return True
    cutoff = _timestamp(valid_after)
    observed = _timestamp(meta.get("timestamp"))
    return cutoff is not None and observed is not None and observed >= cutoff


def _observe_output(
    item_id: str,
    payload: Mapping[str, object],
    output: OutputFieldSchema,
    account_id: str,
    entity_type: str,
    current: bool,
) -> Iterator[SemanticValueBinding]:
    role = output.semantic_role
    parts = _payload_path(output)
    if not role or not output.semantic_type or not parts or entity_type not in role.entity_types:
        return
    # A source declaration represents one fact, rather than a disjunction of predicates.
    if len(role.predicates) != 1:
        return
    invalid, complete = _unusable_paths(payload)
    for path, value in _walk_leaf(payload, parts):
        ref = f"$registry.{item_id}.{path}"
        yield source_observation(
            source_ref=ref,
            source_path=path,
            value=value,
            present=True,
            semantic_type=output.semantic_type,
            account_id=account_id,
            entity_type=entity_type,
            entity_ref=item_id,
            predicate=role.predicates[0],
            role=role.role,
            unusable_paths=invalid,
            observations_complete=complete and current,
        )


def registry_source_observations(
    registry: Mapping[str, object],
    account_id: str,
    *,
    valid_after: str | None = None,
) -> dict[str, SemanticValueBinding]:
    """Read actual server-owned payloads only under the current account scope.

    Missing fields produce no observation. An expired or incomplete observation
    is retained as declared evidence, which cannot justify a guard exemption.
    Provider labels and a planner-supplied source reference never create facts.
    """
    if not account_id:
        return {}
    observed: dict[str, SemanticValueBinding] = {}
    for item_id, value in registry.items():
        item = _item_dict(value)
        payload, meta = item.get("payload"), item.get("meta")
        if not isinstance(payload, dict) or not isinstance(meta, dict):
            continue
        tool_name, kind = meta.get("tool_name"), item.get("type")
        entity_type = _ENTITY_TYPES.get(kind) if isinstance(kind, str) else None
        manifest = available_manifest(tool_name) if isinstance(tool_name, str) else None
        if manifest is None or entity_type is None or item.get("id") != item_id:
            continue
        for output in manifest.outputs:
            for observation in _observe_output(
                item_id,
                payload,
                output,
                account_id,
                entity_type,
                _item_is_current(meta) and _item_is_after_mutation(meta, valid_after),
            ):
                observed[observation.source_ref] = observation
    return observed


def _scalar_arguments(
    arguments: Mapping[str, object], prefix: str = ""
) -> Iterator[tuple[str, ScalarValue]]:
    for name, value in arguments.items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict):
            yield from _scalar_arguments(value, path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if isinstance(child, dict):
                    yield from _scalar_arguments(child, f"{path}[{index}]")
                elif child is None or isinstance(child, str | int | float | bool):
                    yield f"{path}[{index}]", child
        elif value is None or isinstance(value, str | int | float | bool):
            yield path, value


def bind_observed_arguments(
    manifest: ToolManifest,
    arguments: Mapping[str, object],
    sources: Mapping[str, SemanticValueBinding],
    *,
    account_id: str,
    selected_sources: Mapping[str, str] | None = None,
) -> tuple[SemanticValueBinding, ...]:
    """Bind only an explicitly selected canonical source, never mere value equality.

    ``selected_sources`` comes from actual reference resolution. A Place Nancy
    merely present in the registry cannot satisfy a request about a person.
    """
    parameters = {parameter.name: parameter for parameter in manifest.parameters}
    bindings: list[SemanticValueBinding] = []
    for path, value in _scalar_arguments(arguments):
        parameter = parameters.get(path.split(".")[0].split("[")[0])
        if parameter is None or parameter.semantic_role is None or not parameter.semantic_type:
            continue
        selected = (selected_sources or {}).get(path)
        if selected is None:
            continue
        candidates = [
            observed
            for observed in sources.values()
            if observed.source_ref == selected
            and _candidate_matches(observed, account_id, value)
            and binding_matches_role(observed, parameter.semantic_type, parameter.semantic_role)
        ]
        if len(candidates) == 1:
            bindings.append(candidates[0].model_copy(update={"path": path}))
    return tuple(bindings)


def _candidate_matches(observed: SemanticValueBinding, account_id: str, value: ScalarValue) -> bool:
    return (
        observed.status == "present"
        and observed.account_id == account_id
        and type(observed.value) is type(value)
        and observed.value == value
        and bool(observed.entity_ref)
    )


def config_with_registry_bindings(
    config: RunnableConfig,
    registry: Mapping[str, object],
    tool_name: str,
    arguments: Mapping[str, object],
    *,
    selected_sources: Mapping[str, str] | None = None,
) -> RunnableConfig:
    """Build runtime proof immediately before the guard, never mutate args or registry."""
    _, account, checkpointed = binding_scope_from_config(config)
    manifest = available_manifest(tool_name)
    if account is None or manifest is None:
        return config
    configurable = dict(config.get("configurable") or {})
    valid_after = effective_source_cutoff(config)
    if valid_after is not None:
        configurable[SEMANTIC_SOURCE_VALID_AFTER_KEY] = valid_after
    sources = {
        **(checkpointed if valid_after is None else {}),
        **registry_source_observations(registry, account, valid_after=valid_after),
    }
    bindings = bind_observed_arguments(
        manifest, arguments, sources, account_id=account, selected_sources=selected_sources
    )
    configurable[SEMANTIC_SOURCE_OBSERVATIONS_KEY] = {
        ref: observed.model_dump(mode="json") for ref, observed in sources.items()
    }
    configurable[SEMANTIC_VALUE_BINDINGS_KEY] = [
        value.model_dump(mode="json") for value in bindings
    ]
    return {**config, "configurable": configurable}
