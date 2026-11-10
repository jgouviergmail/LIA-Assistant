"""Follow-up suggestions sanitization + metadata enrichment (UXR Lot 4, A2).

The Initiative node's raw LLM output is normalized once (`sanitize_followups`)
before it enters the graph state; the archived-message / done-chunk enrichment
(`with_followup_suggestions`) is branch-free and never mutates its input
(new-dict discipline mirrors the JSONB rule).
"""

import pytest

from src.core.constants import (
    INITIATIVE_FOLLOWUP_MAX_CHARS,
    INITIATIVE_FOLLOWUPS_MAX,
)
from src.core.field_names import FIELD_FOLLOWUP_SUGGESTIONS, FIELD_HABIT_PROPOSAL
from src.domains.agents.services.streaming.followup_metadata import (
    NO_TURN_EXTRAS,
    TurnExtras,
    pop_followups,
    pop_turn_extras,
    push_followups,
    push_motivation,
    push_turn_proposal,
    sanitize_followups,
    with_followup_suggestions,
    with_habit_proposal,
)


class TestSanitizeFollowups:
    def test_strips_whitespace_and_flattens_newlines(self) -> None:
        raw = ["  Montre-moi la météo de demain \n à Paris  "]
        assert sanitize_followups(raw) == ["Montre-moi la météo de demain à Paris"]

    def test_drops_empty_and_whitespace_only_entries(self) -> None:
        assert sanitize_followups(["", "   ", "\n", "Valide"]) == ["Valide"]

    def test_dedupes_case_insensitively_keeping_first(self) -> None:
        raw = ["Ajoute un rappel", "ajoute un RAPPEL", "Autre chose"]
        assert sanitize_followups(raw) == ["Ajoute un rappel", "Autre chose"]

    def test_caps_the_list_at_the_chip_budget(self) -> None:
        raw = [f"Suggestion {i}" for i in range(10)]
        assert len(sanitize_followups(raw)) == INITIATIVE_FOLLOWUPS_MAX

    def test_clamps_each_suggestion_length(self) -> None:
        raw = ["x" * (INITIATIVE_FOLLOWUP_MAX_CHARS + 50)]
        out = sanitize_followups(raw)
        assert len(out[0]) == INITIATIVE_FOLLOWUP_MAX_CHARS

    def test_tolerates_none_and_non_string_entries(self) -> None:
        assert sanitize_followups(None) == []
        assert sanitize_followups([None, 42, "ok"]) == ["ok"]  # type: ignore[list-item]


class TestWithFollowupSuggestions:
    def test_enriches_with_a_new_dict(self) -> None:
        base = {"run_id": "r-1"}
        out = with_followup_suggestions(base, ["Suivant ?"])
        assert out is not base  # new-dict discipline
        assert out[FIELD_FOLLOWUP_SUGGESTIONS] == ["Suivant ?"]
        assert base == {"run_id": "r-1"}  # input untouched

    def test_returns_the_input_unchanged_when_empty(self) -> None:
        base = {"run_id": "r-1"}
        assert with_followup_suggestions(base, []) is base
        assert FIELD_FOLLOWUP_SUGGESTIONS not in base


class TestFollowupHandoff:
    def test_pop_is_once_and_per_run(self) -> None:
        push_followups("run-a", ["Un", "Deux"])
        push_followups("run-b", ["Autre"])

        assert pop_followups("run-a") == ["Un", "Deux"]
        assert pop_followups("run-a") == []  # pop-once
        assert pop_followups("run-b") == ["Autre"]  # runs isolated

    def test_pop_without_push_is_empty(self) -> None:
        assert pop_followups("run-never-pushed") == []

    def test_last_push_wins_for_a_run(self) -> None:
        # Initiative loop iterations: the latest evaluation owns the chips.
        push_followups("run-c", ["Première passe"])
        push_followups("run-c", ["Seconde passe"])
        assert pop_followups("run-c") == ["Seconde passe"]


@pytest.mark.unit
class TestInitiativeMotivation:
    """Provenance line of the initiative (Lot 1-A3): sanitize + handoff +
    metadata enrichment, same pop-once doctrine as the follow-up chips."""

    def test_sanitize_motivation_strips_flattens_and_clamps(self):
        from src.core.constants import INITIATIVE_MOTIVATION_MAX_CHARS
        from src.domains.agents.services.streaming.followup_metadata import (
            sanitize_motivation,
        )

        assert sanitize_motivation("  parce que tu\n suis la F1  ") == ("parce que tu suis la F1")
        assert sanitize_motivation("   ") is None
        assert sanitize_motivation(None) is None
        long = "x" * (INITIATIVE_MOTIVATION_MAX_CHARS + 50)
        clamped = sanitize_motivation(long)
        assert clamped is not None
        assert len(clamped) == INITIATIVE_MOTIVATION_MAX_CHARS

    def test_motivation_handoff_is_pop_once_per_run(self):
        from src.domains.agents.services.streaming.followup_metadata import (
            pop_motivation,
            push_motivation,
        )

        push_motivation("run-a", "parce que tu suis la F1")

        assert pop_motivation("run-a") == "parce que tu suis la F1"
        assert pop_motivation("run-a") is None
        assert pop_motivation("run-never") is None

    def test_metadata_enricher_is_branch_free(self):
        from src.core.field_names import FIELD_INITIATIVE_MOTIVATION
        from src.domains.agents.services.streaming.followup_metadata import (
            with_initiative_motivation,
        )

        base = {"kept": True}
        assert with_initiative_motivation(base, None) is base
        enriched = with_initiative_motivation(base, "parce que")
        assert enriched is not base
        assert enriched[FIELD_INITIATIVE_MOTIVATION] == "parce que"
        assert base == {"kept": True}


@pytest.mark.unit
class TestTurnExtras:
    """Everything a turn hands its stream besides the answer, popped ONCE (ADR-375):
    the chips, the provenance line and the habit proposal card."""

    def test_one_pop_takes_every_extra_of_the_run(self) -> None:
        card = {"id": "p-1", "kind": "automate_need"}
        push_followups("run-x", ["Et demain ?"])
        push_motivation("run-x", "parce que")
        push_turn_proposal("run-x", card)
        push_turn_proposal("run-y", {"id": "p-2"})

        extras = pop_turn_extras("run-x")

        assert extras == TurnExtras(
            followups=("Et demain ?",), motivation="parce que", habit_proposal=card
        )
        assert pop_turn_extras("run-x") == NO_TURN_EXTRAS  # pop-once, every part
        assert pop_turn_extras("run-y").habit_proposal == {"id": "p-2"}  # runs isolated

    def test_a_run_that_pushed_nothing_pops_no_extras(self) -> None:
        assert pop_turn_extras("run-silent") == NO_TURN_EXTRAS

    def test_the_card_enricher_is_branch_free(self) -> None:
        base = {"kept": True}
        assert with_habit_proposal(base, None) is base
        enriched = with_habit_proposal(base, {"id": "p-1"})
        assert enriched is not base
        assert enriched[FIELD_HABIT_PROPOSAL] == {"id": "p-1"}
        assert base == {"kept": True}
