"""Unit tests for the OpenLoop model (P5, interdomain program Lot 2).

Column-level semantics (defaults, enums, indexes) — the atomic status
transitions are covered by the integration suite against real PostgreSQL.
"""

import pytest

from src.domains.open_loops.models import (
    OpenLoop,
    OpenLoopDirection,
    OpenLoopSourceKind,
    OpenLoopStatus,
)


@pytest.mark.unit
class TestOpenLoopEnums:
    """Enum values are the persisted contract — pin them."""

    def test_direction_values(self):
        assert OpenLoopDirection.USER_OWES.value == "user_owes"
        assert OpenLoopDirection.WAITING_ON_OTHER.value == "waiting_on_other"

    def test_status_values(self):
        assert OpenLoopStatus.OPEN.value == "open"
        assert OpenLoopStatus.CLOSED.value == "closed"
        assert OpenLoopStatus.EXPIRED.value == "expired"

    def test_source_kind_values(self):
        assert OpenLoopSourceKind.CONVERSATION.value == "conversation"


@pytest.mark.unit
class TestOpenLoopModel:
    """Model shape: table name, defaults, nullability."""

    def test_tablename(self):
        assert OpenLoop.__tablename__ == "open_loops"

    def test_status_column_defaults_to_open(self):
        assert OpenLoop.status.default.arg == OpenLoopStatus.OPEN.value

    def test_nudge_count_defaults_to_zero(self):
        assert OpenLoop.nudge_count.default.arg == 0

    def test_nullable_contract(self):
        assert OpenLoop.subject.nullable is False
        assert OpenLoop.direction.nullable is False
        assert OpenLoop.counterparty.nullable is True
        assert OpenLoop.due_hint.nullable is True
        assert OpenLoop.source_ref.nullable is True
        assert OpenLoop.closed_reason.nullable is True
        assert OpenLoop.last_nudged_at.nullable is True

    def test_user_fk_cascade(self):
        fk = next(iter(OpenLoop.user_id.foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_open_partial_index_exists(self):
        index_names = {idx.name for idx in OpenLoop.__table__.indexes}
        assert "ix_open_loops_user_open" in index_names
