"""Runtime semantic parameter guard — last-resort net for semantic contracts.

Tool manifests annotate parameters with ``semantic_type`` (physical_address,
email_address, ...). When semantic domain expansion failed upstream, a plan
(or a ReAct tool call) can still pass a *person name* where an address or an
email is expected — the downstream API then geocodes/sends to something
arbitrary, and the wrong result may even be cached.

This guard checks final tool arguments (post Jinja2 / $steps resolution)
against the identity mappings resolved for the current turn: an argument
that is exactly a resolved person name on a guarded parameter fails fast
with a recoverable error BEFORE the paid API call, in both execution modes
(pipeline parallel executor + ReAct execute-tools node).

Fail-open by design: no manifest, no semantic_type, no resolved names, or an
unexpected registry error → no blocking. An exact match against the turn's
resolved person names is a collision signal. A genuinely homonymous location
passes only when an explicitly selected canonical field proves its role,
identity, account and unchanged value.
"""

from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.core.field_names import FIELD_RESOLVED_PERSON_NAMES
from src.domains.agents.semantic.core_types import load_core_types
from src.domains.agents.semantic.manifest_semantics import available_manifest
from src.domains.agents.semantic.semantic_type import TypeCategory
from src.domains.agents.semantic.type_registry import get_registry
from src.domains.agents.semantic.value_bindings import (
    SEMANTIC_SOURCE_OBSERVATIONS_KEY,
    SEMANTIC_SOURCE_VALID_AFTER_KEY,
    SEMANTIC_VALUE_BINDINGS_KEY,
    SemanticValueBinding,
    parse_source_observations,
    parse_value_bindings,
    value_binding_exempts_collision,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Semantic types the guard protects, with the human-readable label used in
# the recoverable error message shown to the LLM.
GUARDED_SEMANTIC_TYPES: dict[str, str] = {
    "physical_address": "physical address",
    "email_address": "email address",
    "locality": "place or locality",
}


@dataclass(frozen=True)
class SemanticParamViolation:
    """A person name detected on an address/email-typed tool parameter.

    Attributes:
        tool_name: Name of the tool whose call was intercepted.
        param_name: Manifest parameter carrying the guarded semantic type.
        semantic_type: The guarded semantic type (e.g. "physical_address").
        value: The offending argument value (a resolved person name).
    """

    tool_name: str
    param_name: str
    semantic_type: str
    value: str

    def llm_message(self) -> str:
        """Build the recoverable error message guiding the LLM.

        Returns:
            English technical message (the model reformulates in the user's
            language) explaining what was expected and how to recover.
        """
        expected = GUARDED_SEMANTIC_TYPES.get(self.semantic_type, self.semantic_type)
        return (
            f"Parameter '{self.param_name}' of {self.tool_name} expects a "
            f"{expected}, but received '{self.value}', which is a person's "
            f"name. Fetch the person's actual {expected} first (e.g. from "
            f"contacts), then retry with that value."
        )


def _normalize(text: str) -> str:
    """Normalize a value for exact-match comparison (whitespace + case)."""
    return " ".join(text.split()).casefold()


def collect_resolved_person_names(
    resolved_references: Mapping[str, Any] | None,
) -> frozenset[str]:
    """Extract normalized person names from the turn's identity mappings.

    The memory-resolution pipeline produces mappings whose values are person
    names by construction ({"my brother": "Marc Lemoine"}), which makes
    exact matching against them a deterministic signal.

    Args:
        resolved_references: The turn's reference → resolved-name mappings
            (state key ``resolved_references``), or None.

    Returns:
        Frozen set of normalized names; empty when there is nothing to guard.
    """
    if not resolved_references:
        return frozenset()
    return frozenset(
        _normalize(value)
        for value in resolved_references.values()
        if isinstance(value, str) and value.strip()
    )


def config_with_person_names(
    config: RunnableConfig,
    state: Mapping[str, Any],
) -> RunnableConfig:
    """Return a config whose configurable carries the turn's person names.

    Called by the nodes that launch plan execution (task orchestrator,
    initiative) so the parallel executor's guard can read the names from
    config. Sourced from STATE — the only conduit that survives a HITL
    interrupt/resume (config is rebuilt on resume, ContextVars are lost).

    Args:
        config: The node's RunnableConfig.
        state: LangGraph state holding ``resolved_references``.

    Returns:
        The same config when there is nothing to guard, otherwise a shallow
        copy with ``resolved_person_names`` added to configurable.
    """
    names = collect_resolved_person_names(state.get("resolved_references"))
    config = config_with_binding_evidence(config, state)
    if not names:
        return config
    configurable = {
        **(config.get("configurable") or {}),
        FIELD_RESOLVED_PERSON_NAMES: sorted(names),
    }
    return {**config, "configurable": configurable}


def config_with_binding_evidence(
    config: RunnableConfig, state: Mapping[str, object]
) -> RunnableConfig:
    """Carry current checkpointed evidence without trusting stale config sidecars."""
    configurable = dict(config.get("configurable") or {})
    keys = (
        SEMANTIC_VALUE_BINDINGS_KEY,
        SEMANTIC_SOURCE_OBSERVATIONS_KEY,
        SEMANTIC_SOURCE_VALID_AFTER_KEY,
    )
    if not any(key in state or key in configurable for key in keys):
        return config
    bindings = parse_value_bindings(state.get(SEMANTIC_VALUE_BINDINGS_KEY))
    sources = parse_source_observations(state.get(SEMANTIC_SOURCE_OBSERVATIONS_KEY))
    configurable[SEMANTIC_VALUE_BINDINGS_KEY] = [
        binding.model_dump(mode="json") for binding in bindings
    ]
    configurable[SEMANTIC_SOURCE_OBSERVATIONS_KEY] = {
        key: observed.model_dump(mode="json") for key, observed in sources.items()
    }
    cutoff = state.get(SEMANTIC_SOURCE_VALID_AFTER_KEY)
    if isinstance(cutoff, str):
        configurable[SEMANTIC_SOURCE_VALID_AFTER_KEY] = cutoff
    else:
        configurable.pop(SEMANTIC_SOURCE_VALID_AFTER_KEY, None)
    return {**config, "configurable": configurable}


def person_names_from_config(config: RunnableConfig) -> frozenset[str]:
    """Read the guard's person names back from a config's configurable.

    Args:
        config: RunnableConfig possibly enriched by config_with_person_names.

    Returns:
        Frozen set of normalized names (empty when the guard has nothing).
    """
    names = (config.get("configurable") or {}).get(FIELD_RESOLVED_PERSON_NAMES) or []
    return frozenset(name for name in names if isinstance(name, str))


def _iter_string_values(value: object) -> list[str]:
    """Flatten a parameter value into the strings to check (str or list[str])."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _json_type_matches(type_name: object, value: object) -> bool:
    """Check declared JSON shape, keeping booleans distinct from numbers."""
    if isinstance(type_name, list):
        return any(_json_type_matches(member, value) for member in type_name)
    matches = {
        "null": value is None,
        "string": isinstance(value, str),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
    }
    return matches.get(type_name, True) if isinstance(type_name, str) else True


def _object_constraints_match(schema: dict[str, object], value: object) -> bool:
    """Use required fields and discriminants to rule out impossible branches."""
    if not isinstance(value, dict):
        return True
    required = schema.get("required")
    if isinstance(required, list) and any(name not in value for name in required):
        return False
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return True
    return all(
        _schema_shape_matches(child, value[name])
        for name, child in properties.items()
        if name in value
    )


def _schema_shape_matches(schema: object, value: object) -> bool:
    """Conservative branch applicability, never treating format failures as absence.

    An invalid email must still reach the email guard. Only declared shapes,
    required fields and exact enum/const discriminants rule out a branch.
    """
    if not isinstance(schema, dict):
        return True
    if not _json_type_matches(schema.get("type"), value):
        return False
    if "const" in schema and value != schema["const"]:
        return False
    options = schema.get("enum")
    if isinstance(options, list) and value not in options:
        return False
    return _object_constraints_match(schema, value)


def _composed_schema_values(
    schema: dict[str, object], value: object, path: str
) -> Iterator[tuple[str, str, str]]:
    """Conjunctions accumulate constraints; unions guard only guaranteed leaves."""
    members = schema.get("allOf")
    if isinstance(members, list):
        for member in members:
            yield from _iter_schema_values(member, value, path)
    for keyword in ("anyOf", "oneOf"):
        branches = schema.get(keyword)
        if not isinstance(branches, list):
            continue
        checks = [
            set(_iter_schema_values(branch, value, path))
            for branch in branches
            if _schema_shape_matches(branch, value)
        ]
        if checks:
            yield from sorted(set.intersection(*checks))


def _array_schema_values(
    schema: dict[str, object], value: object, path: str
) -> Iterator[tuple[str, str, str]]:
    """Tuple prefixes own their positions; items applies only after the prefix."""
    if not isinstance(value, list):
        return
    prefixes = schema.get("prefixItems")
    members = prefixes if isinstance(prefixes, list) else []
    for index, child_value in enumerate(value):
        child = members[index] if index < len(members) else schema.get("items")
        yield from _iter_schema_values(child, child_value, f"{path}[{index}]")


def _iter_schema_values(schema: object, value: object, path: str) -> Iterator[tuple[str, str, str]]:
    """Yield only values with explicit schema annotations, keeping their path."""
    if not isinstance(schema, dict):
        return
    semantic_type = schema.get("x-semantic-type")
    if isinstance(semantic_type, str):
        for candidate in _iter_string_values(value):
            yield path, semantic_type, candidate
    properties = schema.get("properties")
    if isinstance(properties, dict) and isinstance(value, dict):
        for name, child in properties.items():
            if isinstance(name, str) and name in value:
                yield from _iter_schema_values(child, value[name], f"{path}.{name}")
    yield from _array_schema_values(schema, value, path)
    yield from _composed_schema_values(schema, value, path)


# Textual stand-ins for "no value" that a JSON-emitting LLM produces verbatim.
# Compared exactly (case/whitespace-insensitive), never as a substring.
_NULL_PLACEHOLDERS: frozenset[str] = frozenset(
    {"null", "none", "undefined", "nil", "n/a", "na", "nan"}
)


def strip_placeholder_arguments(
    tool_name: str,
    args: Mapping[str, Any],
) -> dict[str, Any]:
    """Drop optional arguments whose value is a textual stand-in for "no value".

    A planner emitting JSON writes ``"location": "null"`` when it means "not
    provided", and every ``if not value`` guard downstream accepts that string:
    prod 2026-07-23 geocoded a city literally named "null" and answered with the
    weather of Cappaghnanool, IE. Removing the argument restores the intended
    behaviour — the tool falls back to its own default (auto-geolocation).

    Deliberately narrow, so a legitimate value is never dropped:

    - only parameters the manifest declares with a ``semantic_type`` (an
      identifier/address/date slot, never free text such as a search query);
    - only parameters the manifest marks as NOT required (a required slot
      holding "null" is a real planning bug and must fail loudly, not silently
      degrade);
    - exact match against :data:`_NULL_PLACEHOLDERS`, so "Nullarbor" or a note
      containing the word "none" is untouched.

    Fail-open like the rest of this module: no manifest, no declared parameter,
    or any registry error leaves the arguments exactly as they were.

    Args:
        tool_name: Tool about to be executed.
        args: Final arguments (after Jinja2 / $steps resolution).

    Returns:
        The arguments, without the placeholder-valued optional parameters.
    """
    if not args:
        return dict(args)

    try:
        manifest = available_manifest(tool_name)
        if manifest is None:
            return dict(args)

        type_registry = get_registry()
        if not len(type_registry):
            load_core_types(type_registry)
        droppable = {
            param.name
            for param in manifest.parameters
            if param.semantic_type
            and not param.required
            and (type_def := type_registry.get(param.semantic_type)) is not None
            and type_def.category != TypeCategory.CONTENT
        }
        if not droppable:
            return dict(args)

        cleaned = dict(args)
        for name in droppable:
            value = cleaned.get(name)
            if isinstance(value, str) and _normalize(value) in _NULL_PLACEHOLDERS:
                del cleaned[name]
                logger.info(
                    "placeholder_argument_dropped",
                    tool_name=tool_name,
                    param_name=name,
                    value_length=len(str(value)),
                )
        return cleaned

    except Exception as exc:
        logger.debug(
            "placeholder_argument_guard_failed_open",
            tool_name=tool_name,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return dict(args)


def check_semantic_params(
    tool_name: str,
    args: Mapping[str, Any],
    resolved_person_names: Collection[str],
    *,
    value_bindings: Sequence[SemanticValueBinding] = (),
    account_id: str | None = None,
    known_sources: Mapping[str, SemanticValueBinding] | None = None,
) -> SemanticParamViolation | None:
    """Check final tool arguments against the turn's resolved person names.

    Args:
        tool_name: Tool about to be executed.
        args: Final arguments (after Jinja2 / $steps resolution).
        resolved_person_names: Normalized person names for the current turn
            (from :func:`collect_resolved_person_names`).

    Returns:
        The first violation found, or None when the call is clean (or when
        the guard cannot apply — no manifest, no guarded params, no names).
    """
    if not resolved_person_names or not args:
        return None

    try:
        manifest = available_manifest(tool_name)
        if manifest is None:
            return None

        for param in manifest.parameters:
            semantic_type = getattr(param, "semantic_type", None)
            checks = list(_iter_schema_values(param.schema, args.get(param.name), param.name))
            if semantic_type in GUARDED_SEMANTIC_TYPES:
                checks.extend(
                    (param.name, semantic_type, candidate)
                    for candidate in _iter_string_values(args.get(param.name))
                )
            for path, type_name, candidate in checks:
                if (
                    type_name in GUARDED_SEMANTIC_TYPES
                    and _normalize(candidate) in resolved_person_names
                    and not value_binding_exempts_collision(
                        value_bindings,
                        path=path,
                        value=candidate,
                        semantic_type=type_name,
                        expected_role=getattr(param, "semantic_role", None),
                        account_id=account_id,
                        known_sources=known_sources or {},
                    )
                ):
                    return SemanticParamViolation(
                        tool_name=tool_name,
                        param_name=path,
                        semantic_type=type_name,
                        value=candidate,
                    )
        return None

    except Exception as exc:
        # Fail-open: the guard is a safety net and must never break a valid
        # tool call; an unexpected registry failure is only worth a debug.
        logger.debug(
            "semantic_param_guard_failed_open",
            tool_name=tool_name,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None
