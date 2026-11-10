"""Database-backed Jev routing snapshots; a toggle never depends on cache delivery.

One read takes every switch and every stored threshold (ADR-374), and an operation keeps
what it read: a toggle or a threshold moved meanwhile reaches the next operation only.
"""

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import JEV_DEFAULT_TIMEOUT_SECONDS
from src.core.llm_config_helper import merge_config
from src.core.security.utils import decrypt_data
from src.domains.llm.models import LLMModel, LLMModelKindEnum, LLMProviderEnum
from src.domains.llm.pricing_service import AsyncPricingService, ModelPrice
from src.domains.llm_config.cache import OVERRIDE_FIELDS
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.llm_config.jev_gates import JEV_GATES, gate_defaults, threshold_refusal
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
    """An operation's engine choice and thresholds; a later change cannot mutate them."""

    requested: bool
    readiness: Readiness
    configuration: DecisionConfiguration | None = None
    thresholds: Mapping[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class JevRouting:
    """One database read of every switch and every stored threshold.

    Attributes:
        flags: ``"global"`` and each usage value → its switch.
        thresholds: Each usage value → its stored JSON, when a row exists.
    """

    flags: dict[str, bool]
    thresholds: dict[str, str]


class JevToggleUpdate(BaseModel):
    """One switch update, not a stale full replacement of everyone else's preferences."""

    model_config = ConfigDict(extra="forbid")
    usage: JevUsage | None = Field(default=None, description="Null selects the global switch.")
    enabled: bool = Field(strict=True, description="Requested switch state.")


async def read_routing(db: AsyncSession) -> JevRouting:
    """Read every switch and every stored threshold in ONE statement."""
    switches = {
        "global": SystemSettingKey.JEV_ENABLED,
        **{usage.value: spec.setting_key for usage, spec in JEV_USAGES.items()},
    }
    stored = {
        spec.thresholds_key: usage.value
        for usage, spec in JEV_USAGES.items()
        if spec.thresholds_key is not None
    }
    rows = (
        await db.execute(
            select(SystemSetting.key, SystemSetting.value).where(
                SystemSetting.key.in_([*switches.values(), *stored])
            )
        )
    ).all()
    values = {row.key: row.value for row in rows}
    return JevRouting(
        flags={name: decode_bool(values.get(key, "")) for name, key in switches.items()},
        thresholds={usage: values[key] for key, usage in stored.items() if key in values},
    )


async def read_flags(db: AsyncSession) -> dict[str, bool]:
    """Read global and per-usage preferences in one database snapshot."""
    return (await read_routing(db)).flags


def _stored_threshold(value: object) -> Decimal | None:
    """A JSON number or numeric string, exactly; anything else is no threshold."""
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def resolve_thresholds(usage: JevUsage, stored: str | None) -> dict[str, Decimal]:
    """The thresholds an operation of ``usage`` decides with.

    Every declared gate starts at its default; a stored value replaces it only when it
    names a declared gate and ``threshold_refusal`` admits it, the predicate the screen's
    write applies too. Anything else is logged and ignored, so a corrupt row can never
    loosen a gate.

    Args:
        usage: The usage whose gates are resolved.
        stored: The raw JSON object stored for it, or ``None``.

    Returns:
        Gate key → threshold, one entry per declared gate (none for an observer).
    """
    resolved = gate_defaults(usage)
    if not stored or not resolved:
        return resolved
    try:
        values = json.loads(stored)
    except ValueError:
        logger.warning("jev_threshold_ignored", usage=usage.value, reason="invalid_json")
        return resolved
    if not isinstance(values, dict):
        logger.warning("jev_threshold_ignored", usage=usage.value, reason="not_an_object")
        return resolved
    gates = {gate.key: gate for gate in JEV_GATES[usage]}
    for key, value in values.items():
        gate = gates.get(key)
        if gate is None:
            logger.warning("jev_threshold_ignored", usage=usage.value, reason="unknown_gate")
            continue
        threshold = _stored_threshold(value)
        refusal = "not_a_number" if threshold is None else threshold_refusal(gate, threshold)
        if threshold is None or refusal is not None:
            logger.warning("jev_threshold_ignored", usage=usage.value, key=key, reason=refusal)
            continue
        resolved[key] = threshold
    return resolved


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
    # The slot's timeout is the call's (the database first); no ceiling of the code's own.
    timeout = config.timeout_seconds or JEV_DEFAULT_TIMEOUT_SECONDS
    return "ready", DecisionConfiguration(config.model, timeout, SecretStr(secret), price)


async def load_jev_snapshot(usage: JevUsage) -> JevSnapshot:
    """Close the short database session before returning a call's fixed choice."""
    from src.infrastructure.database import get_db_context

    try:
        async with asyncio.timeout(CONFIGURATION_TIMEOUT_SECONDS), get_db_context() as db:
            routing = await read_routing(db)
            thresholds = resolve_thresholds(usage, routing.thresholds.get(usage.value))
            if not routing.flags["global"] or not routing.flags[usage.value]:
                return JevSnapshot(False, "ready", thresholds=thresholds)
            readiness, config = await read_configuration(db, usage)
            return JevSnapshot(True, readiness, config, thresholds)
    except Exception as exc:
        logger.warning("jev_configuration_unavailable", error_type=type(exc).__name__)
        return JevSnapshot(False, "unavailable")
