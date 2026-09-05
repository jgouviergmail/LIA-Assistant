"""The ledger row: claimed before the effect, closed from a result (ADR-263).

Every property asserted here is one the repository relies on, so a schema edit
that breaks an invariant fails in CI rather than in production:

- ``(thread_id, idempotency_key)`` unique — the same approval cannot be spent
  twice (measured: a confirmed draft executed twice);
- a ``claim_token`` on every row — a stale worker cannot close what it does not
  own (Systemic Rules → Persistence: fencing);
- no JSONB anywhere — nothing can be mutated in place (the recurring SQLAlchemy
  silent-skip defect);
- the two payload columns are opaque TEXT, encrypted by the repository;
- the row says which schema shape it was written in, and whether its payload
  was cut.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB

from src.core.constants import AGENT_EFFECT_SCHEMA_VERSION
from src.domains.agents.effects.models import AgentEffect, EffectSource, EffectStatus

pytestmark = [pytest.mark.unit]


class TestTheVocabulary:
    def test_status_vocabulary(self) -> None:
        assert {s.value for s in EffectStatus} == {
            "claimed",
            "succeeded",
            "failed",
            "abandoned",
            "refused",
        }

    def test_source_vocabulary_is_only_what_exists(self) -> None:
        """Three values: the heartbeat runs no tool, a peer never mutates for another."""
        assert {s.value for s in EffectSource} == {"user", "scheduled", "subagent"}


class TestTheInvariantsTheRepositoryRelies_On:
    def test_one_claim_per_key_per_thread(self) -> None:
        names = {c.name for c in AgentEffect.__table__.constraints}
        assert "uq_agent_effects_thread_idempotency" in names

    def test_every_row_carries_an_owner_token(self) -> None:
        assert AgentEffect.__table__.c.claim_token.nullable is False

    def test_no_jsonb_column_can_be_mutated_in_place(self) -> None:
        assert not [c.name for c in AgentEffect.__table__.columns if isinstance(c.type, JSONB)]

    def test_the_two_payloads_are_opaque_text(self) -> None:
        for column_name in ("result_payload", "label"):
            column = AgentEffect.__table__.c[column_name]
            assert isinstance(column.type, Text)
            assert column.nullable is True
            assert "encrypt" in (column.comment or "").lower(), column_name

    def test_the_label_is_a_key_and_values_not_a_frozen_sentence(self) -> None:
        """It is rendered in the reader's language at export time, not at write time."""
        assert "i18n_key" in (AgentEffect.__table__.c.label.comment or "")

    def test_rows_say_which_shape_they_were_written_in(self) -> None:
        assert AGENT_EFFECT_SCHEMA_VERSION == 1
        assert AgentEffect.__table__.c.schema_version.nullable is False
        assert AgentEffect.__table__.c.result_truncated.nullable is False

    def test_the_ledger_dies_with_the_account(self) -> None:
        """Owner decision: retention until the account is deleted, then nothing."""
        user_fk = next(iter(AgentEffect.__table__.c.user_id.foreign_keys))
        assert user_fk.column.table.name == "users"
        assert user_fk.ondelete == "CASCADE"

    def test_a_retry_points_at_what_it_retries(self) -> None:
        retry_fk = next(iter(AgentEffect.__table__.c.retry_of.foreign_keys))
        assert retry_fk.column.table.name == "agent_effects"
        assert retry_fk.ondelete == "SET NULL"

    def test_the_timestamps_are_timezone_aware(self) -> None:
        for column_name in ("claimed_at", "closed_at"):
            assert AgentEffect.__table__.c[column_name].type.timezone is True


class TestTheModelAndTheMigrationAgree:
    """A disagreement here only shows in production (measured 2026-09-04).

    The integration schema is built from this metadata, so a model that stores
    member NAMES would agree with itself and pass, while the migration's CHECK
    constraint — written with the VALUES — would reject every insert on a real
    deployment.
    """

    @pytest.mark.parametrize(
        ("column", "expected"),
        [
            ("source", {"user", "scheduled", "subagent"}),
            ("status", {"claimed", "succeeded", "failed", "abandoned", "refused"}),
        ],
    )
    def test_enums_are_stored_as_values_not_names(self, column: str, expected: set[str]) -> None:
        stored = set(AgentEffect.__table__.c[column].type.enums)
        assert stored == expected, f"{column} stores {stored}, the migration declares {expected}"


class TestTheLedgerLifecycleIsDeclared:
    """The retention decision, wired into the machinery that already exists.

    Owner decision (2026-09-03): the ledger is kept until the account is
    deleted, and it leaves with the user's archive — it is their own record of
    what the assistant did on their behalf.
    """

    def test_the_table_is_classified_for_purge_and_export(self) -> None:
        from src.domains.users.user_data_map import (
            TABLE_RULES,
            ExportPolicy,
            TableDataClass,
        )

        rule = TABLE_RULES["agent_effects"]
        assert rule.data_class is TableDataClass.USER_PURGED
        assert rule.export is ExportPolicy.FULL
        assert "ADR-263" in rule.reason

    def test_the_purge_actually_deletes_it(self) -> None:
        """A cascade never fires here: account deletion SCRUBS the user row."""
        import uuid

        from src.domains.users.account_deletion_service import build_purge_statements

        purged = {key for key, _ in build_purge_statements(uuid.uuid4())}
        assert "agent_effects" in purged

    def test_the_two_encrypted_columns_leave_the_archive_readable(self) -> None:
        """Portability means readable data (same rule as the meeting transcript)."""
        from src.domains.account_export.builder import _DECRYPTED_COLUMNS

        assert _DECRYPTED_COLUMNS["agent_effects"] == frozenset({"label", "result_payload"})
