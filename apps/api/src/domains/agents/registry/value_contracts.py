"""Lightweight semantic field contracts, without importing semantic services."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticFieldRole:
    """An explicit field contract, never a relation inferred from its name."""

    role: str
    entity_types: tuple[str, ...] = ()
    accepted_types: tuple[str, ...] = ()
    predicates: tuple[str, ...] = ()
    entity_predicates: tuple[tuple[str, str], ...] = ()
