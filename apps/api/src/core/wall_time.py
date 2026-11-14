"""A time on a wall, and the zone it is read in (ADR-380).

Three things are called « a time », and they are not the same thing:

- an INSTANT, a point everyone shares: an aware ``datetime``;
- a WALL TIME, what a clock shows somewhere — « half past nine in Paris ». It is
  what a person says and reads, and it names an instant only WITH its zone;
- a DAY, which is no time at all.

A bare ``datetime`` cannot say which of the first two it is, a string even less,
and every hour this codebase lost was a wall time taken for an instant on the
way: a ``Z`` appended by a « normalisation », a zone stamped on the wrong value.
:class:`WallTime` holds the pair so that it can no longer be split. Whatever
writes a person's time to a provider is given one (the calendars:
``connectors/clients/event_bounds``), and nothing between the person and the
provider converts it — the provider is told the wall time AND the zone.

One rule for the two nights the clocks change, the one Python's ``zoneinfo`` and
RFC 5545 share: an hour the clocks skip is read with the offset before the
change, an hour they show twice is its first passage. An instant seen on a wall
(:meth:`WallTime.seen_from`) keeps which passage it was. On those two nights
the zone alone does not place a time for every reader
(:attr:`WallTime.zone_suffices`): a provider is then told the INSTANT.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from zoneinfo import ZoneInfo

#: A day and a time to the minute at least, with or without an offset (to the
#: second: old zones had such offsets, and ``isoformat`` writes them). Nothing
#: else is read: a day alone is no time, and a loose spelling is not guessed.
_DAY_AND_TIME: Final = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?(?:Z|[+-]\d{2}:\d{2}(?::\d{2})?)?"
)


@dataclass(frozen=True, slots=True)
class WallTime:
    """What a clock on a wall shows, and the zone that wall is in.

    Two of them are equal when they SHOW the same thing in the same zone, as two
    ``datetime`` are: the two passages of a repeated hour compare equal. Compare
    :meth:`instant` where the passage matters.

    Attributes:
        local: The day and time on the wall, WITHOUT an offset (its ``fold``
            says which passage of a repeated hour it is).
        zone: The IANA zone the wall is in.
    """

    local: datetime
    zone: ZoneInfo

    def __post_init__(self) -> None:
        """Refuse a value that carries an offset: the zone alone says where it is read."""
        if self.local.tzinfo is not None:
            raise ValueError("a wall time carries no offset of its own: its zone places it")

    @classmethod
    def read(cls, written: str, zone: ZoneInfo) -> WallTime:
        """Read a day and a time as someone in ``zone`` means them.

        Written WITHOUT an offset, they are the time on that zone's wall. Written
        WITH one (or ``Z``), they name an instant, and the wall time is what the
        zone's wall shows at that instant.

        Args:
            written: ``YYYY-MM-DDTHH:MM[:SS]``, with or without an offset.
            zone: The zone of the person who wrote it.

        Returns:
            The wall time.

        Raises:
            ValueError: Anything else — a day alone, a loose spelling, an
                impossible date. A value that cannot be read is never guessed.
        """
        if not _DAY_AND_TIME.fullmatch(written):
            raise ValueError("a wall time is YYYY-MM-DDTHH:MM[:SS], with or without an offset")
        moment = datetime.fromisoformat(written)
        if moment.tzinfo is None:
            return cls(moment, zone)
        return cls.seen_from(moment, zone)

    @classmethod
    def seen_from(cls, instant: datetime, zone: ZoneInfo) -> WallTime:
        """What ``zone``'s wall shows at an instant.

        Args:
            instant: An aware ``datetime``.
            zone: The zone whose wall is read.

        Returns:
            The wall time, keeping which passage of a repeated hour it is.

        Raises:
            ValueError: ``instant`` carries no offset: it is no instant.
        """
        if instant.tzinfo is None:
            raise ValueError("an instant carries its offset: a naive value is a wall time")
        return cls(instant.astimezone(zone).replace(tzinfo=None), zone)

    @property
    def zone_suffices(self) -> bool:
        """Whether the zone alone places this time for every reader.

        False in an hour the zone's clocks skip or show twice: told « 02:30 in
        Paris » on such a night, a provider places it by a rule of its own, maybe
        an hour from ours. Whoever writes it there says the INSTANT instead.
        """
        zoned = self.in_its_zone()
        return zoned.replace(fold=0).utcoffset() == zoned.replace(fold=1).utcoffset()

    def in_its_zone(self) -> datetime:
        """The wall time with its zone attached, for a format that carries both (iCalendar)."""
        return self.local.replace(tzinfo=self.zone)

    def instant(self) -> datetime:
        """The instant this wall time is, in UTC."""
        return self.in_its_zone().astimezone(UTC)

    def iso(self) -> str:
        """The day and time on the wall, to the second and WITHOUT an offset.

        What a provider is given beside the zone's name: an offset here would
        be read before the zone and decide the instant in its place.
        """
        return self.local.isoformat(timespec="seconds")


__all__ = ["WallTime"]
