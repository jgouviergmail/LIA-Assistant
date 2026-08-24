"""Apply a change plan to the catalogue, all at once or not at all.

Everything a workbook import writes goes through :class:`LLMModelService`, never
around it: the reasoning-shape cohesion checks, the temporal versioning of
tariffs and the time-slot contract are all enforced there, and an import that
took a shortcut would be an import that quietly breaks invariants the admin UI
respects.

Two guarantees:

- **all or nothing.** A plan carrying any issue is refused outright, and the
  caller owns a single transaction, so a failure halfway leaves no half-applied
  tariff table — nobody can tell which half of one took.
- **silence is written as silence.** Rows the plan marked unchanged produce no
  statement at all. Without that, importing 124 rows would leave 124 useless
  tariff versions and make the cost history unreadable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.pricing_change_plan import ChangeAction, ChangePlan, ModelChange
from src.domains.llm.pricing_time_slots import TimeSlotPrice
from src.domains.llm.schemas import ModelPriceCreate, ModelPriceUpdate
from src.domains.llm.service import LLMModelService
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.tabular_io.report import ParsedRow

logger = get_logger(__name__)

#: Capability columns the sheet may update in place.
_CAPABILITY_KEYS: tuple[str, ...] = (
    "kind",
    "max_input_tokens",
    "max_output_tokens",
    "supports_tools",
    "supports_structured_output",
    "supports_strict_mode",
    "supports_streaming",
    "supports_vision",
    "supports_temperature",
    "supports_top_p",
    "supports_frequency_penalty",
    "supports_presence_penalty",
    "reasoning_doc_i18n_key",
)


def _ladder(raw: object) -> list[str] | None:
    """Parse the ladder cell into the stored narrowing, or None for "no narrowing".

    An empty cell and a cell holding every level of the family mean the same
    thing to ``resolve_reasoning_profile``; the empty one is stored because it
    survives the family gaining a depth. The values themselves were already
    checked against the family by the change plan.

    Args:
        raw: The cell value, comma-separated or absent.

    Returns:
        The declared levels, or ``None`` when nothing is narrowed.
    """
    if not raw:
        return None
    levels = [part.strip() for part in str(raw).split(",") if part.strip()]
    return levels or None


#: Pricing columns carried straight to the tariff row.
_PRICING_KEYS: tuple[str, ...] = (
    "pricing_unit",
    "input_unit_price",
    "cached_input_unit_price",
    "output_unit_price",
)


@dataclass(frozen=True)
class ImportOutcome:
    """What an application actually did — named, never merely counted."""

    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    deactivated: tuple[str, ...] = ()
    reactivated: tuple[str, ...] = ()
    unchanged: int = 0

    @property
    def total_touched(self) -> int:
        """How many models were written to."""
        return len(self.created) + len(self.updated) + len(self.deactivated) + len(self.reactivated)


class PricingImportService:
    """Write a reviewed plan into the catalogue.

    The caller owns the transaction: this service flushes but never commits, so
    the route can log the audit entry and invalidate the caches inside the same
    unit of work as the data it describes.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.models = LLMModelService(db)

    async def apply(
        self,
        plan: ChangePlan,
        *,
        sheet_rows: Sequence[ParsedRow],
        sheet_slots: Sequence[ParsedRow] = (),
    ) -> ImportOutcome:
        """Apply every change of ``plan``.

        Args:
            plan: The reviewed plan. Must be applicable.
            sheet_rows: The parsed rows the plan was built from — they carry the
                typed values; the plan only carries their rendered form.
            sheet_slots: The parsed time-slot rows.

        Returns:
            What was done, model by model.

        Raises:
            ValueError: when the plan carries any issue. An import is
                all-or-nothing, so a plan that cannot be applied entirely is
                not applied at all.
        """
        if not plan.is_applicable:
            raise ValueError(
                f"plan carries {len(plan.issues)} unresolved issue(s) and cannot be applied"
            )

        values_by_model = {row.key: row.values for row in sheet_rows if row.key}
        slots_by_model: dict[str, list[ParsedRow]] = {}
        for slot in sheet_slots:
            if slot.key:
                slots_by_model.setdefault(slot.key, []).append(slot)

        created: list[str] = []
        updated: list[str] = []
        deactivated: list[str] = []
        reactivated: list[str] = []
        unchanged = 0

        for change in plan.changes:
            values = values_by_model.get(change.model_name, {})
            windows = slots_by_model.get(change.model_name, [])

            if change.action is ChangeAction.UNCHANGED:
                unchanged += 1
                continue
            if change.action is ChangeAction.CREATE:
                await self.models.create(_build_create(values, windows))
                created.append(change.model_name)
                continue
            if change.action is ChangeAction.REACTIVATE:
                await self.models.reactivate(change.model_name)
                reactivated.append(change.model_name)
                await self._apply_update(change, values, windows)
                continue
            if change.action is ChangeAction.DEACTIVATE:
                # Apply the row's other edits BEFORE switching the model off:
                # the update path needs an active tariff row to supersede.
                await self._apply_update(change, values, windows)
                await self.models.deactivate(change.model_name)
                deactivated.append(change.model_name)
                continue

            await self._apply_update(change, values, windows)
            updated.append(change.model_name)

        outcome = ImportOutcome(
            created=tuple(created),
            updated=tuple(updated),
            deactivated=tuple(deactivated),
            reactivated=tuple(reactivated),
            unchanged=unchanged,
        )
        logger.info(
            "llm_pricing_import_applied",
            created=len(outcome.created),
            updated=len(outcome.updated),
            deactivated=len(outcome.deactivated),
            reactivated=len(outcome.reactivated),
            unchanged=outcome.unchanged,
        )
        return outcome

    async def _apply_update(
        self,
        change: ModelChange,
        values: Mapping[str, Any],
        windows: Sequence[ParsedRow],
    ) -> None:
        """Send one model's edits through the service, or nothing at all."""
        payload = _build_update(change, values, windows)
        if payload is None:
            return
        await self.models.update(change.model_name, payload)


