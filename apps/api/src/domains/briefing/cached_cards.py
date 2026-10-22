"""Assemble cached section reads while preserving absence and source policy."""

import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Protocol

from src.domains.briefing.constants import SECTION_NAMES, SECTION_SMS
from src.domains.briefing.schemas import CardsBundle, CardSection, CardStatus


class CachedSectionReader(Protocol):
    """Read one cached briefing section, with its visibility policy, or None if absent."""

    def __call__(
        self, name: str, *, include_messages: bool = False
    ) -> Awaitable[CardSection | None]: ...


async def published_cards_bundle(read: CachedSectionReader) -> CardsBundle | None:
    """Read live SMS only after every cached section is available.

    Args:
        read: The caller's section reader, including its visibility policy.

    Returns:
        A publishable bundle with fresh SMS, or None while a section is absent.
    """
    bundle, missing = await cached_cards_bundle(read, include_sms=False, sms_previews=False)
    if missing:
        return None
    sms = await read(SECTION_SMS, include_messages=True)
    return bundle.model_copy(update={SECTION_SMS: sms}) if sms is not None else None


async def cached_cards_bundle(
    read: CachedSectionReader, *, include_sms: bool, sms_previews: bool
) -> tuple[CardsBundle, frozenset[str]]:
    """Return the bundle and visible cache gaps; hidden is never a cache gap.

    Missing distinguishes a cold bundle from an uneventful day. Failed sources
    are not cached, so they remain missing and can trigger a coalesced rebuild.
    The caller owns visibility, consultations and each source's cache policy;
    SMS is read live only when explicitly included, with previews opt-in.
    """
    now = datetime.now(UTC)
    names = tuple(name for name in SECTION_NAMES if include_sms or name != SECTION_SMS)
    results = await asyncio.gather(
        *(
            (
                read(name, include_messages=True)
                if name == SECTION_SMS and sms_previews
                else read(name)
            )
            for name in names
        )
    )
    by_name = dict(zip(names, results, strict=True))
    if not include_sms:
        by_name[SECTION_SMS] = CardSection(status=CardStatus.HIDDEN, generated_at=now)
    missing = frozenset(name for name, section in by_name.items() if section is None)
    bundle = CardsBundle(
        **{
            name: by_name[name] or CardSection(status=CardStatus.NOT_CONFIGURED, generated_at=now)
            for name in SECTION_NAMES
        }
    )
    return bundle, missing
