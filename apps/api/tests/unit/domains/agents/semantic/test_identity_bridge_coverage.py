"""Reverse integrity + annotation ratchet for the domain graph (lot 4, A-03/A-06).

The existing integrity test validates one direction only: every DECLARED
``related_domains`` link must have a type bridge. The converse — a real
IDENTITY bridge with no declared adjacency — was checked nowhere, which is
how the graph stayed a contact-centric star (16 edges, 17 isolated domains)
while the initiative node went blind after half the executions.

Two additions:

1. **Reverse check on IDENTITY bridges only** — scalar types (datetime,
   language_code, recency_filter, URL…) bridge everything and mean nothing;
   identity types (person_name, email_address, phone_number,
   physical_address, coordinate) are what make a cross-domain follow-up
   worth considering. Any identity-bridged pair must be either declared or
   consciously allowlisted here.

2. **Annotation ratchet (A-06)** — the README froze coverage numbers that
   nothing protected (measured drift: params 53%→49%). Absolute counts are
   monotone-safe (a new untyped tool cannot red them; deleting annotations
   can): they may only grow.
"""

from __future__ import annotations

import pytest

from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

# Types whose presence on both sides of a pair makes a cross-domain
# follow-up MEANINGFUL (a person, an address, a reachable identity) — the
# scalar plumbing types deliberately excluded.
IDENTITY_BRIDGE_TYPES: frozenset[str] = frozenset(
    {
        "person_name",
        "email_address",
        "phone_number",
        "physical_address",
        "coordinate",
    }
)

# Identity-bridged pairs DELIBERATELY not declared as related_domains, each
# with its rationale. Shrink-only in spirit: promote an entry to a declared
# adjacency when the product case is made — never grow this list silently.
KNOWN_UNDECLARED_IDENTITY_BRIDGES: frozenset[tuple[str, str]] = frozenset(
    {
        # Telephony is cost-bearing (paid calls): auto-suggesting it as an
        # initiative adjacency needs an explicit product decision first.
        ("task", "telephony"),
        ("telephony", "task"),
        ("telephony", "peer"),
        ("peer", "telephony"),
        # peer→task via person_name: peer payload names are peer-scoped
        # display names, not task assignees — a follow-up adds noise.
        ("task", "peer"),
        ("peer", "task"),
        # peer↔contact: DOCUMENTED decision against (program_domain_configs,
        # runtime defect 2026-07-30 — contact tools pulled into every peer
        # plan, a missing Google scope then invalidated the whole plan).
        ("peer", "contact"),
        ("contact", "peer"),
        # contact is the universal hub: outward adjacencies would arm the
        # initiative after EVERY contact resolution (contacts are usually
        # mid-plan lookups, not the turn's subject). Revisit with usage data.
        ("contact", "weather"),
    }
)

# Annotation floors (A-06) — measured 2026-08-19; may only rise.
MIN_ANNOTATED_PARAMS = 125
MIN_ANNOTATED_OUTPUTS = 145
MIN_CONSUMED_ONTOLOGY_TYPES = 71


@pytest.fixture(scope="module")
def manifests() -> list:
    from tests.unit.domains.agents.semantic.test_semantic_registry_integrity import (
        _collect_static_manifests,
    )

    return _collect_static_manifests()


@pytest.fixture(scope="module")
def registry():
    from src.domains.agents.semantic.expansion_service import get_expansion_service

    return get_expansion_service().registry


def _produced_consumed(registry, manifests) -> tuple[dict, dict]:
    def _domain(m) -> str:
        agent = getattr(m, "agent", None)
        return str(agent).removesuffix("_agent") if agent else "unknown"

    tool_domain = {m.name: _domain(m) for m in manifests}
    produced: dict[str, set[str]] = {}
    consumed: dict[str, set[str]] = {}
    for type_def in registry.get_all():
        for domain in type_def.source_domains:
            produced.setdefault(domain, set()).add(type_def.name)
        for tool_name in type_def.used_in_tools:
            domain = tool_domain.get(tool_name)
            if domain:
                consumed.setdefault(domain, set()).add(type_def.name)
    for m in manifests:
        domain = _domain(m)
        for p in m.parameters or []:
            st = getattr(p, "semantic_type", None)
            if st:
                consumed.setdefault(domain, set()).add(st)
        for o in getattr(m, "outputs", None) or []:
            st = getattr(o, "semantic_type", None)
            if st:
                produced.setdefault(domain, set()).add(st)
    return produced, consumed