def _build_create(values: Mapping[str, Any], windows: Sequence[ParsedRow]) -> ModelPriceCreate:
    """Turn a new row into a creation payload.

    The reasoning identity comes from the two columns the runtime reads. It
    used to go through a ``reasoning_template`` dropdown, which also meant a
    model that does not reason could not be created without picking one.
    """
    fields: dict[str, Any] = {
        "provider": values.get("provider"),
        "model_name": values.get("model_name"),
        "is_reasoning_model": bool(values.get("is_reasoning_model")),
        "reasoning_enum_values": _ladder(values.get("reasoning_enum_values")),
        "time_slots": _windows_payload(values, windows),
    }
    for key in (*_CAPABILITY_KEYS, *_PRICING_KEYS):
        if values.get(key) is not None:
            fields[key] = values[key]
    return ModelPriceCreate(**fields)


def _build_update(
    change: ModelChange,
    values: Mapping[str, Any],
    windows: Sequence[ParsedRow],
) -> ModelPriceUpdate | None:
    """Turn one model's field changes into an update payload, or ``None``.

    Only the fields the plan flagged are sent: an update carrying the whole row
    would supersede a tariff whose price never moved.
    """
    changed = {field.field for field in change.fields}
    payload: dict[str, Any] = {
        key: values[key] for key in changed if key in values and values[key] is not None
    }

    # The ladder cell is text; the column is a list. And an EMPTIED cell means
    # "stop narrowing", which a null cannot say — the service builds its
    # change-set with exclude_none, so the previous restriction would survive
    # (same trap as the cached price just below).
    if "reasoning_enum_values" in changed:
        ladder = _ladder(values.get("reasoning_enum_values"))
        payload.pop("reasoning_enum_values", None)
        if ladder is None:
            payload["clear_reasoning_enum_values"] = True
        else:
            payload["reasoning_enum_values"] = ladder

    # An emptied cached price cannot travel as None — the service's change-set
    # drops nulls — so the intent takes the shape the schema reserves for it.
    if "cached_input_unit_price" in changed and values.get("cached_input_unit_price") is None:
        payload["clear_cached_input_price"] = True

    if change.slots_before != change.slots_after or (
        values.get("time_slots_mode") == "windows" and change.action is not ChangeAction.UNCHANGED
    ):
        payload["time_slots"] = _windows_payload(values, windows)

    if not payload:
        return None
    return ModelPriceUpdate(**payload)


def _windows_payload(
    values: Mapping[str, Any], windows: Sequence[ParsedRow]
) -> list[TimeSlotPrice] | None:
    """Render the time-slot rows for the mode the sheet declares.

    ``inherit`` returns ``None`` so the service keeps the stored windows;
    ``flat`` returns ``[]``, the clearing sentinel ADR-223 reserves — a null
    would be swallowed by the service's change-set and change nothing.
    """
    mode = values.get("time_slots_mode")
    if mode == "inherit" or mode is None:
        return None
    if mode == "flat":
        return []
    return [
        TimeSlotPrice(
            start_utc=str(window.values.get("start_utc")),
            end_utc=str(window.values.get("end_utc")),
            input_unit_price=_decimal(window.values.get("input_unit_price")),
            cached_input_unit_price=(
                None
                if window.values.get("cached_input_unit_price") is None
                else _decimal(window.values.get("cached_input_unit_price"))
            ),
            output_unit_price=_decimal(window.values.get("output_unit_price")),
        )
        for window in windows
    ]


def _decimal(value: Any) -> Decimal:
    """Coerce a parsed cell to the Decimal the schema expects."""
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))
