"""Database-backed Jev routing snapshots; a toggle never depends on cache delivery."""

import asyncio
from dataclasses import dataclass, field
from typing import Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.llm_config_helper import merge_config
from src.core.security.utils import decrypt_data
from src.domains.llm.models import LLMModel, LLMModelKindEnum, LLMProviderEnum
from src.domains.llm.pricing_service import AsyncPricingService, ModelPrice
from src.domains.llm_config.cache import OVERRIDE_FIELDS
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.domains.llm_config.models import LLMConfigOverride, ProviderApiKey
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.system_settings.registry import decode_bool

logger = structlog.get_logger(__name__)
CONFIGURATION_TIMEOUT_SECONDS = 1.0

Readiness = Literal["ready", "missing_key", "unavailable_model", "missing_price", "unavailable"]


@dataclass(frozen=True)
class DecisionConfiguration:
    """A native call's immutable configuration, with a redacted credential."""

    model: str
    timeout_seconds: float
    api_key: SecretStr = field(repr=False)
    price: ModelPrice


@dataclass(frozen=True)
class JevSnapshot:
    """An operation's engine choice; a subsequent toggle cannot mutate it."""

    requested: bool
    readiness: Readiness
    configuration: DecisionConfiguration | None = None


class JevToggleUpdate(BaseModel):
    """One switch update, not a stale full replacement of everyone else's preferences."""

    model_config = ConfigDict(extra="forbid")
    usage: JevUsage | None = Field(default=None, description="Null selects the global switch.")
    enabled: bool = Field(strict=True, description="Requested switch state.")


async def read_flags(db: AsyncSession) -> dict[str, bool]:
    """Read global and per-usage preferences in one database snapshot."""
    keys = {
        "global": SystemSettingKey.JEV_ENABLED,
        **{usage.value: spec.setting_key for usage, spec in JEV_USAGES.items()},
    }
    rows = (
        await db.execute(
            select(SystemSetting.key, SystemSetting.value).where(
                SystemSetting.key.in_(keys.values())
            )
        )
    ).all()
    values = {row.key: decode_bool(row.value) for row in rows}
    return {name: values.get(key, False) for name, key in keys.items()}


async def read_configuration(
    db: AsyncSession, usage: JevUsage
) -> tuple[Readiness, DecisionConfiguration | None]:
    """Resolve the saved slot, catalogue, tariff and encrypted key."""
    slot = JEV_USAGES[usage].llm_type
    override = await db.scalar(select(LLMConfigOverride).where(LLMConfigOverride.llm_type == slot))
    config = merge_config(
        LLM_DEFAULTS[slot],
        {key: getattr(override, key) for key in OVERRIDE_FIELDS} if override else {},
    )
    if config.provider != "typesafe":
        return "unavailable_model", None
    key = await db.scalar(select(ProviderApiKey).where(ProviderApiKey.provider == config.provider))
    if key is None:
        return "missing_key", None
    try:
        secret = decrypt_data(key.encrypted_key)
    except ValueError:
        return "missing_key", None
    if not secret.strip():
        return "missing_key", None
    model = await db.scalar(
        select(LLMModel).where(
            LLMModel.model_name == config.model,
            LLMModel.provider == LLMProviderEnum.typesafe,
            LLMModel.kind == LLMModelKindEnum.decision,
            LLMModel.is_active,
        )
    )
    if model is None:
        return "unavailable_model", None
    price = await AsyncPricingService(db).get_active_model_price(config.model)
    if price is None or price.pricing_unit != "per_1m_tokens":
        return "missing_price", None
    return "ready", DecisionConfiguration(
        config.model, min(config.timeout_seconds or 2.0, 5.0), SecretStr(secret), price
    )


async def load_jev_snapshot(usage: JevUsage) -> JevSnapshot:
    """Close the short database session before returning a call's fixed choice."""
    from src.infrastructure.database import get_db_context

    try:
        async with asyncio.timeout(CONFIGURATION_TIMEOUT_SECONDS), get_db_context() as db:
            flags = await read_flags(db)
            if not flags["global"] or not flags[usage.value]:
                return JevSnapshot(False, "ready")
            readiness, config = await read_configuration(db, usage)
            return JevSnapshot(True, readiness, config)
    except Exception as exc:
        logger.warning("jev_configuration_unavailable", error_type=type(exc).__name__)
        return JevSnapshot(False, "unavailable")
