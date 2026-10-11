"""Finite, constructive read-only source paths for catalogue semantic requirements."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from src.domains.agents.registry.catalogue import ToolManifest, is_read_only_tool
from src.domains.agents.semantic.manifest_semantics import required_parameter_type_options
from src.domains.agents.semantic.semantic_type import is_semantic_pivot


def required_type_groups(
    manifest: ToolManifest, seeded_parameters: Collection[str] = ()
) -> tuple[frozenset[str], ...]:
    """Only exact, independently validated parameter seeds remove prerequisites."""
    return tuple(
        admitted
        for parameter in getattr(manifest, "parameters", ())
        if parameter.name not in seeded_parameters
        for options in required_parameter_type_options(parameter)
        if (admitted := frozenset(name for name in options if is_semantic_pivot(name)))
    )


def produced_types(manifest: ToolManifest) -> set[str]:
    return {
        output.semantic_type
        for output in getattr(manifest, "outputs", ())
        if output.semantic_type and is_semantic_pivot(output.semantic_type)
    }


@dataclass
class SourcePaths:
    """Declared paths that can start, with their full prerequisite tools in order."""

    paths: dict[str, tuple[str, ...]] = field(default_factory=dict)
    providers: dict[str, set[str]] = field(default_factory=dict)
    blocked: set[str] = field(default_factory=set)


def _best_ancestor(
    options: frozenset[str], index: SourcePaths, scores: Mapping[str, float]
) -> tuple[str, ...]:
    candidates = set().union(*(index.providers.get(name, set()) for name in options))
    name = min(candidates, key=lambda item: (len(index.paths[item]), -scores.get(item, 0.0), item))
    return index.paths[name]


def _source_path(
    manifest: ToolManifest,
    requirements: tuple[frozenset[str], ...],
    index: SourcePaths,
    scores: Mapping[str, float],
) -> tuple[str, ...]:
    ancestors: list[str] = []
    for options in requirements:
        ancestors.extend(_best_ancestor(options, index, scores))
    return tuple(dict.fromkeys([*ancestors, manifest.name]))


def _add_ready_sources(
    ready: Sequence[ToolManifest],
    index: SourcePaths,
    requirements: Mapping[str, tuple[frozenset[str], ...]],
    scores: Mapping[str, float],
) -> None:
    # Compute every path against the previous frontier. A sibling output must
    # not appear to precede its own prerequisite within the same frontier.
    paths = {
        manifest.name: _source_path(manifest, requirements[manifest.name], index, scores)
        for manifest in ready
    }
    index.paths.update(paths)
    for manifest in ready:
        for type_name in produced_types(manifest):
            index.providers.setdefault(type_name, set()).add(manifest.name)


def construct_source_paths(
    manifests: Sequence[ToolManifest],
    scores: Mapping[str, float],
    seeded_parameters: Mapping[str, Collection[str]],
) -> SourcePaths:
    """A bounded fixed point: no source can bootstrap itself or an unseeded cycle."""
    pending = {manifest.name: manifest for manifest in manifests if is_read_only_tool(manifest)}
    requirements = {
        name: required_type_groups(manifest, seeded_parameters.get(name, ()))
        for name, manifest in pending.items()
    }
    index = SourcePaths()
    for _ in range(len(pending)):
        ready = [
            pending[name]
            for name in sorted(pending)
            if all(options & index.providers.keys() for options in requirements[name])
        ]
        if not ready:
            break
        _add_ready_sources(ready, index, requirements, scores)
        for manifest in ready:
            del pending[manifest.name]
    index.blocked = set(pending)
    return index
