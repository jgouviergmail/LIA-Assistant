"""Cross-integrity tests: semantic TypeRegistry ↔ tool manifests ↔ domain taxonomy.

The semantic layer has three sources that must stay aligned:

1. ``core_types.py`` — the static ontology (types, hierarchy, editorial
   ``used_in_tools`` / ``source_domains`` links).
2. ``catalogue_manifests.py`` modules — the live tool layer, whose
   ``semantic_type`` annotations on parameters/outputs are the source of
   truth for what each tool actually consumes/produces.
3. ``DOMAIN_REGISTRY`` — the coarse product-level adjacency
   (``related_domains``) used by the initiative pre-filter and routing.

History: tool renames (naming v3.2) silently orphaned ~half of the ontology's
``used_in_tools`` references, degrading the planner's semantic dependencies
section and starving the initiative's connection candidates. These tests make
that class of drift impossible.
"""

from __future__ import annotations

import importlib
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import pytest

from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
from src.domains.agents.semantic.expansion_service import get_expansion_service

# Pseudo-domains used in source_domains that are not functional domains in
# DOMAIN_REGISTRY. "agents" marks internal/orchestration-level types
# (confidence_score, markdown_text, language_code).
ALLOWED_PSEUDO_DOMAINS: frozenset[str] = frozenset({"agents"})

# related_domains declared in the taxonomy that no semantic type bridge
# justifies (in either direction). These are legitimate PRODUCT adjacencies
# ("often used together") without a formal data pivot. Adding a new entry
# here must be a conscious decision — prefer annotating manifests with
# semantic_type so the bridge becomes mechanical.
KNOWN_UNBRIDGED_RELATED_DOMAINS: frozenset[tuple[str, str]] = frozenset(
    {
        ("file", "contact"),
        ("reminder", "contact"),
        # P4 (interdomain program Lot 1) — initiative-node product adjacencies:
        # events generate follow-up work (event→task) and emails carry
        # attachments living in the cloud drive (email→file). No typed
        # parameter pivot exists yet; the chaining guidance lives in the
        # planner/ReAct prompts (CROSS-DOMAIN CHAINS blocks).
        ("event", "task"),
        ("email", "file"),
        # Peers program (ADR-180): routing-level adjacency only — peer tool
        # payloads expose peer-scoped names/slots, not contact/event resource
        # ids. Annotating a bridge without a REAL payload pivot would violate
        # the ADR-121 doctrine (never tag an output without verifying the
        # actual payload); bridge when one exists.
        ("peer", "event"),
    }
)


def _collect_static_manifests() -> list[Any]:
    """Import every static catalogue_manifests module and collect ToolManifests.

    Deduplicated by tool name (modules may re-import shared manifests).
    Dynamic manifests (MCP servers, user tools) are out of scope — they are
    discovered at runtime and never referenced by the static ontology.
    """
    import src.domains.agents as agents_pkg

    base = Path(agents_pkg.__file__).parent
    module_names = [
        f"src.domains.agents.{child.name}.catalogue_manifests"
        for child in sorted(base.iterdir())
        if (child / "catalogue_manifests.py").is_file()
    ]
    module_names.append("src.domains.skills.catalogue_manifests")

    by_name: dict[str, Any] = {}
    for module_name in module_names:
        module = importlib.import_module(module_name)
        for value in vars(module).values():
            if isinstance(value, ToolManifest):
                by_name[value.name] = value
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, ToolManifest):
                        by_name[item.name] = item
    return list(by_name.values())


@pytest.fixture(scope="module")
def manifests() -> list[Any]:
    return _collect_static_manifests()


@pytest.fixture(scope="module")
def registry() -> Any:
    return get_expansion_service().registry


def _manifest_domain(manifest: Any) -> str:
    agent = getattr(manifest, "agent", None) or ""
    return agent.removesuffix("_agent")


