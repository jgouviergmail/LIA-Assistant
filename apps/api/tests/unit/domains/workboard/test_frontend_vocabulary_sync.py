"""The board's columns are ORDERED, and the two languages must order them alike.

The frontend paints the columns left to right from its own tuple: TypeScript
cannot import a Python enum, so the list exists twice by construction. Twice is
where a drift lives — and a drift here is not cosmetic, it puts « terminé »
before « en cours » on the board while every backend read keeps the old order,
so the two surfaces disagree about what « the next column » is.

The backend enum is the authority (``STATUS_ORDER`` derives from it); this test
holds the frontend copy to it, ORDER INCLUDED, and does the same for the four
priorities and the closed set. It reads the TypeScript source rather than a
generated artefact: a generator would be a third place to keep in step.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.domains.workboard.constants import CLOSED_STATUSES, STATUS_ORDER, TicketPriority
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit


def _vocabulary_source() -> str:
    """The frontend module that declares the two ordered tuples."""
    root = repo_root_or_skip()
    path = Path(root) / "apps" / "web" / "src" / "types" / "workboard.ts"
    if not path.exists():  # pragma: no cover - the frontend tree is absent
        pytest.skip("apps/web is not checked out beside apps/api")
    return path.read_text(encoding="utf-8")


def _tuple_values(source: str, name: str) -> list[str]:
    """Read one ``export const NAME = [...] as const`` list, in order.

    Args:
        source: The TypeScript module's text.
        name: The exported constant's name.

    Returns:
        The quoted values, in declaration order.
    """
    match = re.search(rf"export const {name} = \[(.*?)\] as const", source, re.S)
    assert match, f"{name} is not declared as an `as const` tuple"
    return re.findall(r"'([a-z_]+)'", match.group(1))


class TestTheColumnsAreOrderedTheSameWayOnBothSides:
    def test_the_columns_match_the_enum_order(self) -> None:
        """The board paints them in this order; the backend filters in that one."""
        assert _tuple_values(_vocabulary_source(), "TICKET_STATUSES") == list(STATUS_ORDER)

    def test_the_four_priorities_match_the_enum(self) -> None:
        """Weakest first on both sides: the sort and the badge scale read it."""
        assert _tuple_values(_vocabulary_source(), "TICKET_PRIORITIES") == [
            priority.value for priority in TicketPriority
        ]

    def test_the_closed_set_is_the_same_two_columns(self) -> None:
        """« Hide closed older than N days » must hide the same two columns the
        retention sweep considers closed."""
        source = _vocabulary_source()
        match = re.search(
            r"export const CLOSED_STATUSES: readonly TicketStatus\[\] = \[(.*?)\];", source, re.S
        )
        assert match, "CLOSED_STATUSES is not declared as a readonly list"
        assert set(re.findall(r"'([a-z_]+)'", match.group(1))) == set(CLOSED_STATUSES)
