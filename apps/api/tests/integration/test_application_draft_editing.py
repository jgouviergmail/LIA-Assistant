"""The actual modifier rebuilds a proposal without dropping unrelated intent."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.channel_operations import (
    prepare_channel_binding_content,
    prepare_channel_unlink_content,
)
from src.domains.agents.application.channel_schemas import (
    ChannelBindingUnlinkRequest,
    ChannelBindingUpdateRequest,
)
from src.domains.agents.application.command_repository import (
    get_command,
    matches_command,
    save_command,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.location_preparation import prepare_location_change
from src.domains.agents.application.location_schemas import LocationChangeRequest
from src.domains.agents.application.preparation import (
    prepare_layout_content,
    prepare_preference_content,
)
from src.domains.agents.application.schemas import PreferencePatch
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.briefing.constants import SECTION_DISPLAY_ORDER_DEFAULT
from src.domains.channels.models import UserChannelBinding
from src.domains.users.models import User
from src.domains.users.schemas import HomeLocationData
from src.infrastructure.account_preferences import LayoutPreferencePatch
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("remove", [False, True])
async def test_channel_modifier_rebuilds_private_identity_and_invalidates_old_approval(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    remove: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "channels_enabled", True)
    binding = UserChannelBinding(
        id=uuid4(),
        user_id=test_user.id,
        channel_type="telegram",
        channel_user_id="private-edit-chat",
        channel_username="@reader",
        is_active=True,
    )
    async_session.add(binding)
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    selector = (
        {"binding_id": str(binding.id)}
        if remove
        else {"binding_id": str(binding.id), "enabled": True}
    )
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "intent": selector,
                    "remove_fields": [],
                }
            )
        )
    )
    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
    ):
        if remove:
            old = await prepare_channel_unlink_content(
                async_session,
                test_user.id,
                ChannelBindingUnlinkRequest(binding_id=binding.id),
            )
        else:
            old = await prepare_channel_binding_content(
                async_session,
                test_user.id,
                ChannelBindingUpdateRequest(binding_id=binding.id, enabled=False),
            )
        draft_id = "draft-" + str(old.command_id)
        await save_command(async_session, old, draft_id)
        await async_session.commit()
        if remove:
            # Current source supports one Telegram binding per user; emulate a
            # visible provider identity refresh rather than inventing another kind.
            binding.channel_username = "@current-reader"
            await async_session.commit()
        modified = await DraftModificationService().modify(
            old.model_dump(mode="json"),
            "Garde ce canal actif",
            "application_action",
            user_language="fr",
            run_id=draft_id,
        )
    revised = ApplicationActionDraftContent.model_validate(modified)
    assert revised.intent["channel_binding"]["is_active"] is True
    assert revised.intent["channel_binding"]["channel_user_id"] == "private-edit-chat"
    assert revised.intent["channel_binding"]["channel_username"] == (
        "@current-reader" if remove else "@reader"
    )
    assert "private-edit-chat" not in str(llm.ainvoke.call_args.args[0])
    await async_session.refresh(binding)
    assert binding.is_active
    row = await get_command(async_session, old.command_id, test_user.id)
    assert row is not None and matches_command(row, revised, draft_id)
    assert not matches_command(row, old, draft_id)


@pytest.mark.parametrize("unchanged", [True, False])
async def test_home_modifier_only_resolves_a_changed_address_and_replaces_canonical_preview(
    async_session: AsyncSession,
    test_user: User,
    unchanged: bool,
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "intent": {"action": "set", "address": "Original" if unchanged else "Revised"},
                    "remove_fields": [],
                }
            )
        )
    )
    resolver = AsyncMock(
        side_effect=[
            HomeLocationData(address="Original", lat=4, lon=5),
            HomeLocationData(address="Revised", lat=6, lon=7),
        ]
    )
    log = MagicMock()
    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
        patch("src.domains.agents.services.hitl.draft_modifier.logger", log),
        patch(
            "src.domains.agents.application.location_preparation.resolve_home_location", resolver
        ),
        patch(
            "src.domains.connectors.service.ConnectorService.is_places_enabled",
            AsyncMock(return_value=True),
        ),
    ):
        old = await prepare_location_change(
            async_session, test_user.id, LocationChangeRequest(action="set", address="Original")
        )
        draft_id = "draft-" + str(old.command_id)
        await save_command(async_session, old, draft_id)
        await async_session.commit()
        modified = await DraftModificationService().modify(
            old.model_dump(mode="json"),
            "Revois cette adresse",
            "application_action",
            user_language="fr",
            run_id=draft_id,
        )
    revised = ApplicationActionDraftContent.model_validate(modified)
    assert resolver.await_count == (1 if unchanged else 2)
    assert revised.after["home_location"]["address"] == ("Original" if unchanged else "Revised")
    assert revised.after["home_location"]["lat"] == (4 if unchanged else 6)
    assert test_user.home_location_encrypted is None
    prompt = str(llm.ainvoke.call_args.args[0])
    assert '"lat"' not in prompt and '"place_id"' not in prompt
    assert "Original" not in str(log.mock_calls) and "Revised" not in str(log.mock_calls)
    row = await get_command(async_session, old.command_id, test_user.id)
    assert row is not None and matches_command(row, revised, draft_id)


async def test_grid_edit_preserves_the_proposed_order_when_only_visibility_changes(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    order = list(reversed(SECTION_DISPLAY_ORDER_DEFAULT))
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content='{"intent":{"briefing_preferences":{"hidden":["weather"]}},"remove_fields":[]}'
        )
    )
    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
    ):
        old = await prepare_layout_content(
            async_session,
            test_user.id,
            LayoutPreferencePatch(briefing_preferences={"hidden": [], "order": order}),
        )
        draft_id = "draft-" + str(old.command_id)
        await save_command(async_session, old, draft_id)
        await async_session.commit()
        modified = await DraftModificationService().modify(
            old.model_dump(mode="json"),
            "Masque seulement la météo et garde l’ordre prévu",
            "application_action",
            user_language="fr",
            run_id=draft_id,
        )
    revised = ApplicationActionDraftContent.model_validate(modified)
    assert revised.after == {"briefing_preferences": {"hidden": ["weather"], "order": order}}
    await async_session.refresh(test_user)
    assert test_user.briefing_preferences is None


@pytest.mark.parametrize("remove_theme", [False, True])
@pytest.mark.parametrize("full_echo", [False, True])
async def test_modifier_rebuilds_exact_preview_and_invalidates_the_original(
    async_session: AsyncSession,
    test_user: User,
    remove_theme: bool,
    full_echo: bool,
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "intent": {"font_size": 18, **({"theme": "dark"} if full_echo else {})},
                    "remove_fields": ["theme"] if remove_theme else [],
                }
            )
        )
    )
    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
    ):
        old = await prepare_preference_content(
            async_session, test_user.id, PreferencePatch(font_size=17, theme="dark")
        )
        draft_id = "draft-" + str(old.command_id)
        await save_command(async_session, old, draft_id)
        await async_session.commit()
        modified = await DraftModificationService().modify(
            old.model_dump(mode="json"),
            "La police à 18" + (", abandonne le thème" if remove_theme else ""),
            "application_action",
            user_language="fr",
            run_id=draft_id,
        )
    revised = ApplicationActionDraftContent.model_validate(modified)
    assert revised.after == (
        {"font_size": 18} if remove_theme else {"font_size": 18, "theme": "dark"}
    )
    await async_session.refresh(test_user)
    assert test_user.font_size == 16
    row = await get_command(async_session, old.command_id, test_user.id)
    assert row is not None
    assert not matches_command(row, old, draft_id)
    assert matches_command(row, revised, draft_id)
    prompt = llm.ainvoke.call_args.args[0]
    assert str(test_user.id) not in str(prompt)
    assert "hashed_password" not in str(prompt)
    assert '"maximum": 20' in str(prompt)