@pytest.mark.unit
class TestRegistryReferencesRealTools:
    """The ontology's editorial links must reference tools that exist."""

    def test_used_in_tools_reference_existing_tools(
        self, registry: Any, manifests: list[Any]
    ) -> None:
        real_names = {m.name for m in manifests}
        assert real_names, "manifest collection is empty — collector is broken"

        phantoms: list[str] = []
        for type_def in registry.get_all():
            for tool_name in type_def.used_in_tools:
                if tool_name not in real_names:
                    hint = get_close_matches(tool_name, real_names, n=1)
                    phantoms.append(
                        f"{type_def.name}: '{tool_name}'"
                        + (f" (did you mean '{hint[0]}'?)" if hint else "")
                    )
        assert not phantoms, (
            "core_types.py references tools that do not exist in any "
            "catalogue_manifests module:\n" + "\n".join(sorted(phantoms))
        )

    def test_internal_type_references_exist(self, registry: Any) -> None:
        """parent / related_types / broader_types / narrower_types must all
        reference registered types (ontology self-consistency)."""
        names = {t.name for t in registry.get_all()}
        dangling: list[str] = []
        for type_def in registry.get_all():
            refs = [
                *type_def.related_types,
                *type_def.broader_types,
                *type_def.narrower_types,
                *([type_def.parent] if type_def.parent else []),
            ]
            for ref in refs:
                if ref not in names:
                    dangling.append(f"{type_def.name}: '{ref}'")
        assert not dangling, "Dangling internal type references in core_types.py:\n" + "\n".join(
            sorted(dangling)
        )

    def test_source_domains_exist_in_domain_registry(self, registry: Any) -> None:
        valid = set(DOMAIN_REGISTRY) | ALLOWED_PSEUDO_DOMAINS
        unknown: list[str] = []
        for type_def in registry.get_all():
            for domain in type_def.source_domains:
                if domain not in valid:
                    unknown.append(f"{type_def.name}: '{domain}'")
        assert not unknown, (
            "core_types.py references source_domains absent from DOMAIN_REGISTRY "
            "(domain vocabulary is SINGULAR — 'contact', not 'contacts'):\n"
            + "\n".join(sorted(unknown))
        )


@pytest.mark.unit
class TestManifestSemanticTypesRegistered:
    """Every semantic_type annotation in manifests must name a registered type."""

    def test_parameter_and_output_semantic_types_exist(
        self, registry: Any, manifests: list[Any]
    ) -> None:
        registered = {t.name for t in registry.get_all()}
        unknown: list[str] = []
        for manifest in manifests:
            for param in manifest.parameters or []:
                st = getattr(param, "semantic_type", None)
                if st and st not in registered:
                    unknown.append(f"{manifest.name} (param '{param.name}'): '{st}'")
            for output in getattr(manifest, "outputs", None) or []:
                st = getattr(output, "semantic_type", None)
                if st and st not in registered:
                    unknown.append(f"{manifest.name} (output '{output.path}'): '{st}'")
        assert not unknown, (
            "Manifests declare semantic_type values not registered in the "
            "TypeRegistry (typo or missing core_types entry):\n" + "\n".join(sorted(unknown))
        )