class TestReverseIdentityBridges:
    def test_every_identity_bridge_is_declared_or_allowlisted(self, registry, manifests) -> None:
        produced, consumed = _produced_consumed(registry, manifests)
        declared = {(a, b) for a, cfg in DOMAIN_REGISTRY.items() for b in cfg.related_domains}
        missing: list[str] = []
        for a in DOMAIN_REGISTRY:
            for b in DOMAIN_REGISTRY:
                if a == b:
                    continue
                bridge = produced.get(a, set()) & consumed.get(b, set()) & IDENTITY_BRIDGE_TYPES
                if not bridge:
                    continue
                if (a, b) in declared or (b, a) in declared:
                    continue
                if (a, b) in KNOWN_UNDECLARED_IDENTITY_BRIDGES:
                    continue
                missing.append(f"{a} -> {b} via {sorted(bridge)}")
        assert not missing, (
            "Identity-bridged pairs neither declared in related_domains nor "
            "consciously allowlisted (declare the adjacency, or record the "
            "pair with a rationale in KNOWN_UNDECLARED_IDENTITY_BRIDGES):\n"
            + "\n".join(sorted(missing))
        )

    def test_allowlist_is_not_stale(self, registry, manifests) -> None:
        """Every allowlisted pair must still be identity-bridged AND
        undeclared — otherwise the entry is dead weight to remove."""
        produced, consumed = _produced_consumed(registry, manifests)
        declared = {(a, b) for a, cfg in DOMAIN_REGISTRY.items() for b in cfg.related_domains}
        stale = []
        for a, b in KNOWN_UNDECLARED_IDENTITY_BRIDGES:
            bridge = produced.get(a, set()) & consumed.get(b, set()) & IDENTITY_BRIDGE_TYPES
            if not bridge or (a, b) in declared or (b, a) in declared:
                stale.append((a, b))
        assert not stale, f"Stale allowlist entries: {sorted(stale)}"


class TestAnnotationRatchet:
    def test_annotated_counts_never_shrink(self, manifests) -> None:
        params = sum(
            1 for m in manifests for p in (m.parameters or []) if getattr(p, "semantic_type", None)
        )
        outputs = sum(
            1
            for m in manifests
            for o in (getattr(m, "outputs", None) or [])
            if getattr(o, "semantic_type", None)
        )
        assert params >= MIN_ANNOTATED_PARAMS, (
            f"Annotated parameters shrank: {params} < floor {MIN_ANNOTATED_PARAMS} — "
            "restore the annotations; raise the floor after annotation work."
        )
        assert (
            outputs >= MIN_ANNOTATED_OUTPUTS
        ), f"Annotated outputs shrank: {outputs} < floor {MIN_ANNOTATED_OUTPUTS}"

    def test_consumed_ontology_types_never_shrink(self, registry, manifests) -> None:
        used = {
            st
            for m in manifests
            for field in [*(m.parameters or []), *(getattr(m, "outputs", None) or [])]
            if (st := getattr(field, "semantic_type", None))
        }
        all_types = {t.name for t in registry.get_all()}
        consumed = len(used & all_types)
        assert (
            consumed >= MIN_CONSUMED_ONTOLOGY_TYPES
        ), f"Consumed ontology types shrank: {consumed} < floor {MIN_CONSUMED_ONTOLOGY_TYPES}"


class TestNewAdjacencies:
    """The lot-4 declarations: real identity bridges promoted to adjacencies."""

    @pytest.mark.parametrize(
        ("domain", "related"),
        [("event", "email"), ("task", "contact")],
    )
    def test_adjacency_declared(self, domain: str, related: str) -> None:
        assert related in DOMAIN_REGISTRY[domain].related_domains, (
            f"{domain} -> {related} must be declared (identity bridge exists; "
            "initiative adjacency approved in lot 4)"
        )
