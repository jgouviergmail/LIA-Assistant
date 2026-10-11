"""Compact published field roles and presence constraints for planning."""

from collections.abc import Sequence

from src.domains.agents.registry.catalogue import OutputFieldSchema
from src.domains.agents.registry.value_contracts import SemanticFieldRole


def semantic_role_dict(role: SemanticFieldRole) -> dict[str, object]:
    return {
        "role": role.role,
        "entity_types": list(role.entity_types),
        "accepted_types": list(role.accepted_types),
        "predicates": list(role.predicates),
    }


def output_contracts(outputs: Sequence[OutputFieldSchema]) -> list[dict[str, object]]:
    contracts: list[dict[str, object]] = []
    for output in outputs:
        contract: dict[str, object] = {"path": output.path}
        if output.nullable:
            contract["nullable"] = True
        if output.semantic_role is not None:
            contract["semantic_role"] = semantic_role_dict(output.semantic_role)
        if len(contract) > 1:
            contracts.append(contract)
    return contracts
