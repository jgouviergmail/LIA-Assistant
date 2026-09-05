"""One reading of "over this period", for both registers (ADR-263, lot 4).

Six read paths take a period — the two journals, the two readable exports, the
administrator's readable extraction and the technical one — and every one of
them must apply it identically to the PAGE and to the COUNT. A second spelling
of the same window is how a total ends up describing a set the reader cannot
see (ADR-185, measured on the CRM).

Bounds are half-open, ``[since, until)``: a day filter built from midnight to
midnight then covers exactly one day, with no row counted twice by two adjacent
exports and none falling between them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def period_conditions(column: Any, since: datetime | None, until: datetime | None) -> list[Any]:
    """The WHERE clauses for a period, in one place.

    Args:
        column: The timestamp column the register is dated by — the claim for
            an action, the return for a consultation.
        since: Inclusive lower bound, or None for "since the beginning".
        until: EXCLUSIVE upper bound, or None for "up to now".

    Returns:
        Zero, one or two conditions, to be spread into both the page query and
        the count query.
    """
    conditions: list[Any] = []
    if since is not None:
        conditions.append(column >= since)
    if until is not None:
        conditions.append(column < until)
    return conditions
