"""Close catalogues with finite, constructive read-only source paths.

A declared producer counts only if its prerequisite path can start without a
cycle, or with an independently verified value for an exact parameter. Every
ancestor on the chosen path is retained. Mutations never discover an existing
handle. Missing sources and unseeded cycles remain explicit gaps; consumers
selected by the request are not removed to conceal them.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.services.catalogue.source_paths import (
    SourcePaths,
    construct_source_paths,
    required_type_groups,
)

# Retained as a compatibility export for diagnostics; constructive termination
# is bounded by the candidate count and never truncates a finite source chain.
MAX_CLOSURE_ROUNDS = 3


@dataclass(frozen=True)
class ClosureResult:
    """Outcome of a closure computation over a filtered catalogue.

    Attributes:
        additions: Provider tool names to add, in the order they were resolved.
        consumers: Names of already-kept tools that had at least one unsatisfied
            required type when the closure started — including those for which
            no provider could be found. Callers must not evict them to make
            room: dropping a consumer strands the provider added for it, and
            the over-inclusion is harmless (the query selected them anyway).
    """

    additions: list[str] = field(default_factory=list)
    consumers: set[str] = field(default_factory=set)
    unresolved: dict[str, set[str]] = field(default_factory=dict)
    blocked_providers: set[str] = field(default_factory=set)

    def __bool__(self) -> bool:
        """True when runnable provider tools should be added."""
        return bool(self.additions)


def _domain_of(manifest: ToolManifest) -> str:
    """Functional domain owning a manifest (email_agent -> email)."""
    return (getattr(manifest, "agent", "") or "").removesuffix("_agent")


def _constructive_unsatisfied(
    manifests: Sequence[ToolManifest],
    index: SourcePaths,
    seeds: Mapping[str, Collection[str]],
) -> dict[frozenset[str], set[str]]:
    """A kept provider counts only when its complete startup path is also kept."""
    names = {manifest.name for manifest in manifests}
    unsatisfied: dict[frozenset[str], set[str]] = {}
    for manifest in manifests:
        for options in required_type_groups(manifest, seeds.get(manifest.name, ())):
            sources = set().union(*(index.providers.get(name, set()) for name in options))
            sources.discard(manifest.name)
            if any(set(index.paths[source]) <= names for source in sources):
                continue
            unsatisfied.setdefault(options, set()).add(manifest.name)
    return unsatisfied


def _gaps_by_consumer(
    unresolved: Mapping[frozenset[str], set[str]],
) -> dict[str, set[str]]:
    gaps: dict[str, set[str]] = {}
    for options, names in unresolved.items():
        for name in names:
            gaps.setdefault(name, set()).update(options)
    return gaps


def catalogue_source_gaps(
    kept: Sequence[ToolManifest],
    candidates: Sequence[ToolManifest],
    *,
    seeded_parameters: Mapping[str, Collection[str]] | None = None,
) -> dict[str, set[str]]:
    """Report the actual offered catalogue, including ancestors lost to its tool cap."""
    seeds = seeded_parameters or {}
    pool = {manifest.name: manifest for manifest in [*candidates, *kept]}
    index = construct_source_paths(list(pool.values()), {}, seeds)
    return _gaps_by_consumer(_constructive_unsatisfied(kept, index, seeds))


def _add_constructive_provider(
    options: frozenset[str],
    consumers: set[str],
    pool: Mapping[str, ToolManifest],
    kept: dict[str, ToolManifest],
    index: SourcePaths,
    scores: Mapping[str, float],
    additions: list[str],
) -> None:
    """Prefer a runnable path before domain/ranking preferences, then retain every ancestor."""
    eligible = set().union(*(index.providers.get(name, set()) for name in options)) - consumers
    if not eligible:
        return
    consumer_domains = {_domain_of(kept[name]) for name in consumers}
    provider = min(
        eligible,
        key=lambda name: (
            len(set(index.paths[name]) - kept.keys()),
            _domain_of(pool[name]) not in consumer_domains,
            -scores.get(name, 0.0),
            name,
        ),
    )
    for name in index.paths[provider]:
        if name not in kept:
            kept[name] = pool[name]
            additions.append(name)


def resolve_closure_additions(
    kept_manifests: Sequence[Any],
    candidate_manifests: Sequence[Any],
    tool_scores: Mapping[str, float] | None = None,
    *,
    seeded_parameters: Mapping[str, Collection[str]] | None = None,
) -> ClosureResult:
    """Compute the tools to add so the catalogue becomes closed.

    Args:
        kept_manifests: Manifests that survived filtering.
        candidate_manifests: Manifests eligible for the active domains.
        tool_scores: Semantic scores per tool name, used only to rank providers
            against one another — never to decide whether to add one.

    Returns:
        A ClosureResult. Empty when the catalogue is already closed, which is
        the overwhelmingly common case (a read-only request selects a read-only
        tool, which requires no handle).
    """
    scores = tool_scores or {}
    kept_by_name: dict[str, Any] = {manifest.name: manifest for manifest in kept_manifests}
    additions: list[str] = []

    seeds = seeded_parameters or {}
    pool = {manifest.name: manifest for manifest in [*candidate_manifests, *kept_manifests]}
    index = construct_source_paths(list(pool.values()), scores, seeds)
    initial = _constructive_unsatisfied(list(kept_by_name.values()), index, seeds)
    consumers = {name for names in initial.values() for name in names}
    for options in sorted(initial, key=lambda group: tuple(sorted(group))):
        _add_constructive_provider(
            options, initial[options], pool, kept_by_name, index, scores, additions
        )
    unresolved_by_type = _constructive_unsatisfied(list(kept_by_name.values()), index, seeds)
    unresolved = _gaps_by_consumer(unresolved_by_type)
    return ClosureResult(additions, consumers, unresolved, index.blocked)


__all__ = [
    "MAX_CLOSURE_ROUNDS",
    "ClosureResult",
    "resolve_closure_additions",
    "catalogue_source_gaps",
]
