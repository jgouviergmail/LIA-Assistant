"""The shape of a moment, and the three constraints that make it safe.

A moment row is a durable claim on a future instant, so its table carries the
three properties every such table in this repository carries:

- **an identity that cannot be created twice** — the detector runs every five
  minutes over the same calendar window, so without a unique key it would file
  the same event again at every pass;
- **a cheap way to find what is due** — a partial index on the pending rows
  only, because that is the only set the sweep ever scans;
- **a vocabulary in Python, a string in the column.** ``workboard_tickets`` and
  ``open_loops`` both store their status as ``String`` with a Python enum for
  the vocabulary, and the reason is measured (ADR-276): a bare enum member as
  the RESULT of a SQL expression binds as ``NullType`` and writes the VALUE
  where the column stores the NAME. A String column cannot fall into it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB

from src.domains.moments.models import (
    MomentKind,
    MomentSkipReason,
    MomentState,
    ProactiveMoment,
)

pytestmark = pytest.mark.unit


class TestTheVocabulary:
    def test_the_only_kind_shipped_is_the_event_follow_up(self) -> None:
        """Lot 1 ships one kind; the registry is what makes lot 4 additive."""
        assert MomentKind.EVENT_FOLLOWUP.value == "event_followup"

    def test_every_state_a_row_can_reach_is_named(self) -> None:
        assert {state.value for state in MomentState} == {
            "pending",
            "claimed",
            "served",
            "skipped",
            "expired",
            "cancelled",
        }

    def test_a_skip_says_why_on_a_bounded_vocabulary(self) -> None:
        """A free-text reason cannot be counted, and a counter is what an
        operator reads to know whether the feature is working."""
        assert {reason.value for reason in MomentSkipReason} == {
            "not_eligible",
            "llm_skip",
            "quota",
            "cancelled",
            "revalidation_failed",
            "dispatch_failed",
        }


class TestTheTable:
    def test_it_is_named_for_what_it_holds(self) -> None:
        assert ProactiveMoment.__tablename__ == "proactive_moments"

    def test_the_identity_cannot_be_filed_twice(self) -> None:
        """The detector re-reads the same window every pass."""
        unique = [
            constraint
            for constraint in ProactiveMoment.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        ]
        assert len(unique) == 1
        assert [column.name for column in unique[0].columns] == [
            "user_id",
            "kind",
            "source_ref",
        ]

    def test_the_due_index_covers_pending_rows_only(self) -> None:
        """The sweep never scans anything else, and settled rows outnumber
        pending ones by orders of magnitude within a day."""
        indexes = {index.name: index for index in ProactiveMoment.__table__.indexes}
        due_index = indexes["ix_proactive_moments_due_pending"]
        assert [column.name for column in due_index.columns] == ["due_at"]
        assert "pending" in str(due_index.dialect_options["postgresql"]["where"])

    def test_a_deleted_account_takes_its_moments_with_it(self) -> None:
        foreign_key = next(iter(ProactiveMoment.__table__.c.user_id.foreign_keys))
        assert foreign_key.ondelete == "CASCADE"

    def test_the_kind_and_state_are_strings_not_native_enums(self) -> None:
        """See the module docstring: the NullType trap ADR-276 measured."""
        assert isinstance(ProactiveMoment.__table__.c.kind.type, String)
        assert isinstance(ProactiveMoment.__table__.c.state.type, String)

    def test_the_payload_is_jsonb_and_never_null(self) -> None:
        payload = ProactiveMoment.__table__.c.payload
        assert isinstance(payload.type, JSONB)
        assert payload.nullable is False

    def test_the_two_instants_are_timezone_aware(self) -> None:
        """A naive instant compared against ``datetime.now(UTC)`` raises."""
        for name in ("due_at", "not_after"):
            column = ProactiveMoment.__table__.c[name]
            assert column.type.timezone is True, name
            assert column.nullable is False, name

    def test_what_a_pending_row_has_not_got_yet_is_nullable(self) -> None:
        for name in ("claim_owner", "claimed_at", "settled_at", "skip_reason"):
            assert ProactiveMoment.__table__.c[name].nullable is True, name


class TestTheStatePartition:
    """Every state belongs to exactly one half, and the boot checks it.

    The two tuples are how the module knows which rows still move and which are
    only waiting to be deleted. A terminal state missing from ``SETTLED_STATES``
    is invisible to the purge and accumulates for ever — which is precisely the
    leak a claimed row already caused once, measured on a real server. A live
    state missing from ``LIVE_STATES`` is the same defect the other way round:
    nothing would move it on.

    Checked at import, like every other completeness rule here (ADR-085).
    """

    def test_the_shipped_tuples_partition_the_enum(self) -> None:
        from src.domains.moments.repository import (
            LIVE_STATES,
            SETTLED_STATES,
            assert_state_partition_complete,
        )

        assert_state_partition_complete()
        assert set(LIVE_STATES) | set(SETTLED_STATES) == {s.value for s in MomentState}
        assert not set(LIVE_STATES) & set(SETTLED_STATES)

    def test_a_state_in_neither_half_refuses_to_boot(self) -> None:
        from unittest.mock import patch

        from src.domains.moments import repository

        with (
            patch.object(repository, "SETTLED_STATES", (MomentState.SERVED.value,)),
            pytest.raises(RuntimeError, match="unclassified"),
        ):
            repository.assert_state_partition_complete()

    def test_a_state_in_both_halves_refuses_to_boot(self) -> None:
        from unittest.mock import patch

        from src.domains.moments import repository

        both = (*repository.SETTLED_STATES, MomentState.PENDING.value)
        with (
            patch.object(repository, "SETTLED_STATES", both),
            pytest.raises(RuntimeError, match="both halves"),
        ):
            repository.assert_state_partition_complete()

    def test_a_value_that_is_not_a_state_refuses_to_boot(self) -> None:
        from unittest.mock import patch

        from src.domains.moments import repository

        with (
            patch.object(repository, "LIVE_STATES", (*repository.LIVE_STATES, "invented")),
            pytest.raises(RuntimeError, match="not a state"),
        ):
            repository.assert_state_partition_complete()
