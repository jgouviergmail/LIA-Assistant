"""Fail closed on live-policy failure; never renumber a stale persisted list."""

from collections.abc import Mapping, Sequence

from src.domains.agents.context.registry import ContextTypeRegistry


async def context_read_allowed(
    owner: str, domain: str, items: Sequence[Mapping[str, object]]
) -> bool:
    try:
        definition = ContextTypeRegistry.get_definition(domain)
        return definition.read_guard is None or await definition.read_guard(owner, items)
    except Exception:
        # A callback can fail through any dependency; its private input never belongs in logs.
        return False
