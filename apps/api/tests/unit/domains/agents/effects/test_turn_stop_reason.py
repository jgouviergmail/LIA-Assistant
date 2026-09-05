"""Why a turn stopped short, and who is allowed to say it (ADR-263, lot 8).

This file is family C of the lot-7/8/9 test plan, and writing it found a real
defect: ``react_exit_reason`` returns THREE conditions and the wording table
carried two, so a turn stopped by the tool budget printed ``tool_budget`` at the
person whose turn it was — in five languages out of six, and only to the users
unlucky enough to hit it.

Hence the guard here reads the PREDICATE rather than a list. The stop
conditions live in one function (ADR-248 invariant 2: one predicate, two
readers), so that function is the only honest source for « what can be said ».

The second property is the merge: a resumption that ended normally must CLEAR
the reason its first segment stopped for — the turn no longer stopped short.
That is the opposite of the pointers, which a later segment must never blank,
and the difference is deliberate.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.core.i18n_treatments import (
    assert_stop_reason_wording_completeness,
    render_stop_reason,
)
from src.domains.agents.effects.decision_recorder import decision_recorder
from src.domains.agents.effects.decisions import (
    TurnDecision,
    note_answered,
    note_stop_reason,
)
from src.domains.agents.effects.models import DecisionOutcome

pytestmark = [pytest.mark.unit]

_NO_WRITE = "src.domains.agents.effects.decision_recorder._write_shielded"


def _turn() -> TurnDecision:
    return TurnDecision(run_id=f"run-{uuid.uuid4().hex[:6]}", user_id=uuid.uuid4())


class TestTheReasonIsRecordedBesideTheOutcome:
    async def test_a_budget_exit_says_WHY_and_stays_interrupted(self) -> None:
        """Two columns, two facts. Folding the reason into the outcome would
        make « interrupted » mean four different things."""
        decision = _turn()

        with patch(_NO_WRITE, AsyncMock()):
            async with decision_recorder(decision):
                note_stop_reason("compute_budget")

        assert decision.stop_reason == "compute_budget"
        assert decision.outcome is DecisionOutcome.INTERRUPTED

    async def test_a_turn_that_ran_to_its_end_gives_no_reason(self) -> None:
        decision = _turn()

        with patch(_NO_WRITE, AsyncMock()):
            async with decision_recorder(decision):
                note_answered()

        assert decision.stop_reason is None
        assert decision.outcome is DecisionOutcome.ANSWERED

    async def test_an_absent_reason_never_overwrites_one_already_known(self) -> None:
        """The predicate returns None on every iteration that does NOT stop, and
        it is read on each of them."""
        decision = _turn()

        with patch(_NO_WRITE, AsyncMock()):
            async with decision_recorder(decision):
                note_stop_reason("max_iterations")
                note_stop_reason(None)
                note_stop_reason("")

        assert decision.stop_reason == "max_iterations"

    async def test_noting_outside_a_turn_is_silent(self) -> None:
        """The routing function also runs in tests and probes."""
        note_stop_reason("compute_budget")


class TestEveryConditionThePredicateCanReturnIsREADABLE:
    def test_the_boot_guard_accepts_the_current_predicate(self) -> None:
        assert_stop_reason_wording_completeness()

    def test_the_guard_reads_the_PREDICATE_not_a_list(self) -> None:
        """Anti-vacuity, and the whole point: a condition added to the function
        must fail the build, not print its code at a user."""
        import ast
        import inspect

        from src.domains.agents.utils import react_budget

        tree = ast.parse(inspect.getsource(react_budget.react_exit_reason))
        returned = {
            node.value.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Return)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        }

        assert returned == {"max_iterations", "compute_budget", "tool_budget"}

    def test_the_guard_REFUSES_a_missing_wording(self) -> None:
        from src.core import i18n_treatments

        crippled = {
            language: {k: v for k, v in table.items() if k != "tool_budget"}
            for language, table in i18n_treatments.STOP_REASON_WORDING.items()
        }
        with (
            patch.object(i18n_treatments, "STOP_REASON_WORDING", crippled),
            pytest.raises(AssertionError, match="tool_budget"),
        ):
            i18n_treatments.assert_stop_reason_wording_completeness()

    @pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
    @pytest.mark.parametrize("condition", ["max_iterations", "compute_budget", "tool_budget"])
    def test_every_condition_reads_in_every_language(self, condition: str, language: str) -> None:
        wording = render_stop_reason(condition, language)

        assert wording
        assert wording != condition, "the stored code leaked to a reader"

    def test_an_unknown_condition_is_returned_as_stored(self) -> None:
        """An archive must not fail, and must not print a blank either."""
        assert render_stop_reason("something_new", "fr") == "something_new"


class TestTheArchiveSaysItToo:
    def test_the_rendered_turn_names_the_reason_beside_the_outcome(self) -> None:
        from src.domains.account_export.builder import _render_decisions

        rendered = _render_decisions(
            [
                {
                    "started_at": "2026-09-05T10:00:00Z",
                    "execution_mode": "react",
                    "outcome": "interrupted",
                    "stop_reason": "tool_budget",
                }
            ],
            "fr",
        )

        assert "interrompu" in rendered
        assert render_stop_reason("tool_budget", "fr") in rendered

    def test_a_turn_that_answered_carries_no_parenthesis(self) -> None:
        from src.domains.account_export.builder import _render_decisions

        rendered = _render_decisions(
            [
                {
                    "started_at": "2026-09-05T10:00:00Z",
                    "execution_mode": "pipeline",
                    "outcome": "answered",
                    "stop_reason": None,
                }
            ],
            "fr",
        )

        assert "(" not in rendered.split("\n")[-2]
