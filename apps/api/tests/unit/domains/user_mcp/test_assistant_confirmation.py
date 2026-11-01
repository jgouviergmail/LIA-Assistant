"""From the chat, LIA asks more before an MCP tool, never less (spec 2026-10-30 D7).

The assistant's writes are judged by the computation that alerts the person on the
settings page (``questions_lost``) — one oracle — and any confirmation value but
« always » is refused outright. These tests pin the judge on the real synthesis: a
tightening passes, a value that loosens is refused, a change of who drives a server
passes now that a question before a dedicated agent's task counts as asked (owner
decision 2026-10-31), and whatever the oracle reports as lost is refused.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.user_mcp.assistant_confirmation import judge_settings_patch, judge_strategy
from src.domains.user_mcp.behavior import BehaviorInputs
from src.infrastructure.mcp.confirmation import (
    StoredToolChoice,
    ToolChoice,
    declaration_fingerprint,
)
from src.infrastructure.mcp.confirmation_loosening import (
    CONFIRMATION_LOOSENING,
    ConfirmationLooseningRefused,
)
from src.infrastructure.mcp.personal_settings_contract import PersonalMCPSettingsValues

pytestmark = pytest.mark.unit

_TOOLS: tuple[dict[str, Any], ...] = (
    {"name": "delete_note", "input_schema": {}, "annotations": {"destructive_hint": True}},
    {"name": "read_note", "input_schema": {}, "annotations": {"read_only_hint": True}},
)


def _inputs(
    *,
    hitl: bool | None = None,
    iterative: bool = False,
    expand: bool | None = None,
    choices: dict[str, StoredToolChoice] | None = None,
) -> BehaviorInputs:
    return BehaviorInputs(
        server_id=UUID(int=1),
        server_name="Notes",
        hitl_required=hitl,
        iterative_mode=iterative,
        react_expand_iterative=expand,
        tools=_TOOLS,
        tool_choices=choices or {},
    )


def _patch(**values: Any) -> PersonalMCPSettingsValues:
    return PersonalMCPSettingsValues.model_validate(values)


@pytest.fixture(autouse=True)
def _instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mcp_hitl_required", False)
    monkeypatch.setattr(settings, "mcp_react_enabled", True)
    monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", True)


class TestTheRefusal:
    def test_carries_its_code_and_names_the_settings_page(self) -> None:
        refusal = ConfirmationLooseningRefused()

        assert refusal.code == CONFIRMATION_LOOSENING == "CONFIRMATION_LOOSENING"
        assert "Settings > MCP Servers" in str(refusal)


class TestAServerSetting:
    def test_always_on_a_server_driven_directly_passes(self) -> None:
        judge_settings_patch(_inputs(), None, _patch(hitl_required=True))

    def test_any_other_confirmation_value_is_refused_even_when_nothing_is_lost(self) -> None:
        # « As declared » is already the effective rule here: nothing would be lost, and
        # the value is refused all the same — the chat writes « always » or nothing.
        with pytest.raises(ConfirmationLooseningRefused):
            judge_settings_patch(_inputs(), None, _patch(hitl_required=False))

    def test_always_on_a_dedicated_agent_passes(self) -> None:
        # Its question before the task now counts as asked: nothing is lost.
        judge_settings_patch(_inputs(iterative=True), None, _patch(hitl_required=True))

    def test_whatever_the_oracle_reports_as_lost_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.user_mcp import assistant_confirmation
        from src.domains.user_mcp.behavior import server_preview
        from src.domains.user_mcp.behavior_schemas import QuestionLoss

        def losing(*args: Any) -> Any:
            loss = QuestionLoss(server_id=UUID(int=1), server_name="Notes", tool_name="x")
            return server_preview(*args).model_copy(update={"questions_lost": [loss]})

        monkeypatch.setattr(assistant_confirmation, "server_preview", losing)

        with pytest.raises(ConfirmationLooseningRefused):
            judge_settings_patch(_inputs(), None, _patch(always_ask_tools=["read_note"]))

    def test_always_for_a_listed_tool_passes(self) -> None:
        judge_settings_patch(_inputs(), None, _patch(always_ask_tools=["read_note"]))

    def test_a_tool_the_catalogue_does_not_list_is_unavailable(self) -> None:
        with pytest.raises(ResourceNotFoundError):
            judge_settings_patch(_inputs(), None, _patch(always_ask_tools=["purge"]))

    def test_always_overrides_a_never_without_loss(self) -> None:
        never = {
            "delete_note": StoredToolChoice(ToolChoice.NEVER, declaration_fingerprint(_TOOLS[0]))
        }

        judge_settings_patch(_inputs(choices=never), None, _patch(always_ask_tools=["delete_note"]))


class TestWhoDrivesAServer:
    def test_a_dedicated_agent_under_always_passes(self) -> None:
        judge_settings_patch(_inputs(hitl=True), None, _patch(iterative_mode=True))

    def test_back_to_direct_tools_passes(self) -> None:
        judge_settings_patch(_inputs(hitl=True, iterative=True), None, _patch(iterative_mode=False))

    def test_a_dedicated_agent_following_the_declarations_passes(self) -> None:
        # Its task is asked before it starts, since a tool of it would ask.
        judge_settings_patch(_inputs(), None, _patch(iterative_mode=True))

    def test_letting_react_use_the_tools_directly_loses_nothing(self) -> None:
        judge_settings_patch(
            _inputs(hitl=True, iterative=True, expand=False),
            None,
            _patch(react_expand_iterative=True),
        )

    def test_a_value_left_as_stored_is_not_a_change(self) -> None:
        judge_settings_patch(
            _inputs(hitl=True, iterative=True), None, _patch(iterative_mode=True, name="Notes")
        )


class TestNothingToJudge:
    def test_a_patch_of_ordinary_settings_reads_no_synthesis(self) -> None:
        judge_settings_patch(_inputs(iterative=True), None, _patch(name="Notes 2"))


class TestTheAccountStrategy:
    def test_always_passes_when_nothing_is_lost(self) -> None:
        judge_strategy([_inputs()], None, True)

    def test_any_other_value_is_refused_even_when_nothing_is_lost(self) -> None:
        for stored, candidate in ((False, False), (None, None)):
            with pytest.raises(ConfirmationLooseningRefused):
                judge_strategy([_inputs()], stored, candidate)

    def test_always_passes_with_a_dedicated_agent_too(self) -> None:
        judge_strategy([_inputs(), _inputs(iterative=True)], None, True)

    def test_whatever_the_oracle_reports_as_lost_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.user_mcp import assistant_confirmation
        from src.domains.user_mcp.behavior_schemas import QuestionLoss, StrategyPreview

        loss = QuestionLoss(server_id=UUID(int=1), server_name="Notes", tool_name="x")
        monkeypatch.setattr(
            assistant_confirmation,
            "strategy_preview",
            lambda *args: StrategyPreview(questions_lost=[loss]),
        )

        with pytest.raises(ConfirmationLooseningRefused):
            judge_strategy([_inputs()], None, True)

    def test_a_server_with_its_own_choice_is_not_moved_by_the_account(self) -> None:
        judge_strategy([_inputs(hitl=False, iterative=True)], None, True)
