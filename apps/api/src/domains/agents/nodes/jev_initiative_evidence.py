"""Track actual initiative projection omissions; never infer completeness from size."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Self, get_args

from pydantic import JsonValue

from src.core.constants import INITIATIVE_INTERESTS_LIMIT
from src.domains.agents.constants import AgentResultStatus
from src.domains.agents.prompts.prompt_loader import load_prompt

OmissionReason = Literal[
    "text_truncated",
    "list_items_omitted",
    "list_text_truncated",
    "nested_value_omitted",
    "fields_omitted",
    "unsupported_payload",
    "excluded_semantic_field",
    "steps_omitted",
    "fallback_result_truncated",
    "unsupported_step",
    "execution_incomplete",
    "no_structured_evidence",
    "interests_omitted",
    "semantic_bridges_omitted",
    "context_unavailable",
    "source_truncated",
    "not_serializable",
]

# These omitted fields can change whether an initiative has any utility.
SEMANTIC_EXCLUSIONS = frozenset({"creator", "organizer", "status", "reminders", "steps"})
_NEEDS_DESCRIPTION = frozenset({"travel_mode", "units", "date", "user_message", "fields"})


def closed_omissions(values: Mapping[str, object]) -> dict[str, int]:
    """Only fixed codes and positive integer counts can enter INFO metadata."""
    return {
        reason: count
        for reason, count in values.items()
        if reason in get_args(OmissionReason) and type(count) is int and count > 0
    }


def evidence_omissions(state: JsonValue, supplied: dict[str, int] | None) -> dict[str, int]:
    """A declared incomplete state cannot become usable through a missing side argument."""
    codes = closed_omissions(supplied or {})
    evidence = state.get("evidence") if isinstance(state, dict) else None
    if isinstance(evidence, dict) and evidence.get("complete") is False:
        declared = evidence.get("omissions")
        if isinstance(declared, dict):
            codes.update(closed_omissions(declared))
        if not codes:
            codes["context_unavailable"] = 1
    if supplied and not codes:
        codes["context_unavailable"] = 1
    return codes


@dataclass
class InitiativeEvidence:
    """Counts attached at the exact operations that omit source information."""

    omissions: dict[str, int] = field(default_factory=dict)

    @classmethod
    def for_optional(cls, evidence: Self | None) -> Self:
        """Standalone formatters may render without retaining projection diagnostics."""
        return evidence if evidence is not None else cls()

    def omit(self, reason: OmissionReason, count: int = 1) -> None:
        if count > 0:
            self.omissions[reason] = self.omissions.get(reason, 0) + count

    def check_failures(self, results: dict[str, object], turn_id: int | None) -> None:
        """Registry content must not hide a failed current-turn execution."""
        for key, value in results.items():
            if turn_id is not None and not key.startswith(f"{turn_id}:"):
                continue
            if not isinstance(value, dict):
                continue
            if value.get("status") == AgentResultStatus.ERROR.value or value.get("failed_steps"):
                self.omit("execution_incomplete")

    def excluded(self, key: str, technical: frozenset[str], value: object) -> bool:
        if key not in technical and not key.startswith("_"):
            return False
        meaningful = key in SEMANTIC_EXCLUSIONS or (key.startswith("_") and key not in technical)
        if meaningful and value is not None:
            self.omit("excluded_semantic_field")
        return True

    def text(self, value: str) -> str:
        if len(value) <= 150:
            return value
        self.omit("text_truncated")
        return value[:150] + "…"

    def list_preview(self, values: list[object]) -> str:
        first = str(values[0])
        self.omit("list_text_truncated", int(len(first) > 80))
        preview = first[:80]
        if len(values) > 1:
            self.omit("list_items_omitted", len(values) - 1)
            preview += f" (+{len(values) - 1} more)"
        return preview

    def step_summary(self, result: object) -> str:
        if isinstance(result, dict):
            supplied = result.get("message") or result.get("result")
            if supplied:
                return str(supplied)
        rendered = str(result)
        self.omit("fallback_result_truncated", int(len(rendered) > 200))
        return rendered[:200]


def format_memory_facts(facts: list[str] | None) -> str:
    """Render the evaluator's existing memory argument verbatim."""
    if not facts:
        return "No relevant memories."
    return "Relevant user context:\n" + "\n".join(f"- {f}" for f in facts)


def format_tools_for_prompt(manifests: list[Any]) -> str:
    """Retain the evaluator's compact tool descriptions and parameter contract."""
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


def format_interests(profile: dict[str, Any], evidence: InitiativeEvidence | None = None) -> str:
    """Retain the evaluator's interest limit and expose actual omitted active interests."""
    interests = profile.get("interests", [])
    InitiativeEvidence.for_optional(evidence).omit(
        "interests_omitted",
        sum(i.get("status") == "active" for i in interests[INITIATIVE_INTERESTS_LIMIT:]),
    )
    active = [
        f"{i['topic']} ({i['category']})"
        for i in interests[:INITIATIVE_INTERESTS_LIMIT]
        if i.get("status") == "active"
    ]
    if not active:
        return "No known interests."
    return "User interests: " + ", ".join(active)


def named_initiative_state(
    arguments: dict[str, JsonValue],
    evidence: InitiativeEvidence,
    *,
    context: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    """Retain the exact policy and every dynamic argument without parsing source text."""
    template = load_prompt("initiative_prompt", version="v1")
    policy, marker, _ = template.partition("--- DYNAMIC CONTEXT (all variable data below) ---")
    if not marker:
        # A changed template cannot silently discard part of the policy.
        evidence.omit("context_unavailable")
        policy = template
    return {
        "initiative_policy": policy.format(**arguments),
        "context": (
            context
            if context is not None
            else {key: value for key, value in arguments.items() if key != "max_actions"}
        ),
        "evidence": {
            "complete": not evidence.omissions,
            "omissions": dict(evidence.omissions),
            "scope": "retrieved_turn_results",
        },
    }
