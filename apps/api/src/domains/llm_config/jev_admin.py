"""Administrator-facing Jev settings; persistence and audit use the common store."""

import json
from decimal import Decimal
from typing import TYPE_CHECKING, NoReturn
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_structured_validation_error
from src.domains.llm_config.jev_gates import (
    JEV_GATES,
    GateKind,
    GateScope,
    gate_defaults,
    threshold_refusal,
)
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.domains.llm_config.jev_settings import (
    JevToggleUpdate,
    Readiness,
    read_configuration,
    read_flags,
    read_routing,
    resolve_thresholds,
)
from src.domains.system_settings.models import SystemSettingKey
from src.domains.system_settings.service import write_setting

if TYPE_CHECKING:
    from fastapi import Request


class JevGateStatus(BaseModel):
    """One threshold of a usage: what it is, where it may move, where it stands."""

    key: str = Field(description="Gate key within its usage.")
    kind: GateKind = Field(description="What the score is.")
    scope: GateScope = Field(description="Each answer alone, or every answer of the call.")
    default: float = Field(description="The shipped, qualified value.")
    minimum: float = Field(description="Lowest value accepted.")
    maximum: float = Field(description="Highest value accepted.")
    value: float = Field(description="The threshold the next operation decides with.")


class JevUsageStatus(BaseModel):
    """A stored preference and its effective state are distinct."""

    usage: JevUsage = Field(description="Registered integration point.")
    label_key: str = Field(description="Frontend translation key.")
    llm_type: str = Field(description="Configuration slot.")
    enabled: bool = Field(description="Stored local preference.")
    effective: bool = Field(description="Global and local switches on, configuration ready.")
    readiness: Readiness = Field(description="Configuration readiness code.")
    gates: list[JevGateStatus] = Field(
        default_factory=list, description="This usage's thresholds; none for an observer."
    )
    qualified: bool = Field(
        default=True, description="Every threshold equals the value its record qualified."
    )


class JevSettingsResponse(BaseModel):
    """One consistent routing read, with configuration availability per usage."""

    enabled: bool = Field(description="Global switch.")
    usages: list[JevUsageStatus] = Field(description="Only shipped integration points.")


class JevThresholdUpdate(BaseModel):
    """New values for some gates of one usage; a gate left out keeps its value."""

    model_config = ConfigDict(extra="forbid")
    usage: JevUsage = Field(description="The usage whose gates move.")
    values: dict[str, Decimal] = Field(
        min_length=1, max_length=8, description="Gate key → threshold, at the hundredth."
    )


def _gate_statuses(usage: JevUsage, stored: str | None) -> list[JevGateStatus]:
    values = resolve_thresholds(usage, stored)
    return [
        JevGateStatus(
            key=gate.key,
            kind=gate.kind,
            scope=gate.scope,
            default=float(gate.default),
            minimum=float(gate.minimum),
            maximum=float(gate.maximum),
            value=float(values[gate.key]),
        )
        for gate in JEV_GATES.get(usage, ())
    ]


async def get_jev_settings(db: AsyncSession) -> JevSettingsResponse:
    """Read persisted preferences, thresholds and readiness without revealing credentials."""
    routing = await read_routing(db)
    flags = routing.flags
    usages = []
    for usage, spec in JEV_USAGES.items():
        readiness, _ = await read_configuration(db, usage)
        gates = _gate_statuses(usage, routing.thresholds.get(usage.value))
        usages.append(
            JevUsageStatus(
                usage=usage,
                label_key=spec.label_key,
                llm_type=spec.llm_type,
                enabled=flags[usage.value],
                effective=flags["global"] and flags[usage.value] and readiness == "ready",
                readiness=readiness,
                gates=gates,
                qualified=all(gate.value == gate.default for gate in gates),
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


async def _serialize_routing_writes(db: AsyncSession) -> None:
    """Switches and thresholds share one lock: no Redis, the audit joins the transaction."""
    await db.execute(text("SET LOCAL lock_timeout = '2s'"))
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('jev-routing', 0))"))


async def update_jev_setting(
    db: AsyncSession, update: JevToggleUpdate, *, admin_user_id: UUID, request: Request
) -> JevSettingsResponse:
    """Change one switch atomically; serialize first writers and preserve other switches."""
    await _serialize_routing_writes(db)
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


def _reject_threshold(update: JevThresholdUpdate, key: str, reason: str) -> NoReturn:
    raise_structured_validation_error(
        error_type="jev_threshold_invalid",
        loc=["body", "values", key],
        msg="A threshold must name a declared gate and stay within its bounds, at the hundredth.",
        input_value=str(update.values.get(key)),
        ctx={"usage": update.usage.value, "reason": reason},
    )


def _validated(update: JevThresholdUpdate) -> None:
    """Refuse the whole update on the first unusable value: nothing is written."""
    gates = {gate.key: gate for gate in JEV_GATES.get(update.usage, ())}
    if not gates:
        _reject_threshold(update, next(iter(update.values)), "no_gate")
    for key, value in update.values.items():
        gate = gates.get(key)
        if gate is None:
            _reject_threshold(update, key, "unknown_gate")
        refusal = threshold_refusal(gate, value)
        if refusal is not None:
            _reject_threshold(update, key, refusal)


async def update_jev_thresholds(
    db: AsyncSession, update: JevThresholdUpdate, *, admin_user_id: UUID, request: Request
) -> JevSettingsResponse:
    """Move some gates of one usage; a gate set back to its default is no longer stored.

    Serialized with the switches, audited by ``write_setting``. Only values that differ
    from their default are stored, so « qualified » reads straight from the row.
    """
    _validated(update)
    await _serialize_routing_writes(db)
    thresholds_key = JEV_USAGES[update.usage].thresholds_key
    if thresholds_key is None:
        _reject_threshold(update, next(iter(update.values)), "no_gate")
    routing = await read_routing(db)
    current = resolve_thresholds(update.usage, routing.thresholds.get(update.usage.value))
    merged = {**current, **update.values}
    defaults = gate_defaults(update.usage)
    stored = {
        key: f"{value:.2f}" for key, value in sorted(merged.items()) if value != defaults[key]
    }
    await write_setting(
        db,
        thresholds_key,
        json.dumps(stored, separators=(",", ":")),
        action="jev_thresholds_updated",
        admin_user_id=admin_user_id,
        request=request,
        change_reason=None,
    )
    return await get_jev_settings(db)
