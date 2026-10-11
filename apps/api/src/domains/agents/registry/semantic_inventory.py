"""Offline inventory of native semantic contracts, including optional families.

Discovery follows manifest modules rather than feature flags: a disabled family
must still satisfy the integrity checks before a deployment enables it. This
does not connect to MCP servers; their contracts are request-scoped.
"""

from importlib import import_module
from pathlib import Path

from src.domains.agents.registry.catalogue import ToolManifest


def collect_static_manifests() -> list[ToolManifest]:
    """Collect every declared native manifest, deduplicating re-exports by name."""
    domains_dir = Path(__file__).resolve().parents[2]
    modules: set[str] = set()
    for family in ("agents", "skills"):
        for path in (domains_dir / family).rglob("*.py"):
            if "registry" in path.relative_to(domains_dir / family).parts:
                continue
            if "manifest" not in path.stem and path.stem != "catalogue_registration":
                continue
            relative = path.relative_to(domains_dir).with_suffix("")
            modules.add("src.domains." + ".".join(relative.parts))

    by_name: dict[str, ToolManifest] = {}
    for module_name in sorted(modules):
        module = import_module(module_name)
        for value in vars(module).values():
            candidates = value if isinstance(value, (list, tuple)) else (value,)
            for candidate in candidates:
                if isinstance(candidate, ToolManifest):
                    existing = by_name.get(candidate.name)
                    if existing is not None and existing != candidate:
                        raise ValueError(f"Conflicting manifests for {candidate.name!r}")
                    by_name[candidate.name] = candidate
    return [by_name[name] for name in sorted(by_name)]
