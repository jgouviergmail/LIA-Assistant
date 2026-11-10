"""What the initiative evaluator's prompt says of the turn, the person and the tools (ADR-062).

The evaluator reads text: these helpers render it, byte for byte as the node always has
(``tests/unit/domains/agents/nodes/test_initiative_prompt_parts.py``). They count nothing —
the omission bookkeeping fed only the JEV utility gate that ADR-374 retired.
"""

from typing import Any

from src.core.constants import (
    INITIATIVE_INTERESTS_LIMIT,
    INITIATIVE_SUMMARY_LIST_ITEM_MAX_CHARS,
    INITIATIVE_SUMMARY_STEP_RESULT_MAX_CHARS,
    INITIATIVE_SUMMARY_TEXT_MAX_CHARS,
    SEMANTIC_CANDIDATES_MAX_TOOLS_PER_TYPE,
)

# Parameters whose name alone does not say what the evaluator must write.
_NEEDS_DESCRIPTION = frozenset({"travel_mode", "units", "date", "user_message", "fields"})


def is_technical_field(key: str, technical: frozenset[str]) -> bool:
    """A provider identifier, transport field or private (``_``-prefixed) key."""
    return key in technical or key.startswith("_")


def truncate_text(value: str) -> str:
    """A text field, cut with an ellipsis past ``INITIATIVE_SUMMARY_TEXT_MAX_CHARS``."""
    if len(value) <= INITIATIVE_SUMMARY_TEXT_MAX_CHARS:
        return value
    return value[:INITIATIVE_SUMMARY_TEXT_MAX_CHARS] + "…"


def list_preview(values: list[object]) -> str:
    """The first item of a non-empty list, cut, then how many more there are."""
    preview = str(values[0])[:INITIATIVE_SUMMARY_LIST_ITEM_MAX_CHARS]
    if len(values) > 1:
        preview += f" (+{len(values) - 1} more)"
    return preview


def step_summary(result: object) -> str:
    """A step's own message when it has one, else its text cut."""
    if isinstance(result, dict):
        supplied = result.get("message") or result.get("result")
        if supplied:
            return str(supplied)
    return str(result)[:INITIATIVE_SUMMARY_STEP_RESULT_MAX_CHARS]


def format_memory_facts(facts: list[str] | None) -> str:
    """The person's relevant memories, one per line."""
    if not facts:
        return "No relevant memories."
    return "Relevant user context:\n" + "\n".join(f"- {f}" for f in facts)


def format_tools_for_prompt(manifests: list[Any]) -> str:
    """Each adjacent read-only tool with its parameter contract."""
    lines = []
    for manifest in manifests:
        param_parts = []
        for parameter in manifest.parameters:
            if parameter.name in _NEEDS_DESCRIPTION and parameter.description:
                param_parts.append(f"{parameter.name}: {parameter.description}")
            elif parameter.required:
                param_parts.append(f"{parameter.name} (required)")
            else:
                param_parts.append(parameter.name)
        params_str = f" | Params: {', '.join(param_parts)}" if param_parts else ""
        lines.append(f"- {manifest.name}: {manifest.description}{params_str}")
    return "\n".join(lines)


def format_interests(profile: dict[str, Any]) -> str:
    """The person's active interests among the first ``INITIATIVE_INTERESTS_LIMIT``."""
    interests = profile.get("interests", [])
    active = [
        f"{i['topic']} ({i['category']})"
        for i in interests[:INITIATIVE_INTERESTS_LIMIT]
        if i.get("status") == "active"
    ]
    if not active:
        return "No known interests."
    return "User interests: " + ", ".join(active)


def semantic_bridge_line(type_name: str, providers: list[str], consumers: list[str]) -> str:
    """One connection candidate: a type a result provides that a read-only tool consumes."""
    providers_str = ", ".join(providers) if providers else "execution"
    tools_str = ", ".join(consumers[:SEMANTIC_CANDIDATES_MAX_TOOLS_PER_TYPE])
    omitted = len(consumers) - SEMANTIC_CANDIDATES_MAX_TOOLS_PER_TYPE
    if omitted > 0:
        tools_str += f" (+{omitted} more)"
    return f"- {type_name} (from {providers_str} results) → consumable by: {tools_str}"
