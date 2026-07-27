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
unexpected registry error → no blocking. The guard must never break a valid
tool call; it only intercepts a provably wrong one (exact match against the
turn's resolved person names, so false positives are practically impossible).
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.core.field_names import FIELD_RESOLVED_PERSON_NAMES
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Semantic types the guard protects, with the human-readable label used in
# the recoverable error message shown to the LLM.
GUARDED_SEMANTIC_TYPES: dict[str, str] = {
    "physical_address": "physical address",
    "email_address": "email address",
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
    names by construction ({"mon frère": "Marc Lemoine"}), which makes
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
    if not names:
        return config
    configurable = {
        **(config.get("configurable") or {}),
        FIELD_RESOLVED_PERSON_NAMES: sorted(names),
    }
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


def _iter_string_values(value: Any) -> list[str]:
    """Flatten a parameter value into the strings to check (str or list[str])."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


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
        from src.domains.agents.registry import get_global_registry
        from src.domains.agents.registry.agent_registry import ToolManifestNotFound

        try:
            manifest = get_global_registry().get_tool_manifest(tool_name)
        except ToolManifestNotFound:
            return dict(args)

        droppable = {
            param.name
            for param in manifest.parameters
            if getattr(param, "semantic_type", None) and not getattr(param, "required", False)
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
                    value=value,
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
        from src.domains.agents.registry import get_global_registry
        from src.domains.agents.registry.agent_registry import ToolManifestNotFound

        try:
            manifest = get_global_registry().get_tool_manifest(tool_name)
        except ToolManifestNotFound:
            return None

        for param in manifest.parameters:
            semantic_type = getattr(param, "semantic_type", None)
            if semantic_type not in GUARDED_SEMANTIC_TYPES:
                continue
            for candidate in _iter_string_values(args.get(param.name)):
                if _normalize(candidate) in resolved_person_names:
                    return SemanticParamViolation(
                        tool_name=tool_name,
                        param_name=param.name,
                        semantic_type=semantic_type,
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
