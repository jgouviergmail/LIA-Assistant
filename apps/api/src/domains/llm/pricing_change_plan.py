"""Compare a parsed workbook against the catalogue and describe what would change.

This module decides nothing about *how* to write; it says what an import would
do, field by field, so the administrator can see it before anything happens.
Two properties make it trustworthy, both verified on the real 124-model
catalogue:

- an untouched export produces **no change at all** — otherwise every import
  would create a useless tariff version per row and the preview would drown in
  noise;
- an edited file produces **exactly** the edits, correctly classified.

Three rules protect the administrator from their own tooling:

- a row absent from the file changes nothing. A forgotten Excel filter must
  never empty a catalogue.
- a change the service cannot express (a provider swap) is reported, never
  dropped in silence.
- a row edited by somebody else since the export is refused **on its own**; a
  colleague touching one unrelated model must not reject a whole file.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from src.domains.llm.pricing_sheet import FINGERPRINT_COLUMN, MODELS_SHEET
from src.infrastructure.tabular_io.report import CellIssue, IssueCode, ParsedRow

#: Fields whose change means a new tariff version rather than an in-place edit.
PRICING_FIELDS: frozenset[str] = frozenset(
    {
        "pricing_unit",
        "input_unit_price",
        "cached_input_unit_price",
        "output_unit_price",
    }
)

#: Never compared as a value: they drive the lifecycle or the windows instead.
_NON_FIELD_KEYS: frozenset[str] = frozenset(
    {"model_name", "is_active", "time_slots_mode", FINGERPRINT_COLUMN}
)

#: The service cannot change a model's provider once it exists.
_IMMUTABLE_ON_UPDATE: frozenset[str] = frozenset({"provider"})

#: What a brand-new model cannot be built without. An update may be as sparse as
#: one cell, but a creation has to yield a complete row of two tables.
_REQUIRED_TO_CREATE: tuple[str, ...] = (
    "provider",
    "kind",
    "max_input_tokens",
    "max_output_tokens",
    "pricing_unit",
    "input_unit_price",
    "output_unit_price",
)


class ChangeAction(str, Enum):
    """What an import would do with one row."""

    CREATE = "create"
    UPDATE = "update"
    DEACTIVATE = "deactivate"
    REACTIVATE = "reactivate"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class FieldChange:
    """One field moving, rendered as text so a preview can show it verbatim."""

    field: str
    before: str | None
    after: str | None


@dataclass(frozen=True)
class ModelChange:
    """What would happen to one model."""

    model_name: str
    action: ChangeAction
    fields: tuple[FieldChange, ...] = ()
    slots_before: int = 0
    slots_after: int = 0
    row_number: int | None = None


@dataclass(frozen=True)
class ChangePlan:
    """The whole diff: what would change, and what forbids applying it."""

    changes: tuple[ModelChange, ...]
    issues: tuple[CellIssue, ...] = ()
    _counts: dict[ChangeAction, int] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        counts = dict.fromkeys(ChangeAction, 0)
        for change in self.changes:
            counts[change.action] += 1
        object.__setattr__(self, "_counts", counts)

    @property
    def counts(self) -> Mapping[ChangeAction, int]:
        """How many rows fall in each category, for the preview's summary."""
        return self._counts

    @property
    def pricing_changes(self) -> tuple[str, ...]:
        """Models whose tariff would be superseded by a new version."""
        return tuple(
            change.model_name
            for change in self.changes
            if change.action is not ChangeAction.UNCHANGED
            and (
                any(f.field in PRICING_FIELDS for f in change.fields)
                or change.slots_before != change.slots_after
            )
        )

    @property
    def is_applicable(self) -> bool:
        """An import is all-or-nothing: any issue forbids writing anything."""
        return not self.issues

    def fingerprint(self) -> str:
        """Hash the plan itself.

        The preview is only binding if applying re-derives the *same* plan. The
        route compares this value; a mismatch means the world moved between the
        two calls and the administrator must look again.
        """
        payload = [
            {
                "model": change.model_name,
                "action": change.action.value,
                "fields": [[f.field, f.before, f.after] for f in change.fields],
                "slots": [change.slots_before, change.slots_after],
            }
            for change in self.changes
            if change.action is not ChangeAction.UNCHANGED
        ]
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def build_change_plan(
    *,
    db_rows: Sequence[Mapping[str, Any]],
    sheet_rows: Sequence[ParsedRow],
    sheet_slots: Sequence[ParsedRow] = (),
    db_slots: Sequence[ParsedRow] = (),
) -> ChangePlan:
    """Diff a parsed workbook against the catalogue.

    Args:
        db_rows: Current state, as produced by
            :func:`~src.domains.llm.pricing_sheet_rows.build_export_rows`.
        sheet_rows: Rows parsed from the models sheet.
        sheet_slots: Windows read from the workbook's time-slot sheet.
        db_slots: Windows currently stored, in the same shape. Without them a
            windowed model would look edited on every import merely for
            declaring that it has windows — measured on the real catalogue,
            where two models had their tariff superseded for nothing.

    Returns:
        The plan, including every reason it may not be applied.
    """
    current = {str(row["model_name"]): row for row in db_rows}
    slots_by_model = _group_slots(sheet_slots)
    current_slots = _group_slots(db_slots)

    changes: list[ModelChange] = []
    issues: list[CellIssue] = []

    for row in sheet_rows:
        if not row.key:
            continue
        existing = current.get(row.key)
        _check_reasoning_ladder(row, issues)
        if existing is None:
            _check_creatable(row, issues)
            changes.append(
                ModelChange(
                    model_name=row.key,
                    action=ChangeAction.CREATE,
                    fields=_creation_fields(row),
                    slots_after=len(slots_by_model.get(row.key, [])),
                    row_number=row.row_number,
                )
            )
            continue

        _check_freshness(row, existing, issues)
        _check_immutables(row, existing, issues)
        changes.append(_update_change(row, existing, slots_by_model, current_slots))

    return ChangePlan(changes=tuple(changes), issues=tuple(issues))


