"""List edits preserve concurrent UI writes, reject hidden commands and expose real bounds."""

import re
from importlib import import_module
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.chat.shortcuts import ChatShortcut
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [{}, {"settings_shortcuts": None}, {"chat_shortcuts": None}, {"briefing_preferences": None}],
)
def test_layout_schema_never_offers_an_empty_or_null_change(payload: dict[str, object]) -> None:
    model = import_module("src.infrastructure.account_preferences").LayoutPreferencePatch
    assert not Draft202012Validator(model.model_json_schema()).is_valid(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"settings_shortcuts": None},
        {"chat_shortcuts": [{"id": "custom", "text": "Hello", "secret": "hidden"}]},
        {"briefing_preferences": {"hidden": ["unknown"]}},
        {"settings_shortcuts": ["theme", "theme"]},
    ],
)
def test_layout_patch_refuses_invalid_or_hidden_input(payload: dict[str, object]) -> None:
    model = import_module("src.infrastructure.account_preferences").LayoutPreferencePatch
    with pytest.raises(ValidationError):
        model.model_validate(payload)


async def test_layout_write_cannot_overwrite_a_newer_ui_list() -> None:
    owner = import_module("src.infrastructure.account_preferences")
    actor = User(id=uuid4(), is_active=True, settings_shortcuts=["font"], deleted_at=None)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = actor
    receipt = PreferenceWriteReceipt()
    with pytest.raises(ResourceConflictError):
        await owner.update_layout_preferences(
            db,
            actor.id,
            owner.LayoutPreferencePatch(settings_shortcuts=["theme"]),
            expected={"settings_shortcuts": []},
            receipt=receipt,
        )
    assert actor.settings_shortcuts == ["font"]
    db.commit.assert_not_awaited()
    assert not receipt.committed


def test_reserved_slash_commands_are_refused_by_the_server_schema() -> None:
    with pytest.raises(ValidationError):
        ChatShortcut(id="weather", text="Replace a builtin")


def test_reserved_command_authority_covers_the_actual_frontend_registry() -> None:
    ids = import_module("src.core.slash_commands").STATIC_SLASH_COMMAND_IDS
    path = Path(__file__).resolve().parents[7] / "apps/web/src/lib/slash-commands.ts"
    source = path.read_text(encoding="utf-8")
    table = source.split("export const STATIC_SLASH_COMMANDS", 1)[1].split("];", 1)[0]
    assert ids == frozenset(re.findall(r"id: '([^']+)'", table))


async def test_an_ordinary_account_cannot_pin_an_administrative_surface() -> None:
    from src.core.exceptions import AuthorizationError

    owner = import_module("src.infrastructure.account_preferences")
    actor = User(
        id=uuid4(), is_active=True, is_superuser=False, settings_shortcuts=[], deleted_at=None
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = actor
    with pytest.raises(AuthorizationError):
        await owner.update_layout_preferences(
            db, actor.id, owner.LayoutPreferencePatch(settings_shortcuts=["admin-users"])
        )
    db.commit.assert_not_awaited()
    assert actor.settings_shortcuts == []


def test_every_new_settings_section_requires_a_reviewed_server_role_classification() -> None:
    owner = import_module("src.core.settings_surface")
    path = Path(__file__).resolve().parents[7] / "apps/web/src/lib/settings-sections.ts"
    source = path.read_text(encoding="utf-8").split("export const SETTINGS_SECTIONS = {", 1)[1]
    entries = re.findall(r"^  (?:'([^']+)'|([a-z-]+)): \{\s+tab: '([^']+)'", source, re.MULTILINE)
    assert owner.ADMIN_SETTINGS_SECTION_TOKENS == {
        quoted or plain for quoted, plain, tab in entries if tab == "administration"
    }
    assert owner.PERSONAL_SETTINGS_SECTION_TOKENS == {
        quoted or plain for quoted, plain, tab in entries if tab != "administration"
    }


def test_partial_grid_intent_materializes_every_default_before_confirmation() -> None:
    from src.domains.briefing.constants import SECTION_DISPLAY_ORDER_DEFAULT

    owner = import_module("src.infrastructure.account_preferences")
    patch = owner.LayoutPreferencePatch(briefing_preferences={"hidden": ["weather"]})
    assert patch.model_dump(mode="json", exclude_unset=True) == {
        "briefing_preferences": {
            "hidden": ["weather"],
            "order": list(SECTION_DISPLAY_ORDER_DEFAULT),
        }
    }


async def test_explicit_grid_default_is_saved_even_when_an_unset_column_displays_that_default() -> (
    None
):
    from src.domains.briefing.constants import SECTION_DISPLAY_ORDER_DEFAULT

    owner = import_module("src.infrastructure.account_preferences")
    actor = User(
        id=uuid4(), is_active=True, is_superuser=False, briefing_preferences=None, deleted_at=None
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = actor
    receipt = PreferenceWriteReceipt()
    await owner.update_layout_preferences(
        db,
        actor.id,
        owner.LayoutPreferencePatch(briefing_preferences={}),
        expected={
            "briefing_preferences": {"hidden": [], "order": list(SECTION_DISPLAY_ORDER_DEFAULT)}
        },
        receipt=receipt,
    )
    db.commit.assert_awaited_once()
    assert receipt.committed and not receipt.no_op
    assert actor.briefing_preferences == {
        "hidden": [],
        "order": list(SECTION_DISPLAY_ORDER_DEFAULT),
    }
