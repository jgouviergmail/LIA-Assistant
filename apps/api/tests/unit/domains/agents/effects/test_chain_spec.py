"""What the chain covers, column by column (ADR-263, lot 5).

An allowlist that forgets a column leaves a place where a value can be edited
without the chain noticing — which is precisely what the chain exists to make
impossible. So the rule is the opposite of a denylist: **every column of every
covered model is either digested, or excluded on purpose with a reason**, and a
column added tomorrow fails the build until someone decides which it is.

The exclusions are deliberately reduced to the minimum that is logically
necessary: the two bookkeeping columns the NOTARY ITSELF writes. Any other
exception would be a hole someone has to remember.
"""

from __future__ import annotations

import pytest

from src.domains.agents.effects.chain_spec import (
    CHAIN_SUBJECTS,
    NOT_DIGESTED,
    subjects_for,
)

pytestmark = [pytest.mark.unit]


def _model(name: str) -> object:
    from src.domains.agents.effects import models

    return getattr(models, name)


class TestEveryColumnIsClassified:
    @pytest.mark.parametrize("model_name", ["AgentEffect", "AgentTreatment"])
    def test_no_column_is_neither_digested_nor_excluded(self, model_name: str) -> None:
        model = _model(model_name)
        columns = set(model.__table__.columns.keys())  # type: ignore[attr-defined]
        digested = {column for subject in subjects_for(model_name) for column in subject.columns}
        unclassified = sorted(columns - digested - NOT_DIGESTED)

        assert not unclassified, (
            f"{model_name}: {unclassified} are neither digested nor excluded. "
            "Decide: add them to a subject's columns, or to NOT_DIGESTED with "
            "the reason — a forgotten column is a place the chain cannot see."
        )

    @pytest.mark.parametrize("model_name", ["AgentEffect", "AgentTreatment"])
    def test_no_subject_digests_a_column_the_model_lacks(self, model_name: str) -> None:
        model = _model(model_name)
        columns = set(model.__table__.columns.keys())  # type: ignore[attr-defined]
        for subject in subjects_for(model_name):
            missing = sorted(set(subject.columns) - columns)
            assert not missing, f"{subject.kind}: {missing} do not exist on the model"


class TestTheExclusionsAreTheMinimum:
    def test_only_the_notary_s_own_bookkeeping_is_excluded(self) -> None:
        """Every other exception would be a hole someone has to remember."""
        assert NOT_DIGESTED == {"notarised_at", "settled_notarised_at"}

    def test_the_excluded_columns_exist_on_a_model(self) -> None:
        """A stale exclusion advertises a protection that protects nothing."""
        columns: set[str] = set()
        for name in ("AgentEffect", "AgentTreatment"):
            columns |= set(_model(name).__table__.columns.keys())  # type: ignore[attr-defined]

        assert NOT_DIGESTED <= columns


class TestTheTwoStages:
    def test_an_effect_is_covered_in_two_stages(self) -> None:
        kinds = [subject.kind for subject in subjects_for("AgentEffect")]

        assert kinds == ["effect.claimed", "effect.settled"]

    def test_the_claimed_stage_covers_only_IMMUTABLE_columns(self) -> None:
        """A column that changes at close would make a legitimate close look
        like tampering — the false positive this split exists to prevent."""
        claimed = next(s for s in subjects_for("AgentEffect") if s.kind == "effect.claimed")
        mutated_at_close = {
            "status",
            "closed_at",
            "provider_ref",
            "result_payload",
            "result_digest",
            "result_truncated",
            "error_code",
            "retry_of",
        }

        assert not set(claimed.columns) & mutated_at_close

    def test_the_settled_stage_covers_exactly_the_outcome(self) -> None:
        settled = next(s for s in subjects_for("AgentEffect") if s.kind == "effect.settled")

        assert set(settled.columns) == {
            "status",
            "closed_at",
            "provider_ref",
            "result_payload",
            "result_digest",
            "result_truncated",
            "error_code",
            "retry_of",
        }

    def test_a_consultation_is_covered_in_one_stage(self) -> None:
        """It is never mutated, so a second stage would cover nothing."""
        subjects = subjects_for("AgentTreatment")

        assert [s.kind for s in subjects] == ["treatment.recorded"]

    def test_a_consultation_digests_all_of_itself(self) -> None:
        model = _model("AgentTreatment")
        columns = set(model.__table__.columns.keys())  # type: ignore[attr-defined]
        subject = subjects_for("AgentTreatment")[0]

        assert set(subject.columns) == columns - NOT_DIGESTED


class TestTheKindsAreDistinctAndStable:
    def test_every_kind_is_unique(self) -> None:
        kinds = [subject.kind for subject in CHAIN_SUBJECTS]

        assert len(kinds) == len(set(kinds))

    def test_a_kind_names_its_stage_explicitly(self) -> None:
        """The kind is written into every entry's hash: renaming one would
        invalidate the chains that carry it."""
        for subject in CHAIN_SUBJECTS:
            assert "." in subject.kind, f"{subject.kind} is not a <subject>.<stage> name"