def _check_reasoning_ladder(row: ParsedRow, issues: list[CellIssue]) -> None:
    """Refuse a depth the model's family does not offer, and name the ones it does.

    ``reasoning_enum_values`` can only NARROW the ladder the runtime derives
    from (provider, model): a level outside it is dropped by the narrowing
    intersection, in silence. Four catalogue rows once declared ``off`` that
    way and the resulting ladder had no off switch at all.

    The admin form makes this unrepresentable by rendering the family's ladder
    as checkboxes. A spreadsheet cell cannot, so the equivalent guarantee is an
    import that refuses the value and says what would have been accepted --
    ADR-184's rule again: whatever a validator can reject, its producer must be
    able to read.

    Args:
        row: One parsed row of the models sheet.
        issues: Accumulator, appended in place.
    """
    from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile

    raw = row.values.get("reasoning_enum_values")
    if not raw:
        return
    declared = [part.strip() for part in str(raw).split(",") if part.strip()]
    if not declared:
        return

    provider = str(row.values.get("provider") or "")
    profile = resolve_reasoning_profile(provider, row.key or "")
    if not profile.levels:
        # No rule matches this model, so the column is never read: the value is
        # inert rather than wrong, and the read-only ``reasoning_shape`` cell
        # beside it already says the model does no reasoning. Refusing here
        # would invent a constraint the runtime does not apply.
        return
    unknown = [level for level in declared if level not in profile.levels]
    if not unknown:
        return

    issues.append(
        CellIssue(
            IssueCode.REASONING_LEVEL_UNKNOWN,
            sheet=MODELS_SHEET.name,
            column="reasoning_enum_values",
            params={
                "key": row.key or "",
                "row": str(row.row_number),
                "levels": ", ".join(unknown),
                # Empty when no rule matches the model: the column would not be
                # read at all, and saying so is more useful than an empty list.
                "accepted": ", ".join(profile.levels),
            },
        )
    )


def _check_creatable(row: ParsedRow, issues: list[CellIssue]) -> None:
    """Refuse a new row that could not become a model, before anything is written.

    Every missing field is named, not just the first: fixing them one import at
    a time is how a five-minute correction becomes an afternoon.
    """
    for field_name in _REQUIRED_TO_CREATE:
        if row.values.get(field_name) is None:
            issues.append(
                CellIssue(
                    IssueCode.CREATION_FIELD_MISSING,
                    sheet=MODELS_SHEET.name,
                    column=field_name,
                    params={
                        "key": row.key or "",
                        "row": str(row.row_number),
                        "field": field_name,
                    },
                )
            )


def _creation_fields(row: ParsedRow) -> tuple[FieldChange, ...]:
    """Every supplied value of a new model, as an all-new field list."""
    return tuple(
        FieldChange(field=key, before=None, after=_render(row.values.get(key)))
        for key in MODELS_SHEET.editable_keys
        if key not in _NON_FIELD_KEYS and row.values.get(key) is not None
    )


def _check_freshness(row: ParsedRow, existing: Mapping[str, Any], issues: list[CellIssue]) -> None:
    """Refuse a row whose state moved since the file was exported.

    The stamp is *checked, not required*: a workbook rebuilt by hand carries
    none, and refusing it would punish a legitimate use.
    """
    stamped = row.derived.get(FINGERPRINT_COLUMN)
    if not stamped:
        return
    if str(stamped) != str(existing.get(FINGERPRINT_COLUMN, "")):
        issues.append(
            CellIssue(
                IssueCode.ROW_CHANGED_SINCE_EXPORT,
                sheet=MODELS_SHEET.name,
                column=MODELS_SHEET.key_column,
                params={"key": row.key or "", "row": str(row.row_number)},
            )
        )


def _check_immutables(row: ParsedRow, existing: Mapping[str, Any], issues: list[CellIssue]) -> None:
    """Report a change the write path cannot express, rather than dropping it."""
    for key in _IMMUTABLE_ON_UPDATE:
        supplied = row.values.get(key)
        if supplied is not None and supplied != existing.get(key):
            issues.append(
                CellIssue(
                    IssueCode.PROVIDER_IMMUTABLE,
                    sheet=MODELS_SHEET.name,
                    column=key,
                    params={
                        "key": row.key or "",
                        "before": _render(existing.get(key)) or "",
                        "after": _render(supplied) or "",
                    },
                )
            )


