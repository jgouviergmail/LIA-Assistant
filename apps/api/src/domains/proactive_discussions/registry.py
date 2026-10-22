"""Completeness guards for the shared discussion source catalogue."""

from collections.abc import Mapping

from src.domains.shared.discussion_catalogue import SOURCE_REGISTRY as SOURCE_REGISTRY
from src.domains.shared.discussion_catalogue import SourceDefinition as SourceDefinition
from src.domains.shared.discussion_sources import SourceKey


def assert_registry_complete(
    registry: Mapping[SourceKey, SourceDefinition], *, installed: frozenset[SourceKey] | None = None
) -> None:
    """Refuse to boot on an incomplete or incoherent source catalogue (ADR-085).

    Args:
        registry: The source catalogue.
        installed: The source keys whose ports are installed, when known.

    Raises:
        RuntimeError: A source is missing or unknown, a dependency is invalid, a
            capability is incomplete, or the installed ports differ from the
            catalogue.
    """
    if set(registry) != set(SourceKey):
        raise RuntimeError("Discussion source catalogue is incomplete or names an unknown source")
    for key, definition in registry.items():
        if key in definition.dependencies or not set(definition.dependencies).issubset(registry):
            raise RuntimeError("Discussion source dependency is invalid")
        if not definition.domain or not definition.operations:
            raise RuntimeError("Discussion source capability is incomplete")
    if installed is not None and installed != frozenset(registry):
        raise RuntimeError("Discussion source ports differ from the published catalogue")


assert_registry_complete(SOURCE_REGISTRY)
