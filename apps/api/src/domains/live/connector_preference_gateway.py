"""Fresh saved Live connector settings, without model discovery or provider probes on read."""

from uuid import UUID

import httpx
from pydantic import JsonValue, TypeAdapter
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.core.i18n import normalize_language
from src.domains.connectors.models import Connector
from src.domains.live.configuration import effective_live_configuration
from src.domains.live.connector_preference_commands import connector_preference_snapshot
from src.domains.live.connector_service import LiveConnectorService
from src.domains.live.errors import LiveRefusedError
from src.domains.live.model_settings import LiveModelSettings
from src.domains.live.schemas import (
    LiveConfigResponse,
    LiveConnectorResponse,
    LiveConnectorSettings,
    LiveModel,
    LiveModelsResponse,
    LiveVoice,
    LiveVoicesResponse,
)
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.live_connector_preferences import (
    LiveConnectorPreferenceProjection,
    LiveConnectorPreferenceSnapshot,
    LiveConnectorSettingsRefused,
    LiveConnectorSettingValues,
    LiveOptionsProjection,
)

_PUBLIC = TypeAdapter(dict[str, JsonValue])
_CONFIG_FIELDS = frozenset(
    {
        "session_max_minutes",
        "session_max_bounds",
        "idle_timeout_bounds",
        "session_budget_eur_max",
        "unlimited_value",
        "extension_minutes",
        "extension_prompt_seconds",
        "connect_window_seconds",
        "idle_timeout_seconds",
        "hidden_grace_seconds",
        "standby_max_seconds",
        "delegation_timeout_seconds",
        "delegation_result_max_tokens",
    }
)
_INTERNAL_CONFIG_FIELDS = frozenset(
    {
        "delegation_lines",
        "direct_lines",
        "tone_lines",
        "delegation_tool_name",
        "turn_text_max_chars",
    }
)


def assert_live_choice_projection_coverage() -> None:
    shapes = (
        (LiveConfigResponse, _CONFIG_FIELDS | _INTERNAL_CONFIG_FIELDS),
        (
            LiveModel,
            {
                "provider",
                "name",
                "label",
                "voice_model",
                "llm",
                "thinking_levels",
                "capabilities",
            },
        ),
        (LiveModelsResponse, {"models", "default_model", "unpriced"}),
        (LiveVoice, {"name", "characteristic"}),
        (
            LiveVoicesResponse,
            {"provider", "voices", "provenance", "published_at", "source"},
        ),
    )
    if any(set(model.model_fields) != fields for model, fields in shapes):
        raise AssertionError("New Live configuration or choices require explicit projection review")


def assert_live_connector_projection_coverage() -> None:
    assert_live_choice_projection_coverage()
    if set(LiveConnectorSettings.model_fields) != set(LiveConnectorSettingValues.model_fields):
        raise AssertionError("New Live settings require explicit projection review")
    if set(LiveModelSettings.model_fields) != set(LiveConnectorSettingValues.model_fields) - {
        "model",
        "session_budget_eur",
    }:
        raise AssertionError("New per-model Live settings require explicit projection review")
    if set(LiveConnectorResponse.model_fields) != {
        "provider",
        "connector_type",
        "status",
        "settings",
        "model_settings",
        "functionally_verified",
        "capabilities",
        "active",
    }:
        raise AssertionError("New Live connector card fields require explicit projection review")


assert_live_connector_projection_coverage()


def settings_for_native_change(
    connector: Connector, change: dict[str, JsonValue]
) -> LiveConnectorSettings:
    current = LiveConnectorService.connector_settings(connector)
    model = change.get("model", current.model)
    if not isinstance(model, str):
        raise ValueError("Live model must be a string")
    chosen = (
        LiveConnectorService.settings_for_model(connector, model)
        if model != current.model
        else current
    )
    desired = LiveConnectorSettings.model_validate({**chosen.model_dump(), **change})
    if desired.voice == "-":
        raise LiveConnectorSettingsRefused("INVALID_INPUT")
    return desired


async def current_live_owner(db: AsyncSession, actor_id: UUID) -> User:
    actor = await db.scalar(
        select(User).where(User.id == actor_id).execution_options(populate_existing=True)
    )
    if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    return actor


