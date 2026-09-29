"""Administrator-facing Jev settings; persistence and audit use the common store."""

from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_structured_validation_error
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.domains.llm_config.jev_settings import (
    JevToggleUpdate,
    Readiness,
    read_configuration,
    read_flags,
)
from src.domains.system_settings.models import SystemSettingKey
from src.domains.system_settings.service import write_setting

if TYPE_CHECKING:
    from fastapi import Request


class JevUsageStatus(BaseModel):
    """A stored preference and its effective state are distinct."""

    usage: JevUsage = Field(description="Registered integration point.")
    label_key: str = Field(description="Frontend translation key.")
    llm_type: str = Field(description="Configuration slot.")
    enabled: bool = Field(description="Stored local preference.")
    effective: bool = Field(description="Global and local switches on, configuration ready.")
    readiness: Readiness = Field(description="Configuration readiness code.")


class JevSettingsResponse(BaseModel):
    """One consistent routing read, with configuration availability per usage."""

    enabled: bool = Field(description="Global switch.")
    usages: list[JevUsageStatus] = Field(description="Only shipped integration points.")


async def get_jev_settings(db: AsyncSession) -> JevSettingsResponse:
    """Read persisted preferences and readiness without revealing credentials."""
    flags = await read_flags(db)
    usages = []
    for usage, spec in JEV_USAGES.items():
        readiness, _ = await read_configuration(db, usage)
        usages.append(
            JevUsageStatus(
                usage=usage,
                label_key=spec.label_key,
                llm_type=spec.llm_type,
                enabled=flags[usage.value],
                effective=flags["global"] and flags[usage.value] and readiness == "ready",
                readiness=readiness,
            )
        )
    return JevSettingsResponse(enabled=flags["global"], usages=usages)


def _reject_activation(usage: JevUsage, readiness: Readiness) -> None:
    raise_structured_validation_error(
        error_type="jev_configuration_unavailable",
        loc=["body", "enabled"],
        msg="Configure the TypeSafe key, active decision model and tariff first.",
        input_value=True,
        ctx={"readiness": readiness, "usage": usage.value},
    )


async def _validate_activation(db: AsyncSession, selected: JevUsage | None) -> None:
    if selected is not None:
        targets = [selected]
    else:
        flags = await read_flags(db)
        targets = [usage for usage in JEV_USAGES if flags[usage.value]]
    if not targets:
        # A master switch with no local preferences may be prepared once at
        # least one usage is ready. Each local activation still validates itself.
        for usage in JEV_USAGES:
            readiness, _ = await read_configuration(db, usage)
            if readiness == "ready":
                return
        _reject_activation(usage, readiness)
    for usage in targets:
        readiness, _ = await read_configuration(db, usage)
        if readiness != "ready":
            _reject_activation(usage, readiness)


async def update_jev_setting(
    db: AsyncSession, update: JevToggleUpdate, *, admin_user_id: UUID, request: Request
) -> JevSettingsResponse:
    """Change one switch atomically; serialize first writers and preserve other switches."""
    # No Redis lock: the preference, previous value and audit share the transaction.
    await db.execute(text("SET LOCAL lock_timeout = '2s'"))
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('jev-routing', 0))"))
    if update.enabled:
        await _validate_activation(db, update.usage)
    key = JEV_USAGES[update.usage].setting_key if update.usage else SystemSettingKey.JEV_ENABLED
    await write_setting(
        db,
        key,
        update.enabled,
        action="jev_setting_updated",
        admin_user_id=admin_user_id,
        request=request,
        change_reason=None,
    )
    return await get_jev_settings(db)
