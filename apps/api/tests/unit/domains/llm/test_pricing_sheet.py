"""Unit tests for the LLM pricing workbook declaration.

The completeness guard below exists because of a measured failure of method: a
first version of this workbook exported 16 columns against a real schema of
24 + 11, and the fidelity test could not see it — it compared an extraction to
itself. Columns carrying information on more than half the catalogue
(``supports_frequency_penalty`` on 78 models of 124, ``is_reasoning_model`` on
51) were simply absent.

The oracle is therefore the **database schema**, not the author's memory: every
business column is either exported or listed as excluded with a written reason,
and a column added tomorrow reddens CI until somebody decides which it is. Same
doctrine as the boot-time registry completeness asserts (ADR-085).
"""

from __future__ import annotations

import pytest

from src.domains.llm.models import (
    LLMModel,
    LLMModelKindEnum,
    LLMModelPricing,
    LLMProviderEnum,
    LLMReasoningWidgetEnum,
    PricingUnitEnum,
)
from src.domains.llm.pricing_sheet import (
    EXCLUDED_MODEL_COLUMNS,
    EXCLUDED_PRICING_COLUMNS,
    MODEL_SOURCE_COLUMNS,
    MODELS_SHEET,
    PRICING_SOURCE_COLUMNS,
    SLOTS_SHEET,
    build_pricing_workbook_spec,
)


@pytest.mark.unit
class TestSchemaCompleteness:
    """Nothing in the schema may be forgotten in silence."""

    def test_every_model_column_is_exported_or_explicitly_excluded(self) -> None:
        declared = set(MODEL_SOURCE_COLUMNS) | set(EXCLUDED_MODEL_COLUMNS)
        actual = {column.name for column in LLMModel.__table__.columns}
        missing = actual - declared
        assert not missing, (
            f"columns of llm_models neither exported nor excluded: {sorted(missing)}. "
            "Add them to the workbook, or to EXCLUDED_MODEL_COLUMNS with a reason."
        )

    def test_every_pricing_column_is_exported_or_explicitly_excluded(self) -> None:
        declared = set(PRICING_SOURCE_COLUMNS) | set(EXCLUDED_PRICING_COLUMNS)
        actual = {column.name for column in LLMModelPricing.__table__.columns}
        missing = actual - declared
        assert not missing, (
            f"columns of llm_model_pricing neither exported nor excluded: {sorted(missing)}. "
            "Add them to the workbook, or to EXCLUDED_PRICING_COLUMNS with a reason."
        )

    def test_every_exclusion_carries_a_reason(self) -> None:
        for name, reason in {**EXCLUDED_MODEL_COLUMNS, **EXCLUDED_PRICING_COLUMNS}.items():
            assert reason.strip(), f"exclusion of {name!r} has no written reason"

    def test_no_exclusion_names_a_column_that_no_longer_exists(self) -> None:
        """A stale exclusion would hide a genuinely missing column."""
        model_columns = {column.name for column in LLMModel.__table__.columns}
        pricing_columns = {column.name for column in LLMModelPricing.__table__.columns}
        assert set(EXCLUDED_MODEL_COLUMNS) <= model_columns
        assert set(EXCLUDED_PRICING_COLUMNS) <= pricing_columns

    def test_a_column_is_never_both_exported_and_excluded_in_the_same_table(self) -> None:
        """``is_active`` lives on BOTH tables with different meanings, so the
        check has to be per table or one table would vouch for the other."""
        assert not (set(MODEL_SOURCE_COLUMNS) & set(EXCLUDED_MODEL_COLUMNS))
        assert not (set(PRICING_SOURCE_COLUMNS) & set(EXCLUDED_PRICING_COLUMNS))


@pytest.mark.unit
class TestReferentialsComeFromTheEnums:
    """Built from the data, a dropdown would omit any value not yet used."""

    def test_providers_are_the_whole_enum(self) -> None:
        spec = build_pricing_workbook_spec()
        assert set(spec.referentials["PROVIDER"]) == {m.value for m in LLMProviderEnum}

    def test_kinds_are_the_whole_enum(self) -> None:
        spec = build_pricing_workbook_spec()
        assert set(spec.referentials["KIND"]) == {m.value for m in LLMModelKindEnum}

    def test_pricing_units_are_the_whole_enum(self) -> None:
        spec = build_pricing_workbook_spec()
        assert set(spec.referentials["UNIT"]) == {m.value for m in PricingUnitEnum}

    def test_reasoning_widgets_are_the_whole_enum(self) -> None:
        spec = build_pricing_workbook_spec()
        assert set(spec.referentials["WIDGET"]) == {m.value for m in LLMReasoningWidgetEnum}

    def test_time_slot_modes_are_the_three_documented_ones(self) -> None:
        spec = build_pricing_workbook_spec()
        assert set(spec.referentials["SLOTMODE"]) == {"flat", "windows", "inherit"}

    def test_reasoning_templates_are_supplied_by_the_caller(self) -> None:
        spec = build_pricing_workbook_spec(templates=("gpt-5.2", "qwen3-max"))
        assert set(spec.referentials["TEMPLATE"]) >= {"gpt-5.2", "qwen3-max"}

    def test_the_template_referential_is_never_empty(self) -> None:
        """An empty referential would make its dropdown impossible to fill."""
        spec = build_pricing_workbook_spec(templates=())
        assert spec.referentials["TEMPLATE"]


@pytest.mark.unit
class TestSheetShape:
    def test_the_models_sheet_is_keyed_on_the_model_name(self) -> None:
        assert MODELS_SHEET.key_column == "model_name"

    def test_the_slots_sheet_is_keyed_on_the_model_name(self) -> None:
        assert SLOTS_SHEET.key_column == "model_name"

    def test_derived_columns_are_read_only(self) -> None:
        for key in (
            "reasoning_shape",
            "effort_values",
            "effective_from",
            "time_slots_summary",
            "statut",
        ):
            assert MODELS_SHEET.column(key).editable is False, key

    def test_prices_are_declared_with_the_database_scale(self) -> None:
        """DECIMAL(10,6): more decimals must be refused, never rounded."""
        for key in ("input_unit_price", "cached_input_unit_price", "output_unit_price"):
            assert MODELS_SHEET.column(key).decimals == 6

    def test_prices_cannot_be_negative(self) -> None:
        for key in ("input_unit_price", "output_unit_price"):
            assert MODELS_SHEET.column(key).minimum == 0

    def test_the_model_name_is_required(self) -> None:
        assert MODELS_SHEET.column("model_name").required is True

    def test_the_slots_sheet_carries_utc_window_bounds(self) -> None:
        assert SLOTS_SHEET.column("start_utc").kind == "time_hhmm"
        assert SLOTS_SHEET.column("end_utc").kind == "time_hhmm"

    def test_columns_are_grouped_into_readable_blocks(self) -> None:
        """27 columns without collapsible groups (protection disables them):
        colour-coded blocks are what keeps the sheet navigable."""
        blocks = {column.block for column in MODELS_SHEET.columns}
        assert {"identity", "state", "capabilities", "sampling", "reasoning", "pricing"} <= blocks

    def test_the_workbook_declares_both_sheets(self) -> None:
        spec = build_pricing_workbook_spec()
        assert [sheet.name for sheet in spec.sheets] == [MODELS_SHEET.name, SLOTS_SHEET.name]
