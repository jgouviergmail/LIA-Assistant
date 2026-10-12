"""The ontology's editorial links say what the code does — and nothing else.

``test_semantic_registry_integrity.py`` holds the NAMES together (a tool, a
domain, a type that exists). This module holds the CLAIMS: the planner's
semantic-dependencies section renders « <type>: provided by [domains], used by
[tools] » from ``source_domains`` and ``used_in_tools`` (``expansion_service``),
so a domain declared to produce a value it never produces is a false lead
handed to the planner. Measured 2026-10-11: 41 value types declared such a
producer (``search_mode`` « provided by place », a files parameter), 12 types
were annotated by nothing, and the examples of 9 enumerations were values the
code never emits or refuses (ADR-120 amendment 2026-10-11).

Entity types (those with ``properties``) are out of scope: their links name the
domains and tools that handle the ENTITY, which no annotation carries.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from src.domains.agents.registry.domain_taxonomy import domain_of_agent
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.semantic.expansion_service import (
    get_expansion_service,
    parameter_semantic_types,
)
from src.infrastructure.mcp.semantic_schema import _FORMAT_TYPES, _SCALAR_STRING_TYPES

pytestmark = pytest.mark.unit

#: Pseudo-domain of internal, orchestration-level types (see the integrity test).
PSEUDO_DOMAINS = frozenset({"agents"})
#: Types a third-party MCP schema may name through a format or a hint
#: (``infrastructure/mcp/semantic_schema.py``): alive without a native annotation.
MCP_HINT_TYPES = frozenset(_FORMAT_TYPES.values()) | frozenset(_SCALAR_STRING_TYPES)


@pytest.fixture(scope="module")
def manifests() -> list[Any]:
    return collect_static_manifests()


@pytest.fixture(scope="module")
def types() -> list[Any]:
    return list(get_expansion_service().registry.get_all())


def _value_types(types: list[Any]) -> Iterator[Any]:
    return (t for t in types if not t.properties)


def _producers(manifests: list[Any]) -> dict[str, set[str]]:
    """Domains whose static tools OUTPUT each type, through the taxonomy's agent rule."""
    producers: dict[str, set[str]] = {}
    for manifest in manifests:
        domain = domain_of_agent(manifest.agent)
        for output in manifest.outputs or []:
            if output.semantic_type and domain:
                producers.setdefault(output.semantic_type, set()).add(domain)
    return producers


def _annotators(manifests: list[Any]) -> dict[str, set[str]]:
    """Tools whose parameters (nested schemas included) or outputs carry each type."""
    annotators: dict[str, set[str]] = {}
    for manifest in manifests:
        for param in manifest.parameters or []:
            for semantic_type in parameter_semantic_types(param):
                annotators.setdefault(semantic_type, set()).add(manifest.name)
        for output in manifest.outputs or []:
            if output.semantic_type:
                annotators.setdefault(output.semantic_type, set()).add(manifest.name)
    return annotators


def test_a_declared_producer_produces_the_value(types: list[Any], manifests: list[Any]) -> None:
    producers = _producers(manifests)
    phantoms = [
        f"{t.name}: {sorted(set(t.source_domains) - PSEUDO_DOMAINS - producers.get(t.name, set()))}"
        for t in _value_types(types)
        if set(t.source_domains) - PSEUDO_DOMAINS - producers.get(t.name, set())
    ]
    assert not phantoms, (
        "source_domains names a domain whose tools never OUTPUT the type — the planner "
        "is told « provided by » a domain that cannot provide it. Annotate the real "
        "output (verify the payload first, ADR-121) or drop the domain:\n" + "\n".join(phantoms)
    )


def test_a_declared_consumer_carries_the_type(types: list[Any], manifests: list[Any]) -> None:
    annotators = _annotators(manifests)
    phantoms = [
        f"{t.name}: {sorted(set(t.used_in_tools) - annotators.get(t.name, set()))}"
        for t in _value_types(types)
        if set(t.used_in_tools) - annotators.get(t.name, set())
    ]
    assert not phantoms, "used_in_tools names a tool that never carries the type:\n" + "\n".join(
        phantoms
    )


def test_every_value_type_is_read_somewhere(types: list[Any], manifests: list[Any]) -> None:
    annotated = set(_annotators(manifests))
    parents = {t.parent for t in types if t.parent}
    entity_properties = {name for t in types for name in t.properties.values()}
    dead = sorted(
        t.name
        for t in _value_types(types)
        if t.name not in annotated | parents | entity_properties | MCP_HINT_TYPES
    )
    assert not dead, (
        "Registered types nothing annotates, inherits, composes or hints — "
        f"wire them or delete them: {dead}"
    )


def test_examples_of_a_published_enumeration_are_members(
    types: list[Any], manifests: list[Any]
) -> None:
    """When EVERY parameter consuming a type publishes its values, examples are among them."""
    vocabularies: dict[str, list[set[str] | None]] = {}
    for manifest in manifests:
        for param in manifest.parameters or []:
            if param.semantic_type:
                enum = next(
                    (set(c.value) for c in param.constraints or [] if c.kind == "enum"), None
                )
                vocabularies.setdefault(param.semantic_type, []).append(enum)
    stray = []
    for t in _value_types(types):
        published = vocabularies.get(t.name)
        if not published or any(enum is None for enum in published) or not t.examples:
            continue
        allowed = set().union(*[enum for enum in published if enum is not None])
        if set(t.examples) - allowed:
            stray.append(f"{t.name}: {sorted(set(t.examples) - allowed)} not in {sorted(allowed)}")
    assert not stray, "Examples outside the published vocabulary:\n" + "\n".join(stray)


def test_the_guard_reads_a_qualified_family_as_its_domain() -> None:
    assert domain_of_agent("devops_diagnostics_agent") == "devops"
    assert domain_of_agent("web_search_agent") == "web_search"
    assert domain_of_agent("python_sandbox_agent") is None
