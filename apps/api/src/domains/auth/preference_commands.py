"""Non-secret assistant preference commands shared by the UI and native drafts."""

from collections.abc import Mapping
from contextlib import suppress
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    GetJsonSchemaHandler,
    JsonValue,
    StrictBool,
    field_validator,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import RESPONSE_DISPLAY_MODE_CHOICES
from src.core.exceptions import raise_user_not_found
from src.domains.auth.schemas import (
    DebugPanelPreferenceRequest,
    DisplayModePreferenceRequest,
    ExecutionModePreferenceRequest,
    HealthMetricsAgentsPreferenceRequest,
    LocationPreferenceRequest,
    LoginNotificationsPreferenceRequest,
    MemoryPreferenceRequest,
    OnboardingPreferenceRequest,
    TokensDisplayPreferenceRequest,
    VoiceModePreferenceRequest,
    VoicePreferenceRequest,
)
from src.domains.users.extraction_consent import invalidate_extractions
from src.domains.users.models import User
from src.domains.users.preference_cas import (
    PreferenceWriteReceipt,
    check_expected_preferences,
    verified_preference_noop,
)
from src.domains.users.repository import UserRepository

# Each entry names its original HTTP contract and any differently named payload key.
ASSISTANT_PREFERENCE_SOURCES: dict[str, tuple[type[BaseModel], str]] = {
    "memory_enabled": (MemoryPreferenceRequest, "memory_enabled"),
    "health_metrics_agents_enabled": (
        HealthMetricsAgentsPreferenceRequest,
        "health_metrics_agents_enabled",
    ),
    "execution_mode": (ExecutionModePreferenceRequest, "execution_mode"),
    "use_last_known_location": (LocationPreferenceRequest, "enabled"),
    "voice_enabled": (VoicePreferenceRequest, "voice_enabled"),
    "voice_mode_enabled": (VoiceModePreferenceRequest, "voice_mode_enabled"),
    "voice_stt_mode": (VoiceModePreferenceRequest, "voice_stt_mode"),
    "tokens_display_enabled": (TokensDisplayPreferenceRequest, "tokens_display_enabled"),
    "login_notifications_enabled": (LoginNotificationsPreferenceRequest, "enabled"),
    "onboarding_completed": (OnboardingPreferenceRequest, "onboarding_completed"),
    "debug_panel_enabled": (DebugPanelPreferenceRequest, "debug_panel_enabled"),
    "response_display_mode": (DisplayModePreferenceRequest, "response_display_mode"),
}


class AssistantPreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_enabled: StrictBool | None = None
    health_metrics_agents_enabled: StrictBool | None = None
    execution_mode: Literal["pipeline", "react"] | None = None
    use_last_known_location: StrictBool | None = None
    voice_enabled: StrictBool | None = None
    voice_mode_enabled: StrictBool | None = None
    voice_stt_mode: Literal["local", "remote"] | None = None
    tokens_display_enabled: StrictBool | None = None
    login_notifications_enabled: StrictBool | None = None
    onboarding_completed: StrictBool | None = None
    debug_panel_enabled: StrictBool | None = None
    response_display_mode: str | None = None

    @field_validator("response_display_mode")
    @classmethod
    def validate_display_mode(cls, value: str | None) -> str | None:
        if value is not None and value not in RESPONSE_DISPLAY_MODE_CHOICES:
            raise ValueError("Unsupported response display mode")
        return value

    @model_validator(mode="after")
    def validate_original_contracts(self) -> AssistantPreferencePatch:
        if not self.model_fields_set:
            raise ValueError("Name at least one assistant preference")
        for name in self.model_fields_set:
            value = getattr(self, name)
            if value is None:
                raise ValueError("A non-null preference requires an explicit value")
            model, source_name = ASSISTANT_PREFERENCE_SOURCES[name]
            model.model_validate({source_name: value})
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(
            super().__get_pydantic_json_schema__(core_schema, handler)
        )
        properties: dict[str, JsonSchemaValue] = {}
        for name, (source, source_name) in ASSISTANT_PREFERENCE_SOURCES.items():
            prop = dict(source.model_json_schema()["properties"][source_name])
            alternatives = [item for item in prop.pop("anyOf", []) if item.get("type") != "null"]
            if len(alternatives) == 1:
                prop.update(alternatives[0])
            prop.pop("default", None)
            if name == "response_display_mode":
                prop["enum"] = list(RESPONSE_DISPLAY_MODE_CHOICES)
            properties[name] = prop
        return {**schema, "minProperties": 1, "properties": properties}


def stt_remote_available() -> bool:
    from src.core.constants import ELEVENLABS_PROVIDER_NAME
    from src.core.llm_config_helper import get_provider_api_key

    return bool(get_provider_api_key(ELEVENLABS_PROVIDER_NAME))


async def update_assistant_preferences(
    db: AsyncSession,
    actor_id: UUID,
    patch: AssistantPreferencePatch,
    *,
    expected: Mapping[str, JsonValue] | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> User:
    patch = AssistantPreferencePatch.model_validate(patch.model_dump(exclude_unset=True))
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None:
        raise_user_not_found(actor_id)
    assert actor is not None
    if expected is not None:
        check_expected_preferences(actor, patch, expected)
        if verified_preference_noop(patch, expected, receipt):
            return actor
    if patch.voice_stt_mode == "remote" and not stt_remote_available():
        raise ValueError("Remote STT is not configured")
    changed_consent = any(
        name in patch.model_fields_set and getattr(actor, name) != getattr(patch, name)
        for name in ("memory_enabled", "health_metrics_agents_enabled")
    )
    if changed_consent:
        invalidate_extractions(actor)
    voice_changed = (
        "voice_enabled" in patch.model_fields_set and actor.voice_enabled != patch.voice_enabled
    )
    for name in patch.model_fields_set:
        setattr(actor, name, getattr(patch, name))
    if patch.use_last_known_location is False:
        # Consent and removal are one transaction; no location can be retained in between.
        actor.last_known_location_encrypted = None
        actor.last_known_location_updated_at = None
    db.add(actor)
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    await db.refresh(actor)
    if voice_changed:
        with suppress(Exception):
            from src.infrastructure.observability.metrics_voice import (
                voice_preference_toggles_total,
            )

            voice_preference_toggles_total.labels(
                action="enabled" if actor.voice_enabled else "disabled"
            ).inc()
    return actor


def assert_assistant_preference_coverage() -> None:
    if set(AssistantPreferencePatch.model_fields) != set(ASSISTANT_PREFERENCE_SOURCES):
        raise AssertionError("Assistant preference fields require an explicit source contract")
    sources = {model for model, _ in ASSISTANT_PREFERENCE_SOURCES.values()}
    for source in sources:
        mapped = {
            field for model, field in ASSISTANT_PREFERENCE_SOURCES.values() if model is source
        }
        if mapped != set(source.model_fields):
            raise AssertionError(
                f"Unreviewed assistant preference source fields: {source.__name__}"
            )


assert_assistant_preference_coverage()
