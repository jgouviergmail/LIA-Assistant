"""The account's MCP strategy travels in the preferences patch « always » alone (spec 2026-10-30 D7).

The chat may switch « always ask before an MCP tool » on, never off: the schema
publishes ``true`` alone, any other value is refused with a sentence naming the
settings page, and the computation that alerts the person on that page judges the
change at proposal and again at the write. The person's own page is not bound by it.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from src.domains.agents.application import preference_dispatch, preparation
from src.domains.agents.application.schemas import PreferencePatch
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.mcp.confirmation_loosening import ConfirmationLooseningRefused
from src.infrastructure.mcp.personal_state_gateway import (
    PersonalMCPStateGateway,
    configure_personal_mcp_state,
)

pytestmark = pytest.mark.unit

_OWNER = UUID(int=1)
_FIELD = "mcp_hitl_required"


@pytest.fixture
def judge() -> Iterator[AsyncMock]:
    strategy = AsyncMock()
    previous = configure_personal_mcp_state(
        PersonalMCPStateGateway(read=AsyncMock(), write=AsyncMock(), judge_strategy=strategy)
    )
    try:
        yield strategy
    finally:
        configure_personal_mcp_state(previous)


class TestThePatch:
    def test_the_assistant_may_write_the_strategy(self) -> None:
        assert PreferencePatch.model_validate({_FIELD: True}).mcp_hitl_required is True

    def test_the_schema_publishes_true_alone_and_where_to_go_otherwise(self) -> None:
        published = PreferencePatch.model_json_schema()["properties"][_FIELD]

        assert published["type"] == "boolean" and published["const"] is True
        assert "Settings > MCP Servers" in published["description"]

    def test_the_card_names_the_field_in_every_language(self) -> None:
        from src.core.i18n_application import APPLICATION_FIELD_LABELS

        assert all(labels[_FIELD] for labels in APPLICATION_FIELD_LABELS.values())


class TestTheProposal:
    async def test_is_judged_before_any_card(self, judge: AsyncMock) -> None:
        judge.side_effect = ConfirmationLooseningRefused()
        read = AsyncMock()

        with (
            patch.object(preparation, "read_preferences", read),
            pytest.raises(ConfirmationLooseningRefused),
        ):
            await preparation.prepare_preference_content(
                MagicMock(), _OWNER, PreferencePatch.model_validate({_FIELD: False})
            )

        judge.assert_awaited_once()
        assert judge.await_args.args[1:] == (_OWNER, False)
        read.assert_not_awaited()

    async def test_other_preferences_are_never_judged(self, judge: AsyncMock) -> None:
        read = AsyncMock(return_value=SimpleNamespace(values={"theme": "dark"}))

        with patch.object(preparation, "read_preferences", read):
            await preparation.prepare_preference_content(
                MagicMock(), _OWNER, PreferencePatch.model_validate({"theme": "light"})
            )

        judge.assert_not_awaited()

    async def test_without_a_judge_nothing_unjudged_goes_through(self) -> None:
        from src.core.exceptions import AuthorizationError

        previous = configure_personal_mcp_state(
            PersonalMCPStateGateway(read=AsyncMock(), write=AsyncMock())
        )
        try:
            with pytest.raises(AuthorizationError):
                await preparation.prepare_preference_content(
                    MagicMock(), _OWNER, PreferencePatch.model_validate({_FIELD: True})
                )
        finally:
            configure_personal_mcp_state(previous)


class TestTheWrite:
    async def test_is_judged_again_before_the_account_is_written(self, judge: AsyncMock) -> None:
        judge.side_effect = ConfirmationLooseningRefused()
        update = AsyncMock()

        with (
            patch.object(preference_dispatch.UserService, "update_user", update),
            pytest.raises(ConfirmationLooseningRefused),
        ):
            await preference_dispatch.execute_preference_patch(
                MagicMock(),
                _OWNER,
                "preferences.update",
                {_FIELD: True},
                {_FIELD: None},
                PreferenceWriteReceipt(),
            )

        update.assert_not_awaited()

    async def test_a_judged_change_is_written(self, judge: AsyncMock) -> None:
        update = AsyncMock()

        with patch.object(preference_dispatch.UserService, "update_user", update):
            await preference_dispatch.execute_preference_patch(
                MagicMock(),
                _OWNER,
                "preferences.update",
                {_FIELD: True},
                {_FIELD: None},
                PreferenceWriteReceipt(),
            )

        judge.assert_awaited_once()
        update.assert_awaited_once()


class TestTheOpenPageFollows:
    def test_a_change_of_the_strategy_refreshes_the_mcp_servers_page(self) -> None:
        from src.domains.agents.application.action_preparation import build_action_content
        from src.domains.agents.application.registry import APPLICATION_OPERATIONS
        from src.domains.agents.application.state_changes import changed_resources

        spec = APPLICATION_OPERATIONS.get("preferences.update")
        strategy = build_action_content(
            _OWNER,
            spec,
            PreferencePatch.model_validate({_FIELD: True}),
            {_FIELD: None},
            {_FIELD: True},
        )
        theme = build_action_content(
            _OWNER,
            spec,
            PreferencePatch.model_validate({"theme": "light"}),
            {"theme": "dark"},
            {"theme": "light"},
        )

        assert "user_mcp" in changed_resources(strategy)
        assert "user_mcp" not in changed_resources(theme)
