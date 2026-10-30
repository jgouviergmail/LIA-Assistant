"""The two Redis scripts of the briefing section cache, on top of any test double's get/set/delete.

``section_outcomes`` writes a section through ONE script (clear the attempt
marker, then write only if no push bumped the section's generation since the
read began) and bumps a generation through another. Every briefing test double
that stores sections needs the same semantics; written once here, a double
gains them by delegating its ``eval`` to :func:`briefing_eval`.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.domains.briefing.section_outcomes import BUMP_GENERATION_SCRIPT, FENCED_WRITE_SCRIPT


class SectionStoreDouble(Protocol):
    """The three operations a briefing test double already has."""

    async def get(self, key: str) -> Any: ...

    async def set(self, key: str, value: str, *, ex: int) -> Any: ...

    async def delete(self, *keys: str) -> int: ...


async def briefing_eval(store: SectionStoreDouble, script: str, *args: Any) -> Any:
    """Run one of the section cache's scripts with its real semantics.

    Args:
        store: The double holding the keys.
        script: The Lua source ``section_outcomes`` sent.
        *args: The script's keys then its arguments, as redis-py passes them
            after ``numkeys``.

    Returns:
        What Redis would return.

    Raises:
        AssertionError: Any other script — the double must not answer for it.
    """
    if script == FENCED_WRITE_SCRIPT:
        cache_key, generation_key, marker_key, payload, expected, ttl = (str(a) for a in args)
        cleared = await store.delete(marker_key)
        current = await store.get(generation_key)
        if str(current if current is not None else "0") != expected:
            return [0, cleared]
        await store.set(cache_key, payload, ex=int(ttl))
        return [1, cleared]
    if script == BUMP_GENERATION_SCRIPT:
        key, ttl = str(args[0]), int(args[1])
        value = int((await store.get(key)) or 0) + 1
        await store.set(key, str(value), ex=ttl)
        return value
    raise AssertionError("not a briefing section script")
