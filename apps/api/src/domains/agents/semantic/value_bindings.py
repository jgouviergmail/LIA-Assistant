"""Field-level semantic evidence, kept beside values rather than rewriting them."""

import re
from collections.abc import Collection, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from src.domains.agents.registry.value_contracts import SemanticFieldRole

ScalarValue = str | int | float | bool | None
BindingStatus = Literal["present", "missing", "declared", "unusable"]

SEMANTIC_VALUE_BINDINGS_KEY = "semantic_value_bindings"
SEMANTIC_SOURCE_OBSERVATIONS_KEY = "semantic_source_observations"
SEMANTIC_SOURCE_VALID_AFTER_KEY = "semantic_source_valid_after"


class SemanticValueBinding(BaseModel):
    """Evidence for one unchanged value at one exact target parameter path.

    A declared output is not an observed value. Sources and account scope are
    independently supplied by the server; a planner-authored binding alone
    cannot authorize an exemption from the person/address guard.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    path: str
    value: ScalarValue
    semantic_type: str
    source_ref: str
    account_id: str
    status: BindingStatus
    entity_type: str | None = None
    entity_ref: str | None = None
    predicate: str | None = None
    role: str | None = None


def parse_value_bindings(value: object) -> tuple[SemanticValueBinding, ...]:
    """Decode checkpoint/config evidence; malformed observations confer no trust."""
    if not isinstance(value, list | tuple):
        return ()
    bindings: list[SemanticValueBinding] = []
    for item in value:
        try:
            bindings.append(SemanticValueBinding.model_validate(item))
        except ValidationError:
            continue
    return tuple(bindings)


def _binding_matches_scope(
    binding: SemanticValueBinding,
    path: str,
    value: ScalarValue,
    account_id: str | None,
    known_source_refs: Collection[str],
) -> bool:
    """Only a present, scoped, known observation can justify using a value."""
    return (
        binding.status == "present"
        and binding.value is not None
        and binding.path == path
        and type(binding.value) is type(value)
        and binding.value == value
        and bool(account_id)
        and binding.account_id == account_id
        and binding.source_ref in known_source_refs
        and bool(binding.entity_ref)
    )


def binding_matches_role(
    binding: SemanticValueBinding, semantic_type: str, expected_role: SemanticFieldRole
) -> bool:
    """Require an explicitly admitted value type, entity, predicate and role."""
    accepted_types = set(expected_role.accepted_types) | {semantic_type}
    return (
        binding.semantic_type in accepted_types
        and binding.role == expected_role.role
        and bool(expected_role.entity_types)
        and binding.entity_type in expected_role.entity_types
        and bool(expected_role.predicates)
        and binding.predicate in expected_role.predicates
        and (
            not expected_role.entity_predicates
            or (binding.entity_type, binding.predicate) in expected_role.entity_predicates
        )
    )


def _binding_matches_observation(
    binding: SemanticValueBinding, observed: SemanticValueBinding | None
) -> bool:
    """A source reference does not authorize relabelling its value or identity."""
    if observed is None or observed.status != "present":
        return False
    facts = (
        "value",
        "semantic_type",
        "source_ref",
        "account_id",
        "entity_type",
        "entity_ref",
        "predicate",
        "role",
    )
    return type(binding.value) is type(observed.value) and all(
        getattr(binding, fact) == getattr(observed, fact) for fact in facts
    )


def value_binding_exempts_collision(
    bindings: Sequence[SemanticValueBinding],
    *,
    path: str,
    value: ScalarValue,
    semantic_type: str,
    expected_role: SemanticFieldRole | None,
    account_id: str | None,
    known_sources: Mapping[str, SemanticValueBinding],
) -> bool:
    """Exempt a textual collision only after independently scoped role evidence."""
    if expected_role is None:
        return False
    return any(
        _binding_matches_scope(binding, path, value, account_id, known_sources)
        and _binding_matches_observation(binding, known_sources.get(binding.source_ref))
        and binding_matches_role(binding, semantic_type, expected_role)
        for binding in bindings
    )


def usable_binding_sources(
    bindings: Sequence[SemanticValueBinding],
    account_id: str,
    known_sources: Mapping[str, SemanticValueBinding],
) -> tuple[SemanticValueBinding, ...]:
    """Observed scalar sources only; declarations and unusable paths never seed a plan."""
    return tuple(
        binding
        for binding in bindings
        if _binding_matches_scope(binding, binding.path, binding.value, account_id, known_sources)
        and _binding_matches_observation(binding, known_sources.get(binding.source_ref))
    )


def source_observation(
    *,
    source_ref: str,
    source_path: str,
    value: ScalarValue,
    present: bool,
    semantic_type: str,
    account_id: str,
    entity_type: str | None = None,
    entity_ref: str | None = None,
    predicate: str | None = None,
    role: str | None = None,
    unusable_paths: Collection[str] = (),
    observations_complete: bool = True,
) -> SemanticValueBinding:
    """Project an observed leaf without changing its value, path or source reference.

    The caller supplies presence from the actual payload. An MCP observation
    declaring the field unusable takes precedence over that payload presence.
    """
    status: BindingStatus = "present" if present and value is not None else "missing"
    if not observations_complete and status == "present":
        status = "declared"
    if _source_path_is_unusable(source_path, unusable_paths):
        status = "unusable"
    return SemanticValueBinding(
        path=source_path,
        value=value,
        semantic_type=semantic_type,
        source_ref=source_ref,
        account_id=account_id,
        status=status,
        entity_type=entity_type,
        entity_ref=entity_ref,
        predicate=predicate,
        role=role,
    )


def _source_path_is_unusable(path: str, unusable_paths: Collection[str]) -> bool:
    """A bad array item never poisons its valid siblings; only declared [] is generic."""
    abstract = re.sub(r"\[\d+\]", "[]", path)
    return any(
        candidate == path or ("[]" in candidate and candidate == abstract)
        for candidate in unusable_paths
    )


def parse_source_observations(value: object) -> dict[str, SemanticValueBinding]:
    """Read canonical source observations independently from proposed target bindings."""
    if not isinstance(value, dict):
        return {}
    sources: dict[str, SemanticValueBinding] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        try:
            observed = SemanticValueBinding.model_validate(item)
        except ValidationError:
            continue
        if observed.source_ref == key:
            sources[key] = observed
    return sources


# The evidence a guarded value is checked against: the canonical fields
# selected this turn, the account the call runs for, their source observations.
type BindingScope = tuple[
    tuple[SemanticValueBinding, ...], str | None, dict[str, SemanticValueBinding]
]


def binding_scope_from_config(config: Mapping[str, object]) -> BindingScope:
    """Read serializable server-side binding evidence from a RunnableConfig."""
    configurable = config.get("configurable")
    metadata = config.get("metadata")
    values = configurable if isinstance(configurable, dict) else {}
    identity = metadata if isinstance(metadata, dict) else {}
    account = identity.get("user_id")
    return (
        parse_value_bindings(values.get(SEMANTIC_VALUE_BINDINGS_KEY)),
        account if isinstance(account, str) else None,
        parse_source_observations(values.get(SEMANTIC_SOURCE_OBSERVATIONS_KEY)),
    )
