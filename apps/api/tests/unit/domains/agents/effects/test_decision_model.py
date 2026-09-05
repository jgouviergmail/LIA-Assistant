"""What one TURN may carry, and what it must never (ADR-263, lot 6).

The decision register is the spine the other two hang off: `agent_effects` says
what was DONE, `agent_treatments` what was READ, and both carry a `run_id` that
until now pointed at nothing. This row is what that identifier means.

Two properties are enforced by the shape rather than by code that could forget:
it **points** at the request and the answer instead of copying them, and it is
**one row per turn** — a HITL resumption reuses the identifier, so the write is
an upsert and `segments` says how many times the turn ran. Overwriting in
silence would make an interrupted turn indistinguishable from a straight one,
which is precisely the fact an audit wants.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


class TestTheColumnsAreTheContract:
    def test_the_row_carries_what_a_reader_needs(self) -> None:
        from src.domains.agents.effects.models import AgentDecision

        assert set(AgentDecision.__table__.columns.keys()) == {
            "id",
            "user_id",
            "thread_id",
            "run_id",
            "source",
            "execution_mode",
            "route",
            "plan_step_count",
            "request_message_id",
            "response_message_id",
            "outcome",
            "stop_reason",
            "segments",
            "started_at",
            "ended_at",
            "duration_ms",
            "schema_version",
        }

    @pytest.mark.parametrize(
        "forbidden",
        [
            "content",
            "prompt",
            "request",
            "response",
            "answer",
            "plan",
            "label",
            "args",
            "result_payload",
        ],
    )
    def test_no_column_can_carry_CONTENT(self, forbidden: str) -> None:
        """It points at the words; it never becomes a second copy of them —
        and therefore never a second place to leak them."""
        from src.domains.agents.effects.models import AgentDecision

        assert forbidden not in AgentDecision.__table__.columns


class TestItPointsAndNeverCopies:
    @pytest.mark.parametrize("column", ["request_message_id", "response_message_id"])
    def test_a_deleted_conversation_leaves_a_TOMBSTONE(self, column: str) -> None:
        """`SET NULL`, never `CASCADE`: the turn happened, and deleting the
        conversation must remove its text without erasing the fact."""
        from src.domains.agents.effects.models import AgentDecision

        keys = list(AgentDecision.__table__.c[column].foreign_keys)

        assert len(keys) == 1
        assert keys[0].column.table.name == "conversation_messages"
        assert keys[0].ondelete == "SET NULL"

    @pytest.mark.parametrize("column", ["request_message_id", "response_message_id"])
    def test_a_pointer_may_be_absent(self, column: str) -> None:
        """A scheduled turn has no request message, and a failed one no answer."""
        from src.domains.agents.effects.models import AgentDecision

        assert AgentDecision.__table__.c[column].nullable

    def test_the_turn_belongs_to_the_account_and_dies_with_it(self) -> None:
        from src.domains.agents.effects.models import AgentDecision

        keys = list(AgentDecision.__table__.c.user_id.foreign_keys)

        assert keys[0].column.table.name == "users"
        assert keys[0].ondelete == "CASCADE"


class TestOneRowPerTurn:
    def test_a_turn_cannot_be_recorded_twice(self) -> None:
        from src.domains.agents.effects.models import AgentDecision

        uniques = {
            tuple(sorted(column.name for column in constraint.columns))
            for constraint in AgentDecision.__table__.constraints
            if type(constraint).__name__ == "UniqueConstraint"
        }

        assert ("run_id",) in uniques

    def test_a_resumed_turn_is_COUNTED_rather_than_overwritten(self) -> None:
        """Without this column an interrupted turn and a straight one look
        identical once resumed — and the interruption is the interesting half."""
        from src.domains.agents.effects.models import AgentDecision

        column = AgentDecision.__table__.c.segments

        assert not column.nullable
        assert column.server_default is not None, "an existing row must not read as zero"


class TestItIsIndexedForTheReadsItServes:
    def test_one_account_s_turns_newest_first(self) -> None:
        from src.domains.agents.effects.models import AgentDecision

        indexed = {
            tuple(column.name for column in index.columns)
            for index in AgentDecision.__table__.indexes
        }

        assert ("user_id", "started_at") in indexed

    def test_the_turns_of_one_conversation(self) -> None:
        from src.domains.agents.effects.models import AgentDecision

        indexed = {
            tuple(column.name for column in index.columns)
            for index in AgentDecision.__table__.indexes
        }

        assert ("thread_id",) in indexed


class TestTheOutcomeVocabularyIsHONEST:
    def test_a_turn_that_never_answered_has_a_value_of_its_own(self) -> None:
        """A register holding only the turns that went well is the shape of an
        account nobody should trust."""
        from src.domains.agents.effects.models import DecisionOutcome

        assert {member.value for member in DecisionOutcome} == {
            "answered",
            "failed",
            "interrupted",
        }


class TestEveryOutcomeCanBeREAD:
    def test_the_boot_guard_accepts_the_current_vocabulary(self) -> None:
        from src.core.i18n_treatments import assert_decision_wording_completeness

        assert_decision_wording_completeness()

    def test_the_boot_guard_REFUSES_a_missing_wording(self) -> None:
        """Anti-vacuity: a guard that cannot fail is a promise nobody checks."""
        from unittest.mock import patch

        from src.core import i18n_treatments

        crippled = {
            language: {key: value for key, value in table.items() if key != "interrupted"}
            for language, table in i18n_treatments.DECISION_OUTCOME_WORDING.items()
        }
        with (
            patch.object(i18n_treatments, "DECISION_OUTCOME_WORDING", crippled),
            pytest.raises(AssertionError, match="interrupted"),
        ):
            i18n_treatments.assert_decision_wording_completeness()

    @pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
    def test_every_outcome_reads_in_every_language(self, language: str) -> None:
        from src.core.i18n_treatments import render_decision_outcome
        from src.domains.agents.effects.models import DecisionOutcome

        for member in DecisionOutcome:
            wording = render_decision_outcome(member.value, language)

            assert wording, f"{member.value} has no wording in {language}"
            if language != "en":
                assert wording != member.value, "the stored code leaked to a reader"

    def test_an_UNKNOWN_outcome_is_returned_as_stored_rather_than_blanked(self) -> None:
        """An archive must not fail, and must not print a blank either."""
        from src.core.i18n_treatments import render_decision_outcome

        assert render_decision_outcome("something_new", "fr") == "something_new"