@pytest.mark.unit
class TestEveryRequiredHandleHasAReadOnlySource:
    """A required semantic type nobody can READ is a dead end by construction.

    The catalogue closure repairs a catalogue that merely *omitted* the source
    of a required handle. It cannot invent one. A tool declaring a REQUIRED
    parameter whose type no read-only tool produces is therefore unplannable in
    every catalogue, whatever the scores — the exact shape of the 2026-07-30
    incident, one step earlier in the chain.

    Read-only is the operative word: ``send_email_tool`` outputs a
    ``message_id`` too, and accepting a mutation as a source would let this
    guard pass on a catalogue that still cannot run.
    """

    def test_required_semantic_types_are_all_sourceable(self, manifests: list[Any]) -> None:
        from src.domains.agents.registry.catalogue import is_read_only_tool

        sources: dict[str, set[str]] = {}
        for manifest in manifests:
            if not is_read_only_tool(manifest):
                continue
            for output in getattr(manifest, "outputs", None) or []:
                semantic_type = getattr(output, "semantic_type", None)
                if semantic_type:
                    sources.setdefault(semantic_type, set()).add(manifest.name)

        dead_ends: list[str] = []
        for manifest in manifests:
            for param in manifest.parameters or []:
                semantic_type = getattr(param, "semantic_type", None)
                if not semantic_type or not getattr(param, "required", False):
                    continue
                if not sources.get(semantic_type, set()) - {manifest.name}:
                    dead_ends.append(
                        f"{manifest.name} (param '{param.name}') requires "
                        f"'{semantic_type}', which no read-only tool produces"
                    )

        assert not dead_ends, (
            "Required semantic types with no read-only producer — the planner "
            "can never obtain them, so no valid plan exists. Either annotate "
            "the listing tool's output with the type, or drop the annotation "
            "if the tool actually resolves the value itself (as the peer, hue "
            "and wikipedia tools do):\n" + "\n".join(sorted(dead_ends))
        )


@pytest.mark.unit
class TestTaxonomyTypeBridgeCoverage:
    """Each related_domains link should be justified by at least one type bridge.

    A link (a, b) is justified when some semantic type is PRODUCED by one side
    (source_domains or manifest output annotation) and CONSUMED by a tool of
    the other side (used_in_tools or manifest parameter annotation), in either
    direction. Product-only adjacencies without a data pivot must be listed in
    KNOWN_UNBRIDGED_RELATED_DOMAINS — consciously.
    """

    def test_related_domains_have_type_bridges(self, registry: Any, manifests: list[Any]) -> None:
        tool_domain = {m.name: _manifest_domain(m) for m in manifests}

        produced: dict[str, set[str]] = {}  # domain -> type names it provides
        consumed: dict[str, set[str]] = {}  # domain -> type names its tools consume

        for type_def in registry.get_all():
            for domain in type_def.source_domains:
                produced.setdefault(domain, set()).add(type_def.name)
            for tool_name in type_def.used_in_tools:
                domain = tool_domain.get(tool_name)
                if domain:
                    consumed.setdefault(domain, set()).add(type_def.name)

        for manifest in manifests:
            domain = _manifest_domain(manifest)
            for param in manifest.parameters or []:
                st = getattr(param, "semantic_type", None)
                if st:
                    consumed.setdefault(domain, set()).add(st)
            for output in getattr(manifest, "outputs", None) or []:
                st = getattr(output, "semantic_type", None)
                if st:
                    produced.setdefault(domain, set()).add(st)

        def bridged(a: str, b: str) -> bool:
            forward = produced.get(a, set()) & consumed.get(b, set())
            backward = produced.get(b, set()) & consumed.get(a, set())
            return bool(forward or backward)

        unbridged: list[str] = []
        for domain_name, config in DOMAIN_REGISTRY.items():
            for related in config.related_domains:
                pair = (domain_name, related)
                if pair in KNOWN_UNBRIDGED_RELATED_DOMAINS:
                    continue
                if not bridged(domain_name, related):
                    unbridged.append(f"{domain_name} -> {related}")

        assert not unbridged, (
            "related_domains links without any semantic type bridge. Either add "
            "semantic_type annotations to the relevant manifests (preferred) or "
            "record the pair in KNOWN_UNBRIDGED_RELATED_DOMAINS with a rationale:\n"
            + "\n".join(sorted(unbridged))
        )

    def test_known_unbridged_list_is_not_stale(self, registry: Any, manifests: list[Any]) -> None:
        """Entries in the allowlist must still exist in the taxonomy — and be
        removed from the allowlist once a real type bridge appears."""
        declared_pairs = {
            (domain_name, related)
            for domain_name, config in DOMAIN_REGISTRY.items()
            for related in config.related_domains
        }
        stale = KNOWN_UNBRIDGED_RELATED_DOMAINS - declared_pairs
        assert not stale, f"Allowlist entries no longer declared in the taxonomy: {sorted(stale)}"
