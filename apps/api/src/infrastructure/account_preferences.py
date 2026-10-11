"""Shared account layout commands used by UI and native confirmed operations."""

from collections.abc import Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, GetJsonSchemaHandler, JsonValue, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, raise_user_not_found
from src.core.settings_surface import (
    ADMIN_SETTINGS_SECTION_TOKENS,
    PERSONAL_SETTINGS_SECTION_TOKENS,
)
from src.domains.briefing.constants import SECTION_NAMES
from src.domains.briefing.preferences import BriefingPreferences, sanitize_briefing_preferences
from src.domains.chat.shortcuts import ChatShortcut, ChatShortcutsPayload, sanitize_chat_shortcuts
from src.domains.shared.settings_shortcuts import (
    SettingsShortcutsPayload,
    sanitize_settings_shortcuts,
)
from src.domains.users.models import User
from src.domains.users.preference_cas import (
    PreferenceWriteReceipt,
    verified_preference_noop,
)
from src.domains.users.repository import UserRepository

_SECTION_SCHEMA_NAMES: list[JsonValue] = []
_SECTION_SCHEMA_NAMES.extend(sorted(SECTION_NAMES))


class StrictBriefingPreferences(BriefingPreferences):
    model_config = ConfigDict(frozen=True, extra="forbid")
    hidden: list[str] = Field(
        default_factory=list,
        max_length=len(SECTION_NAMES),
        json_schema_extra={"items": {"type": "string", "enum": _SECTION_SCHEMA_NAMES}},
    )
    order: list[str] = Field(
        default_factory=list,
        max_length=len(SECTION_NAMES),
        json_schema_extra={"items": {"type": "string", "enum": _SECTION_SCHEMA_NAMES}},
    )


class StrictChatShortcut(ChatShortcut):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LayoutPreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    briefing_preferences: StrictBriefingPreferences | None = None
    chat_shortcuts: list[StrictChatShortcut] | None = Field(
        default=None, max_length=settings.chat_shortcuts_max_count
    )
    settings_shortcuts: list[str] | None = Field(
        default=None, max_length=settings.settings_shortcuts_max_count
    )

    @model_validator(mode="after")
    def require_valid_changes(self) -> LayoutPreferencePatch:
        if not self.model_fields_set:
            raise ValueError("A layout patch must contain a change")
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError("Null is not a layout reset; use an explicit empty list or grid")
        if self.briefing_preferences is not None:
            grid = sanitize_briefing_preferences(self.briefing_preferences.model_dump(mode="json"))
            self.briefing_preferences = StrictBriefingPreferences.model_validate(
                grid.model_dump(mode="json")
            )
        if self.chat_shortcuts is not None:
            ChatShortcutsPayload(shortcuts=self.chat_shortcuts)
        if self.settings_shortcuts is not None:
            SettingsShortcutsPayload(shortcuts=self.settings_shortcuts)
            if "my-shortcuts" in self.settings_shortcuts:
                raise ValueError("The shortcut picker cannot pin itself")
            if (
                not set(self.settings_shortcuts)
                <= PERSONAL_SETTINGS_SECTION_TOKENS | ADMIN_SETTINGS_SECTION_TOKENS
            ):
                raise ValueError("Unknown pinned settings section")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        published = handler.resolve_ref_schema(
            super().__get_pydantic_json_schema__(schema, handler)
        )
        properties: dict[str, JsonSchemaValue] = {}
        for name, original in published["properties"].items():
            prop = {key: value for key, value in original.items() if key != "default"}
            choices = [choice for choice in prop.pop("anyOf", []) if choice.get("type") != "null"]
            if len(choices) == 1:
                prop.update(choices[0])
            elif choices:
                prop["anyOf"] = choices
            properties[name] = prop
        return {**published, "minProperties": 1, "properties": properties}


def require_layout_scope(actor: User, patch: LayoutPreferencePatch) -> None:
    if not actor.is_superuser and ADMIN_SETTINGS_SECTION_TOKENS.intersection(
        patch.settings_shortcuts or []
    ):
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})


def layout_values(actor: User) -> dict[str, JsonValue]:
    """Exactly the tolerant values visible in the UI, with current role filtering."""
    pinned = sanitize_settings_shortcuts(
        actor.settings_shortcuts, max_count=settings.settings_shortcuts_max_count
    )
    visible = PERSONAL_SETTINGS_SECTION_TOKENS | (
        ADMIN_SETTINGS_SECTION_TOKENS if actor.is_superuser else frozenset()
    )
    return {
        "briefing_preferences": sanitize_briefing_preferences(
            actor.briefing_preferences
        ).model_dump(mode="json"),
        "chat_shortcuts": sanitize_chat_shortcuts(actor.chat_shortcuts).model_dump(mode="json")[
            "shortcuts"
        ],
        "settings_shortcuts": [
            token for token in pinned if token in visible and token != "my-shortcuts"
        ],
    }


async def update_layout_preferences(
    db: AsyncSession,
    actor_id: UUID,
    patch: LayoutPreferencePatch,
    *,
    expected: Mapping[str, JsonValue] | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> User:
    patch = LayoutPreferencePatch.model_validate(patch.model_dump(exclude_unset=True))
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None:
        raise_user_not_found(actor_id)
    assert actor is not None
    require_layout_scope(actor, patch)
    if expected is not None:
        current = layout_values(actor)
        if set(expected) != patch.model_fields_set:
            raise ValueError("Expected layout must cover exactly the patched fields")
        if {name: current[name] for name in patch.model_fields_set} != dict(expected):
            raise ResourceConflictError("layout_preferences", detail={"error_code": "STALE_STATE"})
        stored = {name: getattr(actor, name) for name in patch.model_fields_set}
        if stored == patch.model_dump(mode="json", exclude_unset=True) and verified_preference_noop(
            patch, expected, receipt
        ):
            return actor
    for name, value in patch.model_dump(mode="json", exclude_unset=True).items():
        setattr(actor, name, value)
    db.add(actor)
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    await db.refresh(actor)
    return actor


if set(BriefingPreferences.model_fields) != {"hidden", "order"}:
    raise AssertionError(
        "New briefing preferences require reviewed normalization and preview coverage"
    )
if set(ChatShortcut.model_fields) != {"id", "text"}:
    raise AssertionError("New shortcut fields require reviewed projection and sensitivity")
if set(SettingsShortcutsPayload.model_fields) != {"shortcuts"}:
    raise AssertionError("New pinned-section fields require explicit scope coverage")
