"""From the chat, LIA makes itself ask more before an MCP tool, never less (spec 2026-10-30 D7).

A change the judge refuses never becomes a card: the proposal answers with the refusal's
code and its sentence naming the settings page. A card proposed before the state moved is
judged again at the write, and the person reads why it was not applied. A gateway that
cannot judge refuses rather than lets a change through unjudged.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.exceptions import AuthorizationError
from src.domains.agents.application import personal_mcp_settings as settings_operation
from src.domains.agents.application.personal_mcp_settings_schemas import PersonalMCPSettingsInput
from src.infrastructure.mcp.confirmation_loosening import (
    CONFIRMATION_LOOSENING,
    ConfirmationLooseningRefused,
)
from src.infrastructure.mcp.personal_settings_contract import PersonalMCPSettingsValues
from src.infrastructure.mcp.personal_state_gateway import (
    PersonalMCPStateGateway,
    configure_personal_mcp_state,
)

pytestmark = pytest.mark.unit

_OWNER = UUID(int=1)


def _request(**patch_values: Any) -> PersonalMCPSettingsInput:
    return PersonalMCPSettingsInput(
        server_id=uuid4(), patch=PersonalMCPSettingsValues.model_validate(patch_values)
    )


@pytest.fixture
def gateway() -> Iterator[SimpleNamespace]:
    judge = AsyncMock()
    installed = PersonalMCPStateGateway(
        read=AsyncMock(),
        write=AsyncMock(),
        settings=AsyncMock(),
        judge_settings=judge,
    )
    previous = configure_personal_mcp_state(installed)
    try:
        yield SimpleNamespace(judge=judge, installed=installed)
    finally:
        configure_personal_mcp_state(previous)


@pytest.fixture(autouse=True)
def _access() -> Iterator[None]:
    with patch.object(settings_operation, "require_personal_mcp_access", AsyncMock()):
        yield


class TestTheProposal:
    async def test_a_refused_change_never_becomes_a_card(self, gateway: SimpleNamespace) -> None:
        gateway.judge.side_effect = ConfirmationLooseningRefused()

        with pytest.raises(ConfirmationLooseningRefused):
            await settings_operation.prepare_personal_mcp_settings(
                MagicMock(), _OWNER, _request(hitl_required=False)
            )

    async def test_the_judge_reads_the_patch_the_card_would_carry(
        self, gateway: SimpleNamespace
    ) -> None:
        request = _request(always_ask_tools=["delete_note"])
        gateway.judge.side_effect = ConfirmationLooseningRefused()

        with pytest.raises(ConfirmationLooseningRefused):
            await settings_operation.prepare_personal_mcp_settings(MagicMock(), _OWNER, request)

        (_db, owner, server, patch_), _ = gateway.judge.await_args
        assert (owner, server, patch_) == (_OWNER, request.server_id, request.patch)

    async def test_a_gateway_that_cannot_judge_refuses(self) -> None:
        previous = configure_personal_mcp_state(
            PersonalMCPStateGateway(read=AsyncMock(), write=AsyncMock(), settings=AsyncMock())
        )
        try:
            with pytest.raises(AuthorizationError):
                await settings_operation.prepare_personal_mcp_settings(
                    MagicMock(), _OWNER, _request(name="Notes")
                )
        finally:
            configure_personal_mcp_state(previous)


class TestTheModelReadsWhy:
    async def test_the_tool_answers_the_code_and_the_page_to_go_to(self) -> None:
        from langgraph.store.memory import InMemoryStore

        from src.domains.agents.application.native_tool_preparation import prepare_native_tool
        from tests.helpers.runtime_context import make_tool_runtime

        async def refused(*_: Any) -> Any:
            raise ConfirmationLooseningRefused()

        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=MagicMock())
        session.__aexit__ = AsyncMock(return_value=False)

        output = await prepare_native_tool(
            {"server_id": str(uuid4()), "patch": {"hitl_required": False}},
            make_tool_runtime(user_id=_OWNER, store=InMemoryStore()),
            name="update_lia_personal_mcp_server_settings_tool",
            model=PersonalMCPSettingsInput,
            prepare=refused,
            sessions=lambda: session,
        )

        assert not output.success
        assert output.error_code == CONFIRMATION_LOOSENING
        assert "Settings > MCP Servers" in output.message


class TestACardJudgedAgainAtTheWrite:
    async def test_the_person_reads_why_it_was_not_applied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.agents.application import draft_execution
        from src.domains.agents.application.action_preparation import build_action_content
        from src.domains.agents.application.psyche_summary_schemas import (
            PsycheSummaryPatch,
            PsycheSummaryScope,
        )
        from src.domains.agents.application.psyche_summary_spec import PSYCHE_SUMMARY_OPERATION
        from src.domains.users.preference_cas import PreferenceWriteReceipt

        scope = PsycheSummaryScope(
            digest="a" * 64, input_digest="b" * 64, state_present=False, language="fr", settings={}
        )
        public = scope.public_scope()
        draft = build_action_content(
            uuid4(),
            PSYCHE_SUMMARY_OPERATION,
            PsycheSummaryPatch(psyche_summary=scope),
            {"psyche_summary": public},
            {"psyche_summary": {**public, "requested": True}},
        )

        async def refused(*_: Any) -> None:
            raise ConfirmationLooseningRefused()

        monkeypatch.setattr(draft_execution, "_apply_approved_action", refused)
        result = await draft_execution._execute_outcome(
            draft, draft.actor_id, PreferenceWriteReceipt()
        )

        assert not result.success and result.error_code == CONFIRMATION_LOOSENING
        assert not result.committed

    def test_the_card_says_it_in_every_language(self) -> None:
        from src.core.i18n_draft_refusals import (
            WORDED_REFUSAL_CODES,
            get_draft_refusal_message,
        )

        assert CONFIRMATION_LOOSENING in WORDED_REFUSAL_CODES
        for language in ("fr", "en", "de", "es", "it", "zh-CN"):
            assert "MCP" in get_draft_refusal_message(CONFIRMATION_LOOSENING, language)


class TestTheCardShowsWhatChanges:
    @staticmethod
    def _expected() -> Any:
        from datetime import UTC, datetime

        from src.infrastructure.mcp.personal_metadata_contract import PersonalMCPReadItem
        from src.infrastructure.mcp.personal_state_contract import PersonalMCPStateSnapshot

        now = datetime(2026, 10, 31, tzinfo=UTC)
        server = PersonalMCPReadItem(
            id=uuid4(),
            name="Notes",
            endpoint_host="notes.example",
            auth_type="none",
            status="active",
            is_enabled=True,
            plugin_id=None,
            domain_description=None,
            timeout_seconds=30,
            hitl_required=None,
            iterative_mode=True,
            react_expand_iterative=None,
            suspended_tool_choices=0,
            header_name=None,
            has_credentials=False,
            has_oauth_credentials=False,
            oauth_scopes=None,
            tool_count=2,
            tools=(),
            next_tool_offset=None,
            last_connected_at=None,
            has_connection_error=False,
            created_at=now,
            updated_at=now,
        )
        return PersonalMCPStateSnapshot(server=server, digest="0" * 64)

    def test_before_and_after_carry_the_confirmation_the_driver_and_the_tools(self) -> None:
        from src.domains.agents.application.personal_mcp_settings_schemas import (
            personal_mcp_settings_target,
        )

        expected = self._expected()
        patch_ = PersonalMCPSettingsValues(
            hitl_required=True, react_expand_iterative=False, always_ask_tools=("delete_note",)
        )

        before = personal_mcp_settings_target(expected)
        after = personal_mcp_settings_target(expected, patch_)

        assert (before["hitl_required"], before["react_expand_iterative"]) == (None, None)
        assert (after["hitl_required"], after["react_expand_iterative"]) == (True, False)
        assert after["always_ask_tools"] == ["delete_note"]
        assert "always_ask_tools" not in before


class TestAnAmendedCard:
    async def test_is_judged_like_a_proposed_one_and_keeps_its_sentence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed amendment cancels the card with the error's text as its reason: the
        refusal reaches it whole — its sentence names the page — never as « invalid input »."""
        from src.domains.agents.application import draft_editing
        from src.domains.agents.application.action_preparation import build_action_content
        from src.domains.agents.application.personal_mcp_settings_schemas import (
            PersonalMCPSettingsObservation,
            PersonalMCPSettingsPatch,
            personal_mcp_settings_target,
        )
        from src.domains.agents.application.personal_mcp_settings_spec import (
            PERSONAL_MCP_SETTINGS_OPERATION,
        )

        expected = TestTheCardShowsWhatChanges._expected()
        request = PersonalMCPSettingsInput(
            server_id=expected.server.id, patch=PersonalMCPSettingsValues(name="Notes 2")
        )
        draft = build_action_content(
            _OWNER,
            PERSONAL_MCP_SETTINGS_OPERATION,
            PersonalMCPSettingsPatch(
                personal_mcp_settings=PersonalMCPSettingsObservation(
                    request=request, expected=expected
                )
            ),
            {"personal_mcp_settings": personal_mcp_settings_target(expected)},
            {"personal_mcp_settings": personal_mcp_settings_target(expected, request.patch)},
        )

        async def refused(*_: Any) -> Any:
            raise ConfirmationLooseningRefused()

        monkeypatch.setitem(draft_editing.MANAGEMENT_EDITORS, draft.operation_id, refused)

        with pytest.raises(ConfirmationLooseningRefused) as refusal:
            await draft_editing.rebuild_application_draft(draft.model_dump(mode="json"), {})

        assert "Settings > MCP Servers" in str(refusal.value)
