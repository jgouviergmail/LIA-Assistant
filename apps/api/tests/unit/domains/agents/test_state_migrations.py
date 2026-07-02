"""Unit tests for the state schema migration chain (F7).

The migration infrastructure existed since schema 1.0 but was never wired
into checkpoint loading; ``load_or_create_state`` now runs it. These tests
pin the chain's contract: idempotent, purely additive, always converging to
``CURRENT_SCHEMA_VERSION``.
"""

import uuid
from typing import Any, cast

from src.domains.agents.models import (
    CURRENT_SCHEMA_VERSION,
    MessagesState,
    create_initial_state,
    migrate_state_to_current,
    needs_migration,
)


def _legacy_state(version: str | None) -> MessagesState:
    """Minimal checkpoint-like state at an old schema version."""
    state: dict[str, Any] = {"messages": [], "current_turn_id": 3}
    if version is not None:
        state["_schema_version"] = version
    return cast(MessagesState, state)


class TestMigrationChain:
    """0.0 → … → CURRENT_SCHEMA_VERSION, additive and idempotent."""

    def test_fresh_state_needs_no_migration(self):
        state = create_initial_state(uuid.uuid4(), "session", "run")
        assert not needs_migration(state)

    def test_legacy_state_without_version_migrates_to_current(self):
        state = _legacy_state(None)
        assert needs_migration(state)

        migrated = migrate_state_to_current(state)

        assert migrated["_schema_version"] == CURRENT_SCHEMA_VERSION

    def test_1_2_to_1_3_adds_replay_safe_hitl_keys(self):
        state = _legacy_state("1.2")

        migrated = cast(dict[str, Any], migrate_state_to_current(state))

        assert migrated["_schema_version"] == CURRENT_SCHEMA_VERSION
        assert migrated["for_each_hitl_ctx"] is None
        assert migrated["for_each_cancelled"] is False
        assert migrated["cancellation_reason"] is None
        assert migrated["draft_edit_iteration"] == 0
        assert migrated["draft_clarification_question"] is None
        assert migrated["user_display_name"] is None

    def test_migration_preserves_existing_values(self):
        state = cast(dict[str, Any], _legacy_state("1.2"))
        state["user_display_name"] = "Jérôme"
        state["draft_edit_iteration"] = 2

        migrated = cast(dict[str, Any], migrate_state_to_current(cast(MessagesState, state)))

        assert migrated["user_display_name"] == "Jérôme"
        assert migrated["draft_edit_iteration"] == 2

    def test_migration_is_idempotent(self):
        state = _legacy_state("1.1")

        once = migrate_state_to_current(state)
        twice = migrate_state_to_current(once)

        assert twice == once
        assert not needs_migration(twice)

    def test_current_version_state_untouched(self):
        state = _legacy_state(CURRENT_SCHEMA_VERSION)
        before = dict(cast(dict[str, Any], state))

        migrated = cast(dict[str, Any], migrate_state_to_current(state))

        assert migrated == before