async def live_options_projection(
    service: LiveConnectorService,
    actor: User,
    section: str,
    provider: str | None,
    *,
    language: str,
) -> LiveOptionsProjection:
    if section == "voices":
        if not provider:
            raise ValueError("Choose a Live provider before listing voices")
        voices = await service.list_voices(actor, provider_id=provider, language=language)
        return LiveOptionsProjection(
            choices=[_PUBLIC.validate_python(row.model_dump(mode="json")) for row in voices.voices],
            details=_PUBLIC.validate_python(voices.model_dump(mode="json", exclude={"voices"})),
        )
    if section != "models":
        raise ValueError("Unknown Live choice section")
    models = await service.list_models(actor, language=language)
    return LiveOptionsProjection(
        choices=[
            _PUBLIC.validate_python({**row.model_dump(mode="json"), "selectable": True})
            for row in models.models
            if provider is None or row.provider == provider
        ]
        + [
            {"name": name, "selectable": False, "reason": "undeclared_tariff"}
            for name in dict.fromkeys(models.unpriced)
        ],
        details={
            "default_model": models.default_model,
            "unpriced_total": len(set(models.unpriced)),
            "unpriced_scope": "all_owned_providers",
            "source_scope": "application_live_catalogue",
        },
    )


class SavedLiveConnectorPreferences:
    async def options(
        self,
        db: AsyncSession,
        actor_id: UUID,
        section: str,
        provider: str | None,
        *,
        language: str,
    ) -> LiveOptionsProjection:
        actor = await current_live_owner(db, actor_id)
        try:
            return await live_options_projection(
                LiveConnectorService(db), actor, section, provider, language=language
            )
        except LiveRefusedError as exc:
            code = "NOT_FOUND" if exc.code == "connector_missing" else "EXTERNAL_API_ERROR"
            raise LiveConnectorSettingsRefused(code) from None
        except httpx.TimeoutException:
            raise LiveConnectorSettingsRefused("TIMEOUT") from None
        except httpx.HTTPStatusError as exc:
            code = (
                "RATE_LIMIT_EXCEEDED" if exc.response.status_code == 429 else "EXTERNAL_API_ERROR"
            )
            raise LiveConnectorSettingsRefused(code) from None
        except AuthorizationError, SQLAlchemyError, ValueError, TypeError:
            raise
        except Exception:
            # Vendor SDK diagnostics may contain URLs or credentials. Never project them.
            raise LiveConnectorSettingsRefused("EXTERNAL_API_ERROR") from None

    async def prepare(
        self,
        db: AsyncSession,
        actor_id: UUID,
        provider: str,
        change: dict[str, JsonValue],
    ) -> tuple[
        LiveConnectorPreferenceSnapshot,
        LiveConnectorSettingValues,
        LiveConnectorSettingValues,
    ]:
        actor = await current_live_owner(db, actor_id)
        service = LiveConnectorService(db)
        try:
            connector = await service.connector_of(
                actor, provider, language=normalize_language(actor.language)
            )
        except LiveRefusedError:
            raise LiveConnectorSettingsRefused("NOT_FOUND") from None
        before = LiveConnectorSettingValues.model_validate(
            service.connector_settings(connector).model_dump()
        )
        desired = LiveConnectorSettingValues.model_validate(
            settings_for_native_change(connector, change).model_dump()
        )
        return (
            connector_preference_snapshot(actor, connector, provider),
            before,
            desired,
        )

    async def read(self, db: AsyncSession, actor_id: UUID) -> LiveConnectorPreferenceProjection:
        actor = await current_live_owner(db, actor_id)
        saved = await LiveConnectorService(db).connectors_response(actor)
        return LiveConnectorPreferenceProjection(
            connectors=[
                _PUBLIC.validate_python(row.model_dump(mode="json")) for row in saved.connectors
            ],
            active_provider=saved.active_provider,
            configuration=_PUBLIC.validate_python(
                effective_live_configuration().model_dump(mode="json", include=set(_CONFIG_FIELDS))
            ),
        )

    async def write(
        self,
        db: AsyncSession,
        actor_id: UUID,
        provider: str,
        settings: dict[str, JsonValue],
        *,
        expected: LiveConnectorPreferenceSnapshot,
        receipt: PreferenceWriteReceipt,
        language: str,
    ) -> None:
        actor = await current_live_owner(db, actor_id)
        try:
            await LiveConnectorService(db).update_connector_settings(
                actor,
                provider,
                LiveConnectorSettings.model_validate(settings),
                language=language,
                expected=expected,
                receipt=receipt,
            )
        except LiveRefusedError as exc:
            code = "NOT_FOUND" if exc.code == "connector_missing" else "EXTERNAL_API_ERROR"
            raise LiveConnectorSettingsRefused(code) from None
