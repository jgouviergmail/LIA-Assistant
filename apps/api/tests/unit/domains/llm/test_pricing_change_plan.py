"""Unit tests for the diff engine.

Two properties matter more than any individual rule, and both were measured on
the real 124-model catalogue before this code existed:

- **idempotence**: an untouched export, re-imported, must produce no change at
  all. Without it every import would create 124 useless tariff versions and the
  preview would be unreadable.
- **sensitivity**: an edited file must produce exactly the edits, correctly
  classified — no false positive, no false negative.

The rest guards the rules an administrator relies on: a row absent from the
file changes nothing, a deactivation is explicit, a price is rewritten only
when it really moved.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from src.domains.llm.pricing_change_plan import ChangeAction, build_change_plan
from src.domains.llm.pricing_sheet import FINGERPRINT_COLUMN
from src.domains.llm.pricing_sheet_rows import fingerprint_row
from src.infrastructure.tabular_io.report import IssueCode, ParsedRow

BASE: dict[str, Any] = {
    "model_name": "gpt-x",
    "provider": "openai",
    "kind": "chat",
    "is_active": True,
    "max_input_tokens": 1000,
    "max_output_tokens": 200,
    "supports_tools": True,
    "supports_structured_output": True,
    "supports_strict_mode": False,
    "supports_streaming": True,
    "supports_vision": False,
    "supports_temperature": True,
    "supports_top_p": True,
    "supports_frequency_penalty": True,
    "supports_presence_penalty": True,
    "reasoning_template": "gpt-x",
    "reasoning_doc_i18n_key": None,
    "pricing_unit": "per_1m_tokens",
    "input_unit_price": Decimal("1"),
    "cached_input_unit_price": None,
    "output_unit_price": Decimal("2"),
    "time_slots_mode": "flat",
}


def _db_row(**overrides: Any) -> dict[str, Any]:
    row = {**BASE, **overrides}
    row[FINGERPRINT_COLUMN] = fingerprint_row(row)
    return row


def _sheet_row(db_row: dict[str, Any], row_number: int = 3, **edits: Any) -> ParsedRow:
    """Mirror what the reader would produce for a row of the workbook."""
    values = {key: value for key, value in {**db_row, **edits}.items() if key != FINGERPRINT_COLUMN}
    return ParsedRow(
        row_number=row_number,
        key=str(values["model_name"]),
        values=values,
        derived={FINGERPRINT_COLUMN: db_row[FINGERPRINT_COLUMN]},
    )


def _plan(db_rows: list[dict[str, Any]], sheet_rows: list[ParsedRow], slots: Any = ()):
    return build_change_plan(db_rows=db_rows, sheet_rows=sheet_rows, sheet_slots=slots)


@pytest.mark.unit
class TestIdempotence:
    def test_an_untouched_export_produces_no_change(self) -> None:
        rows = [_db_row(model_name=f"m{i}") for i in range(5)]
        plan = _plan(rows, [_sheet_row(r, 3 + i) for i, r in enumerate(rows)])

        assert plan.issues == ()
        assert all(change.action is ChangeAction.UNCHANGED for change in plan.changes)

    def test_an_untouched_export_writes_no_tariff(self) -> None:
        """The rule that stops 124 rows creating 124 useless tariff versions."""
        rows = [_db_row(model_name=f"m{i}") for i in range(3)]
        plan = _plan(rows, [_sheet_row(r, 3 + i) for i, r in enumerate(rows)])

        assert not plan.pricing_changes

    def test_a_price_written_with_trailing_zeros_is_not_a_change(self) -> None:
        """0.40 and 0.4 are the same tariff; the workbook round-trips floats."""
        db_row = _db_row(input_unit_price=Decimal("0.40"))
        plan = _plan([db_row], [_sheet_row(db_row, input_unit_price=Decimal("0.4"))])

        assert plan.changes[0].action is ChangeAction.UNCHANGED


@pytest.mark.unit
class TestSensitivity:
    def test_a_price_edit_is_detected_and_classified(self) -> None:
        db_row = _db_row()
        plan = _plan([db_row], [_sheet_row(db_row, input_unit_price=Decimal("9"))])

        change = plan.changes[0]
        assert change.action is ChangeAction.UPDATE
        assert [f.field for f in change.fields] == ["input_unit_price"]
        assert (change.fields[0].before, change.fields[0].after) == ("1", "9")

    def test_a_capability_edit_is_detected(self) -> None:
        db_row = _db_row()
        plan = _plan([db_row], [_sheet_row(db_row, supports_vision=True)])

        assert [f.field for f in plan.changes[0].fields] == ["supports_vision"]

    def test_a_new_model_is_a_creation(self) -> None:
        plan = _plan([], [_sheet_row(_db_row(model_name="brand-new"))])

        assert plan.changes[0].action is ChangeAction.CREATE

    def test_only_the_edited_rows_move(self) -> None:
        rows = [_db_row(model_name=f"m{i}") for i in range(4)]
        sheet = [_sheet_row(r, 3 + i) for i, r in enumerate(rows)]
        sheet[2] = _sheet_row(rows[2], 5, output_unit_price=Decimal("7"))

        plan = _plan(rows, sheet)

        moved = [c for c in plan.changes if c.action is not ChangeAction.UNCHANGED]
        assert [c.model_name for c in moved] == ["m2"]


@pytest.mark.unit
class TestLifecycle:
    def test_turning_active_off_is_a_deactivation(self) -> None:
        db_row = _db_row()
        plan = _plan([db_row], [_sheet_row(db_row, is_active=False)])

        assert plan.changes[0].action is ChangeAction.DEACTIVATE

    def test_turning_active_on_is_a_reactivation(self) -> None:
        db_row = _db_row(is_active=False)
        plan = _plan([db_row], [_sheet_row(db_row, is_active=True)])

        assert plan.changes[0].action is ChangeAction.REACTIVATE

    def test_a_row_absent_from_the_file_changes_nothing(self) -> None:
        """A forgotten filter must never delete a catalogue."""
        rows = [_db_row(model_name="kept"), _db_row(model_name="not-in-file")]
        plan = _plan(rows, [_sheet_row(rows[0])])

        assert [c.model_name for c in plan.changes] == ["kept"]
        assert not any(c.action is ChangeAction.DEACTIVATE for c in plan.changes)


@pytest.mark.unit
class TestPricingRules:
    def test_clearing_the_cached_price_is_an_explicit_change(self) -> None:
        """An emptied cell means NULL; the old value must not survive."""
        db_row = _db_row(cached_input_unit_price=Decimal("0.5"))
        plan = _plan([db_row], [_sheet_row(db_row, cached_input_unit_price=None)])

        change = plan.changes[0]
        assert [f.field for f in change.fields] == ["cached_input_unit_price"]
        assert change.fields[0].after is None

    def test_changing_the_unit_is_a_pricing_change(self) -> None:
        db_row = _db_row()
        plan = _plan([db_row], [_sheet_row(db_row, pricing_unit="per_audio_hour")])

        assert plan.pricing_changes == ("gpt-x",)

    def test_a_capability_edit_alone_is_not_a_pricing_change(self) -> None:
        db_row = _db_row()
        plan = _plan([db_row], [_sheet_row(db_row, supports_vision=True)])

        assert not plan.pricing_changes


@pytest.mark.unit
class TestTimeSlots:
    def test_declaring_windows_carries_the_rows_of_the_slot_sheet(self) -> None:
        db_row = _db_row()
        slots = [
            ParsedRow(
                row_number=3,
                key="gpt-x",
                values={
                    "model_name": "gpt-x",
                    "start_utc": "01:00",
                    "end_utc": "04:00",
                    "input_unit_price": Decimal("2"),
                    "cached_input_unit_price": None,
                    "output_unit_price": Decimal("4"),
                },
            )
        ]

        plan = _plan([db_row], [_sheet_row(db_row, time_slots_mode="windows")], slots)

        assert plan.changes[0].slots_after == 1

    def test_flat_clears_the_windows(self) -> None:
        db_row = _db_row(time_slots_mode="windows")
        plan = _plan([db_row], [_sheet_row(db_row, time_slots_mode="flat")])

        assert plan.changes[0].action is ChangeAction.UPDATE
        assert plan.changes[0].slots_after == 0

    def test_inherit_leaves_the_windows_untouched(self) -> None:
        """``inherit`` is the ADR-223 contract: omitted means unchanged."""
        db_row = _db_row(time_slots_mode="windows")
        plan = _plan([db_row], [_sheet_row(db_row, time_slots_mode="inherit")])

        assert plan.changes[0].action is ChangeAction.UNCHANGED


@pytest.mark.unit
class TestRefusals:
    def test_changing_the_provider_of_an_existing_model_is_refused(self) -> None:
        """The service cannot express it; dropping it silently would be a lie."""
        db_row = _db_row()
        plan = _plan([db_row], [_sheet_row(db_row, provider="anthropic")])

        assert IssueCode.PROVIDER_IMMUTABLE in {issue.code for issue in plan.issues}

    def test_a_row_edited_underneath_the_administrator_is_refused(self) -> None:
        db_row = _db_row()
        stale = _sheet_row(db_row, input_unit_price=Decimal("5"))
        moved = {**db_row, "output_unit_price": Decimal("99")}
        moved[FINGERPRINT_COLUMN] = fingerprint_row(moved)

        plan = _plan([moved], [stale])

        assert IssueCode.ROW_CHANGED_SINCE_EXPORT in {issue.code for issue in plan.issues}

    def test_only_the_stale_row_is_refused_not_the_whole_file(self) -> None:
        """A colleague touching one model must not reject a whole import."""
        fresh = _db_row(model_name="fresh")
        moved = _db_row(model_name="moved")
        stale_sheet = _sheet_row(moved, 4)
        moved_now = {**moved, "output_unit_price": Decimal("99")}
        moved_now[FINGERPRINT_COLUMN] = fingerprint_row(moved_now)

        plan = _plan([fresh, moved_now], [_sheet_row(fresh, 3), stale_sheet])

        stale = [i for i in plan.issues if i.code is IssueCode.ROW_CHANGED_SINCE_EXPORT]
        assert len(stale) == 1
        assert stale[0].params["key"] == "moved"

    def test_a_row_without_a_fingerprint_is_accepted(self) -> None:
        """A hand-built file has no stamp; it is checked, not required."""
        db_row = _db_row()
        row = ParsedRow(row_number=3, key="gpt-x", values={**BASE}, derived={})

        plan = _plan([db_row], [row])

        assert not any(i.code is IssueCode.ROW_CHANGED_SINCE_EXPORT for i in plan.issues)

    def test_a_creation_needs_no_fingerprint(self) -> None:
        row = ParsedRow(
            row_number=3, key="new-one", values={**BASE, "model_name": "new-one"}, derived={}
        )
        plan = _plan([], [row])

        assert plan.changes[0].action is ChangeAction.CREATE
        assert not plan.issues


@pytest.mark.unit
class TestPlanIntegrity:
    def test_the_plan_fingerprint_is_stable_for_the_same_plan(self) -> None:
        db_row = _db_row()
        first = _plan([db_row], [_sheet_row(db_row, input_unit_price=Decimal("9"))])
        second = _plan([db_row], [_sheet_row(db_row, input_unit_price=Decimal("9"))])

        assert first.fingerprint() == second.fingerprint()

    def test_the_plan_fingerprint_changes_with_the_plan(self) -> None:
        """This is what makes a preview binding: apply refuses a different plan."""
        db_row = _db_row()
        first = _plan([db_row], [_sheet_row(db_row, input_unit_price=Decimal("9"))])
        second = _plan([db_row], [_sheet_row(db_row, input_unit_price=Decimal("8"))])

        assert first.fingerprint() != second.fingerprint()

    def test_a_plan_carrying_an_issue_is_not_applicable(self) -> None:
        db_row = _db_row()
        plan = _plan([db_row], [_sheet_row(db_row, provider="anthropic")])

        assert plan.is_applicable is False

    def test_a_clean_plan_is_applicable(self) -> None:
        db_row = _db_row()
        plan = _plan([db_row], [_sheet_row(db_row, input_unit_price=Decimal("9"))])

        assert plan.is_applicable is True

    def test_counts_are_exposed_for_the_preview(self) -> None:
        rows = [_db_row(model_name=f"m{i}") for i in range(3)]
        sheet = [_sheet_row(r, 3 + i) for i, r in enumerate(rows)]
        sheet[0] = _sheet_row(rows[0], 3, is_active=False)
        sheet[1] = _sheet_row(rows[1], 4, input_unit_price=Decimal("9"))

        plan = _plan(rows, sheet)

        assert plan.counts[ChangeAction.DEACTIVATE] == 1
        assert plan.counts[ChangeAction.UPDATE] == 1
        assert plan.counts[ChangeAction.UNCHANGED] == 1


@pytest.mark.unit
class TestWindowedModelsAreNotRewrittenForNothing:
    """Found on the real catalogue: re-importing an untouched export marked the
    two windowed models as updated, because declaring ``windows`` was treated as
    touching them. Each import would have superseded their tariff for nothing.
    """

    @staticmethod
    def _window(model: str, start: str, end: str, price: str) -> ParsedRow:
        return ParsedRow(
            row_number=3,
            key=model,
            values={
                "model_name": model,
                "start_utc": start,
                "end_utc": end,
                "input_unit_price": Decimal(price),
                "cached_input_unit_price": None,
                "output_unit_price": Decimal("9"),
            },
        )

    def test_identical_windows_are_not_a_change(self) -> None:
        db_row = _db_row(time_slots_mode="windows")
        windows = [self._window("gpt-x", "01:00", "04:00", "2")]

        plan = build_change_plan(
            db_rows=[db_row],
            sheet_rows=[_sheet_row(db_row, time_slots_mode="windows")],
            sheet_slots=windows,
            db_slots=windows,
        )

        assert plan.changes[0].action is ChangeAction.UNCHANGED
        assert not plan.pricing_changes

    def test_a_changed_window_price_is_a_change(self) -> None:
        db_row = _db_row(time_slots_mode="windows")

        plan = build_change_plan(
            db_rows=[db_row],
            sheet_rows=[_sheet_row(db_row, time_slots_mode="windows")],
            sheet_slots=[self._window("gpt-x", "01:00", "04:00", "5")],
            db_slots=[self._window("gpt-x", "01:00", "04:00", "2")],
        )

        assert plan.changes[0].action is ChangeAction.UPDATE

    def test_an_added_window_is_a_change(self) -> None:
        db_row = _db_row(time_slots_mode="windows")

        plan = build_change_plan(
            db_rows=[db_row],
            sheet_rows=[_sheet_row(db_row, time_slots_mode="windows")],
            sheet_slots=[
                self._window("gpt-x", "01:00", "04:00", "2"),
                self._window("gpt-x", "06:00", "10:00", "2"),
            ],
            db_slots=[self._window("gpt-x", "01:00", "04:00", "2")],
        )

        assert plan.changes[0].action is ChangeAction.UPDATE
        assert plan.changes[0].slots_after == 2

    def test_reordering_windows_is_not_a_change(self) -> None:
        """Resolution never depends on order (ADR-223), so neither does the diff."""
        db_row = _db_row(time_slots_mode="windows")
        first = self._window("gpt-x", "01:00", "04:00", "2")
        second = self._window("gpt-x", "06:00", "10:00", "3")

        plan = build_change_plan(
            db_rows=[db_row],
            sheet_rows=[_sheet_row(db_row, time_slots_mode="windows")],
            sheet_slots=[second, first],
            db_slots=[first, second],
        )

        assert plan.changes[0].action is ChangeAction.UNCHANGED


@pytest.mark.unit
class TestCreationRequirements:
    """A creation must be viable before anything is written.

    Discovering at write time that a new row cannot become a model turns a
    reviewable preview into a failed import — and the administrator learns it
    after clicking apply rather than before.
    """

    @staticmethod
    def _new_row(**overrides: Any) -> ParsedRow:
        values = {**BASE, "model_name": "brand-new", **overrides}
        return ParsedRow(row_number=9, key="brand-new", values=values, derived={})

    def test_a_complete_new_row_is_accepted(self) -> None:
        plan = _plan([], [self._new_row()])

        assert plan.changes[0].action is ChangeAction.CREATE
        assert not plan.issues

    def test_a_creation_without_a_reasoning_template_is_refused(self) -> None:
        """Templates are how the sheet expresses a reasoning shape; the custom
        marker means "matches none", which cannot be turned into a model."""
        plan = _plan([], [self._new_row(reasoning_template="(custom)")])

        assert IssueCode.CREATION_NEEDS_TEMPLATE in {i.code for i in plan.issues}

    def test_a_creation_missing_its_provider_is_refused(self) -> None:
        plan = _plan([], [self._new_row(provider=None)])

        issue = next(i for i in plan.issues if i.code is IssueCode.CREATION_FIELD_MISSING)
        assert issue.params["field"] == "provider"

    def test_a_creation_missing_its_price_is_refused(self) -> None:
        plan = _plan([], [self._new_row(input_unit_price=None)])

        assert IssueCode.CREATION_FIELD_MISSING in {i.code for i in plan.issues}

    def test_every_missing_field_is_named_not_just_the_first(self) -> None:
        """An administrator fixing one field at a time is an administrator
        importing the same file five times."""
        plan = _plan([], [self._new_row(provider=None, kind=None, output_unit_price=None)])

        missing = {
            i.params["field"] for i in plan.issues if i.code is IssueCode.CREATION_FIELD_MISSING
        }
        assert missing == {"provider", "kind", "output_unit_price"}

    def test_an_existing_model_is_not_held_to_creation_requirements(self) -> None:
        """Updating one price must not demand the whole row be filled in."""
        db_row = _db_row()
        sparse = ParsedRow(
            row_number=3,
            key="gpt-x",
            values={"model_name": "gpt-x", "input_unit_price": Decimal("9")},
            derived={FINGERPRINT_COLUMN: db_row[FINGERPRINT_COLUMN]},
        )

        plan = _plan([db_row], [sparse])

        assert not plan.issues
        assert plan.changes[0].action is ChangeAction.UPDATE
