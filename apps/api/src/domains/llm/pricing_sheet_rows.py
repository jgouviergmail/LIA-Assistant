"""Turn the catalogue into the rows the workbook exports.

Three derived columns exist because the raw data alone misleads:

- ``time_slots_summary`` and ``time_slots_mode`` put the windowed tariff **on
  the row that carries the price**. Without them a DeepSeek row showed
  ``0.22 / 0.66`` — its off-peak base — and read as flat pricing, the windows
  living on another sheet nobody had reason to open.
- ``statut`` states what the runtime would really do: a model with no active
  tariff is billed zero in silence, and a dated model with no tariff of its own
  is billed under its base model.
- ``reasoning_shape`` keeps the file self-describing for the models the
  reasoning templates cannot express.

Fingerprints cover the **editable** columns only. A diagnostic recomputed
elsewhere must never make an untouched row look edited.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.llm_utils import resolve_priced_name
from src.domains.llm.models import LLMModel, LLMModelPricing
from src.domains.llm.pricing_sheet import (
    FINGERPRINT_COLUMN,
    MODELS_SHEET,
)

#: i18n keys this module resolves through the ``labels`` mapping. Published so
#: the route can hand over exactly what is needed, and a gap is findable.
EXPORT_LABEL_KEYS: tuple[str, ...] = (
    "settings.admin.llm.sheet.status.ok",
    "settings.admin.llm.sheet.status.no_pricing",
    "settings.admin.llm.sheet.status.multiple",
    "settings.admin.llm.sheet.status.shadowed",
    "settings.admin.llm.sheet.slots_summary",
    "settings.admin.llm.sheet.reasoning_prefix",
)

_SLOT_PRICE_KEYS: tuple[str, ...] = (
    "input_unit_price",
    "cached_input_unit_price",
    "output_unit_price",
)


@dataclass(frozen=True)
class ExportPayload:
    """Everything the writer needs, plus what the import will compare against.

    Attributes:
        models: One mapping per catalogue model, keyed by the sheet's columns.
        slots: One mapping per UTC window, for the time-slot sheet.
        fingerprints: Per-model hash of the editable values, so an import can
            refuse exactly the rows that changed underneath the administrator.
    """

    models: tuple[Mapping[str, Any], ...]
    slots: tuple[Mapping[str, Any], ...]
    fingerprints: Mapping[str, str]


def fingerprint_row(row: Mapping[str, Any]) -> str:
    """Hash the editable values of one exported row.

    Derived columns are excluded on purpose: a status recomputed because some
    *other* model changed must not make this row look edited.

    Args:
        row: An exported model row.

    Returns:
        A short, stable hexadecimal digest.
    """
    payload = {key: _canonical(row.get(key)) for key in sorted(MODELS_SHEET.editable_keys)}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _canonical(value: Any) -> Any:
    """Reduce a value to something JSON can hash identically every time."""
    if isinstance(value, Decimal):
        # Normalise so 0.40 and 0.4 hash the same: the workbook round-trips
        # through a float, and trailing zeros are not a change.
        return format(value.normalize(), "f")
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return str(value)


async def build_export_rows(db: AsyncSession, *, labels: Mapping[str, str]) -> ExportPayload:
    """Read the catalogue and shape it into workbook rows.

    Args:
        db: Active database session.
        labels: Translated strings for the derived columns, keyed by
            :data:`EXPORT_LABEL_KEYS`.

    Returns:
        The rows and the per-row fingerprints.
    """
    models = list((await db.scalars(select(LLMModel).order_by(LLMModel.model_name))).all())
    pricing_rows = list(
        (
            await db.scalars(
                select(LLMModelPricing)
                .options(selectinload(LLMModelPricing.model))
                .where(LLMModelPricing.is_active)
                .order_by(
                    LLMModelPricing.effective_from.desc(),
                    LLMModelPricing.id.desc(),
                )
            )
        ).all()
    )

    active_by_model: dict[Any, list[LLMModelPricing]] = {}
    for pricing in pricing_rows:
        active_by_model.setdefault(pricing.model_id, []).append(pricing)
    priced_names = {pricing.model.model_name for pricing in pricing_rows}

    rows: list[Mapping[str, Any]] = []
    slots: list[Mapping[str, Any]] = []
    fingerprints: dict[str, str] = {}

    for model in models:
        current = active_by_model.get(model.id, [])
        # The list is ordered most recent first; the head is the tariff that
        # applies. After migration 6e7f8a9b0c1d there can only ever be one.
        applied = current[0] if current else None
        row = _model_row(model, applied, current, priced_names, labels)
        # Stamped into the row itself so the file carries it back on import;
        # computed from the editable cells only, which is why the fingerprint
        # column is read-only and therefore never part of its own input.
        digest = fingerprint_row(row)
        row[FINGERPRINT_COLUMN] = digest
        rows.append(row)
        fingerprints[model.model_name] = digest
        slots.extend(_slot_rows(model.model_name, applied))

    return ExportPayload(
        models=tuple(rows),
        slots=tuple(slots),
        fingerprints=fingerprints,
    )


def _model_row(
    model: LLMModel,
    pricing: LLMModelPricing | None,
    active: Sequence[LLMModelPricing],
    priced_names: set[str],
    labels: Mapping[str, str],
) -> dict[str, Any]:
    windows = list(pricing.time_slots or []) if pricing else []
    return {
        "model_name": model.model_name,
        "provider": model.provider.value,
        "kind": model.kind.value,
        "is_active": model.is_active,
        "max_input_tokens": model.max_input_tokens,
        "max_output_tokens": model.max_output_tokens,
        "supports_tools": model.supports_tools,
        "supports_structured_output": model.supports_structured_output,
        "supports_strict_mode": model.supports_strict_mode,
        "supports_streaming": model.supports_streaming,
        "supports_vision": model.supports_vision,
        "supports_temperature": model.supports_temperature,
        "supports_top_p": model.supports_top_p,
        "supports_frequency_penalty": model.supports_frequency_penalty,
        "supports_presence_penalty": model.supports_presence_penalty,
        "is_reasoning_model": model.is_reasoning_model,
        # The stored narrowing, verbatim and comma-separated. Empty means "no
        # narrowing": the family's own ladder applies, which is what the
        # read-only shape beside it prints.
        "reasoning_enum_values": ", ".join(model.reasoning_enum_values or ()) or None,
        "reasoning_shape": _reasoning_shape(model, labels),
        "reasoning_doc_i18n_key": model.reasoning_doc_i18n_key,
        "pricing_unit": pricing.pricing_unit.value if pricing else None,
        "input_unit_price": pricing.input_unit_price if pricing else None,
        "cached_input_unit_price": pricing.cached_input_unit_price if pricing else None,
        "output_unit_price": pricing.output_unit_price if pricing else None,
        "effective_from": pricing.effective_from.isoformat() if pricing else None,
        "time_slots_mode": "windows" if windows else "flat",
        "time_slots_summary": _slots_summary(windows, labels),
        "statut": _status(model, active, priced_names, labels),
    }


def _slot_rows(model_name: str, pricing: LLMModelPricing | None) -> list[dict[str, Any]]:
    """Expand a model's windows into rows of the time-slot sheet."""
    if pricing is None or not pricing.time_slots:
        return []
    rows: list[dict[str, Any]] = []
    for window in pricing.time_slots:
        row: dict[str, Any] = {
            "model_name": model_name,
            "start_utc": window.get("start_utc"),
            "end_utc": window.get("end_utc"),
        }
        for key in _SLOT_PRICE_KEYS:
            raw = window.get(key)
            row[key] = None if raw is None else Decimal(str(raw))
        rows.append(row)
    return rows