def _group_slots(slots: Sequence[ParsedRow]) -> dict[str, list[ParsedRow]]:
    """Index time-slot rows by the model they belong to."""
    grouped: dict[str, list[ParsedRow]] = {}
    for slot in slots:
        if slot.key:
            grouped.setdefault(slot.key, []).append(slot)
    return grouped


def _window_signature(slots: Sequence[ParsedRow]) -> tuple[tuple[str | None, ...], ...]:
    """Canonical, order-independent view of a model's windows.

    Resolution never depends on order (ADR-223), so a reordering is not an
    edit either — comparing sorted signatures keeps the diff honest.
    """
    return tuple(
        sorted(
            tuple(
                _render(slot.values.get(key))
                for key in (
                    "start_utc",
                    "end_utc",
                    "input_unit_price",
                    "cached_input_unit_price",
                    "output_unit_price",
                )
            )
            for slot in slots
        )
    )


def _update_change(
    row: ParsedRow,
    existing: Mapping[str, Any],
    slots_by_model: Mapping[str, Sequence[ParsedRow]],
    current_slots: Mapping[str, Sequence[ParsedRow]],
) -> ModelChange:
    fields = tuple(
        FieldChange(
            field=key,
            before=_render(existing.get(key)),
            after=_render(row.values.get(key)),
        )
        for key in MODELS_SHEET.editable_keys
        if key not in _NON_FIELD_KEYS and _differs(existing.get(key), row.values.get(key), key)
    )

    stored = current_slots.get(row.key or "", ())
    slots_before = (
        len(stored) if stored else (1 if existing.get("time_slots_mode") == "windows" else 0)
    )
    slots_after, slots_touched = _resolve_slots(row, existing, slots_by_model, stored)

    action = _resolve_action(row, existing, fields, slots_touched)
    return ModelChange(
        model_name=row.key or "",
        action=action,
        fields=fields,
        slots_before=slots_before,
        slots_after=slots_after,
        row_number=row.row_number,
    )


def _resolve_slots(
    row: ParsedRow,
    existing: Mapping[str, Any],
    slots_by_model: Mapping[str, Sequence[ParsedRow]],
    stored: Sequence[ParsedRow],
) -> tuple[int, bool]:
    """Apply the three time-slot modes (ADR-223 contract).

    ``windows`` counts as a rewrite only when the supplied windows actually
    differ from the stored ones. Treating the mere declaration as a change made
    every windowed model look edited on a re-imported, untouched export.

    Returns:
        The resulting window count, and whether the windows would be rewritten.
    """
    mode = row.values.get("time_slots_mode")
    had_windows = bool(stored) or existing.get("time_slots_mode") == "windows"

    if mode == "inherit" or mode is None:
        return len(stored) if stored else (1 if had_windows else 0), False
    if mode == "flat":
        return 0, had_windows
    supplied = slots_by_model.get(row.key or "", ())
    return len(supplied), _window_signature(supplied) != _window_signature(stored)


def _resolve_action(
    row: ParsedRow,
    existing: Mapping[str, Any],
    fields: Sequence[FieldChange],
    slots_touched: bool,
) -> ChangeAction:
    """Name the row's primary intent.

    A lifecycle transition wins over an ordinary edit: an administrator turning
    a model off wants to read "deactivated", not "updated", even when they
    changed a price in the same pass. The field list still carries everything.
    """
    was_active = bool(existing.get("is_active"))
    now_active = row.values.get("is_active")

    if now_active is not None and bool(now_active) != was_active:
        return ChangeAction.REACTIVATE if now_active else ChangeAction.DEACTIVATE
    if fields or slots_touched:
        return ChangeAction.UPDATE
    return ChangeAction.UNCHANGED


def _differs(before: Any, after: Any, key: str | None = None) -> bool:
    """Compare two cell values the way the workbook round-trips them.

    Args:
        before: The stored value, as the export rendered it.
        after: The value read back from the file.
        key: The column, when its text has a canonical form the operator is
            not required to reproduce character for character.
    """
    if key == "reasoning_enum_values":
        # The export writes "low, high"; retyping it as "low,high" is the same
        # ladder. A preview is a claim about what will change, and spacing is
        # not a change -- reporting one would also trigger a write storing the
        # identical list. Order is NOT normalised: the ladder is ascending, so
        # it carries meaning.
        return _ladder_cell(before) != _ladder_cell(after)
    return _render(before) != _render(after)


def _ladder_cell(value: Any) -> tuple[str, ...]:
    """The levels a ladder cell names, whatever spacing was used."""
    if value is None or value == "":
        return ()
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def _render(value: Any) -> str | None:
    """Render a value as the text a preview shows and a hash consumes."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        # 0.40 and 0.4 are the same tariff: the workbook stores a float, and a
        # trailing zero is not an edit.
        return format(value.normalize(), "f")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)
