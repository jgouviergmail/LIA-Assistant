"""What a person refuses, and the direction the refusal points in.

The preference stores a REFUSAL set, never an allow-list — ADR-197's doctrine,
applied to a second vocabulary. Three consequences, and each is a decision:

- ``NULL`` means « never expressed », so an account that predates the feature
  behaves exactly as before;
- a kind added in a later lot is ON until someone refuses it, rather than
  invisible until everyone re-opts in;
- and the two directions are asymmetric on purpose. **Reading is forgiving**
  (the column is JSONB and could have been hand-edited; the safe reading of
  anything unexpected is « nothing refused »), **writing is strict** (a value
  the registry does not know is dropped rather than stored, so a renamed kind
  cannot silence itself for ever).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.domains.moments.models import MomentKind
from src.domains.moments.preferences import (
    disabled_kinds_for,
    is_kind_enabled,
    sanitize_disabled_kinds,
    unmet_kind_dependencies,
)

pytestmark = pytest.mark.unit

FOLLOWUP = MomentKind.EVENT_FOLLOWUP.value


def _user(stored: object) -> object:
    return SimpleNamespace(moment_kinds_disabled=stored)


class TestReadingIsForgiving:
    def test_never_expressed_refuses_nothing(self) -> None:
        assert disabled_kinds_for(_user(None)) == frozenset()

    def test_an_empty_list_refuses_nothing(self) -> None:
        assert disabled_kinds_for(_user([])) == frozenset()

    def test_a_refusal_is_read_back(self) -> None:
        assert disabled_kinds_for(_user([FOLLOWUP])) == frozenset({FOLLOWUP})

    def test_a_hand_edited_column_degrades_to_nothing_refused(self) -> None:
        """Silencing a kind by accident is the failure to avoid, not the other
        way round."""
        for junk in ("not a list", 42, {"kind": FOLLOWUP}):
            assert disabled_kinds_for(_user(junk)) == frozenset(), junk

    def test_an_unknown_entry_is_not_a_refusal(self) -> None:
        assert disabled_kinds_for(_user(["ghost_kind", FOLLOWUP])) == frozenset({FOLLOWUP})

    def test_an_account_with_no_column_at_all_refuses_nothing(self) -> None:
        assert disabled_kinds_for(SimpleNamespace()) == frozenset()


class TestWritingIsStrict:
    def test_a_known_kind_is_stored(self) -> None:
        assert sanitize_disabled_kinds([FOLLOWUP]) == [FOLLOWUP]

    def test_an_unknown_kind_is_dropped_rather_than_refused(self) -> None:
        """A renamed vocabulary must not block a save, and must not silence a
        kind nobody named."""
        assert sanitize_disabled_kinds(["ghost_kind"]) == []

    def test_duplicates_collapse(self) -> None:
        assert sanitize_disabled_kinds([FOLLOWUP, FOLLOWUP]) == [FOLLOWUP]

    def test_the_order_is_stable(self) -> None:
        """Two saves of the same choice must produce the same column, or every
        write looks like a change."""
        assert sanitize_disabled_kinds([FOLLOWUP]) == sanitize_disabled_kinds([FOLLOWUP])

    def test_non_strings_are_dropped(self) -> None:
        assert sanitize_disabled_kinds([1, None, FOLLOWUP]) == [FOLLOWUP]  # type: ignore[list-item]


class TestTheGate:
    def test_a_kind_nobody_refused_is_enabled(self) -> None:
        assert is_kind_enabled(_user(None), FOLLOWUP) is True

    def test_a_refused_kind_is_not(self) -> None:
        assert is_kind_enabled(_user([FOLLOWUP]), FOLLOWUP) is False


class TestDependenciesArePublished:
    """ADR-184: what is enforced is published, so the panel can say why."""

    def test_a_kind_whose_requirement_is_met_says_nothing(self) -> None:
        assert unmet_kind_dependencies(available=frozenset({"calendar"})) == {}

    def test_a_kind_with_no_calendar_says_what_it_waits_for(self) -> None:
        assert unmet_kind_dependencies(available=frozenset()) == {FOLLOWUP: ("calendar",)}
