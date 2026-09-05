"""What a TREATMENT row may carry, and what it must never carry (ADR-263, lot 4).

Two registers, two identities. An ACTION is claimed before it happens and
closed from an explicit result; a TREATMENT is merely OBSERVED — there is
nothing to claim, nothing to replay, nothing to confirm. Modelling it in the
effects table would have meant a synthetic idempotency key for a call that has
none, and a `UNIQUE(thread_id, idempotency_key)` collision the second time one
turn consults the same capability.

The column set is the contract, and it is deliberately narrow: a consultation
records WHICH capability, WHEN, with WHICH outcome — never WHAT was asked.
« Searched Marie's emails » reveals a search nobody asked to have recorded,
where « sent an email to Marie » records an act the user requested.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


class TestTheColumnsAreTheContract:
    def test_the_row_carries_what_a_reader_needs(self) -> None:
        from src.domains.agents.effects.models import AgentTreatment

        columns = set(AgentTreatment.__table__.columns.keys())
        expected = {
            "id",
            "user_id",
            "thread_id",
            "run_id",
            "source",
            "execution_mode",
            "tool_name",
            "mutation_policy",
            "outcome",
            "duration_ms",
            "occurred_at",
            # The notary's marker (ADR-263 lot 5): the ONE column the chain
            # does not digest, because digesting it would make the act of
            # notarising invalidate the digest it just took.
            "notarised_at",
        }
        assert columns == expected, f"unexpected column set: {sorted(columns ^ expected)}"

    @pytest.mark.parametrize(
        "forbidden",
        ["label", "args", "arguments", "args_digest", "query", "result", "result_payload"],
    )
    def test_no_column_can_carry_what_was_asked(self, forbidden: str) -> None:
        """The PII line this register does not cross, stated column by column."""
        from src.domains.agents.effects.models import AgentTreatment

        assert forbidden not in AgentTreatment.__table__.columns

    def test_the_account_owns_its_treatments(self) -> None:
        """Retention: until the account is deleted, like the actions."""
        from src.domains.agents.effects.models import AgentTreatment

        foreign_keys = list(AgentTreatment.__table__.c.user_id.foreign_keys)
        assert len(foreign_keys) == 1
        assert foreign_keys[0].column.table.name == "users"
        assert foreign_keys[0].ondelete == "CASCADE"

    def test_it_is_indexed_for_the_two_questions_it_answers(self) -> None:
        """« this turn » and « my journal », the only two reads there are."""
        from src.domains.agents.effects.models import AgentTreatment

        indexed = {
            tuple(column.name for column in index.columns)
            for index in AgentTreatment.__table__.indexes
        }
        assert ("run_id",) in indexed, "the turn's treatments must be findable by run"
        assert ("user_id", "occurred_at") in indexed, "the journal pages by user and time"

    def test_it_has_no_uniqueness_to_violate(self) -> None:
        """A consultation is not idempotent: two calls are two rows."""
        from src.domains.agents.effects.models import AgentTreatment

        constraints = {type(c).__name__ for c in AgentTreatment.__table__.constraints}
        assert "UniqueConstraint" not in constraints


class TestTheStoredVocabulary:
    def test_the_source_is_stored_as_its_VALUE(self) -> None:
        """The convention the effects table paid for: values, not member names.

        Without ``values_callable`` the column stores ``USER`` while every
        migration and query says ``user`` — and the test schema, built from
        this same metadata, would agree with itself and pass.
        """
        from src.domains.agents.effects.models import AgentTreatment

        enum_type = AgentTreatment.__table__.c.source.type
        assert set(enum_type.enums) == {"user", "scheduled", "subagent"}

    def test_the_outcome_says_only_what_was_observed(self) -> None:
        from src.domains.agents.effects.models import TreatmentOutcome

        assert {member.value for member in TreatmentOutcome} == {"ok", "failed"}


class TestTheTwoRegistersStayApart:
    def test_they_are_two_tables(self) -> None:
        from src.domains.agents.effects.models import AgentEffect, AgentTreatment

        assert AgentTreatment.__tablename__ == "agent_treatments"
        assert AgentEffect.__tablename__ == "agent_effects"

    def test_a_treatment_is_not_an_effect(self) -> None:
        """No shared base row, no discriminator: one forgotten filter would
        make a displayed total lie."""
        from src.domains.agents.effects.models import AgentEffect, AgentTreatment

        assert not issubclass(AgentTreatment, AgentEffect)
        assert "status" not in AgentTreatment.__table__.columns
        assert "claim_token" not in AgentTreatment.__table__.columns