def _slots_summary(windows: Sequence[Mapping[str, Any]], labels: Mapping[str, str]) -> str | None:
    """State the windowed tariff on the row that carries the price."""
    if not windows:
        return None
    listing = ", ".join(f"{w.get('start_utc')}-{w.get('end_utc')}" for w in windows)
    template = labels.get("settings.admin.llm.sheet.slots_summary", "{count}: {windows}")
    return template.format(count=len(windows), windows=listing)


def _reasoning_shape(model: LLMModel, labels: Mapping[str, str]) -> str:
    """A one-cell, human-readable summary of what the model does with reasoning.

    Since ADR-245 this prints what the RUNTIME resolves -- the translator family
    and the ladder it will accept -- rather than the catalogue's own
    ``reasoning_widget``, a column that has since been dropped along with the
    four stored shapes it discriminated. The declared narrowing is shown next
    to it when the row carries one: it is the single catalogue value the
    resolution still reads.
    """
    from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile

    declared = model.reasoning_enum_values
    profile = resolve_reasoning_profile(
        model.provider,
        model.model_name,
        model_levels=tuple(declared) if declared else None,
    )
    if not profile.levels:
        return profile.family
    parts = [profile.family, "[" + ",".join(profile.levels) + "]"]
    if profile.supports_budget and profile.budget_range is not None:
        parts.append(f"budget={profile.budget_range[0]}-{profile.budget_range[1]}")
    if not profile.can_disable:
        parts.append("always-on")
    if declared:
        parts.append("declared=[" + ",".join(declared) + "]")
    prefix = labels.get("settings.admin.llm.sheet.reasoning_prefix", "reasoning")
    return f"{prefix} / " + " ".join(parts)


def _status(
    model: LLMModel,
    active: Sequence[LLMModelPricing],
    priced_names: set[str],
    labels: Mapping[str, str],
) -> str:
    """Name what the runtime would really do with this model.

    Inheritance is checked **before** absence, and that order is load-bearing: a
    dated model with no tariff of its own is billed at its base model's rate,
    exactly as designed. Reporting it as "no active tariff" would raise a false
    alarm and send an administrator fixing something that is not broken —
    while a model with neither is genuinely billed zero in silence.
    """
    if len(active) > 1:
        template = labels.get("settings.admin.llm.sheet.status.multiple", "{count} active tariffs")
        return template.format(count=len(active))

    resolved = resolve_priced_name(model.model_name, priced_names.__contains__)
    if resolved and resolved != model.model_name:
        template = labels.get("settings.admin.llm.sheet.status.shadowed", "billed under {name}")
        return template.format(name=resolved)

    if not active:
        return labels.get("settings.admin.llm.sheet.status.no_pricing", "no active pricing")
    return labels.get("settings.admin.llm.sheet.status.ok", "ok")
