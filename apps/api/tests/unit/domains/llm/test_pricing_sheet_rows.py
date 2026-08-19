"""Unit tests for the export row builder.

Two things this module must get right, both learned from the owner's review of
a real export:

- **the row that carries the price must say what the price is.** A windowed
  tariff showed only its base prices with a discreet mode flag lost among 27
  columns, and read as flat pricing. The summary column is the fix.
- **an anomaly is stated, never implied.** A model with no active tariff is
  billed zero in silence at runtime; the export says so in words.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.pricing_sheet import CUSTOM_TEMPLATE_MARKER
from src.domains.llm.pricing_sheet_rows import EXPORT_LABEL_KEYS, build_export_rows
from tests.helpers.llm_helpers import create_llm_pricing_async, ensure_llm_model_async

LABELS = {
    "settings.admin.llm.sheet.status.ok": "ok",
    "settings.admin.llm.sheet.status.no_pricing": "aucun tarif actif",
    "settings.admin.llm.sheet.status.multiple": "{count} tarifs actifs",
    "settings.admin.llm.sheet.status.shadowed": "facturé sous {name}",
    "settings.admin.llm.sheet.slots_summary": "{count} fenêtres : {windows}",
    "settings.admin.llm.sheet.reasoning_prefix": "raisonnement",
}

PEAK = [
    {
        "start_utc": "01:00",
        "end_utc": "04:00",
        "input_unit_price": 0.44,
        "cached_input_unit_price": 0.014,
        "output_unit_price": 1.32,
    },
    {
        "start_utc": "06:00",
        "end_utc": "10:00",
        "input_unit_price": 0.44,
        "cached_input_unit_price": 0.014,
        "output_unit_price": 1.32,
    },
]


async def _row(db: AsyncSession, model_name: str) -> dict:
    payload = await build_export_rows(db, labels=LABELS)
    return next(row for row in payload.models if row["model_name"] == model_name)


@pytest.mark.unit
class TestNominalRows:
    async def test_a_priced_model_carries_its_tariff(self, async_session: AsyncSession) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="ex-priced",
            input_price=Decimal("0.4"),
            output_price=Decimal("1.6"),
        )

        row = await _row(async_session, "ex-priced")

        assert row["input_unit_price"] == Decimal("0.4")
        assert row["output_unit_price"] == Decimal("1.6")
        assert row["pricing_unit"] == "per_1m_tokens"

    async def test_capabilities_and_sampling_flags_are_carried(
        self, async_session: AsyncSession
    ) -> None:
        await ensure_llm_model_async(async_session, "ex-caps")

        row = await _row(async_session, "ex-caps")

        for key in (
            "supports_tools",
            "supports_vision",
            "supports_strict_mode",
            "supports_temperature",
            "supports_top_p",
            "supports_frequency_penalty",
            "supports_presence_penalty",
        ):
            assert key in row, key

    async def test_the_effective_date_of_the_current_tariff_is_readable(
        self, async_session: AsyncSession
    ) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="ex-dated",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )

        row = await _row(async_session, "ex-dated")

        assert row["effective_from"] and "T" in row["effective_from"]


@pytest.mark.unit
class TestDiagnosticsAreStated:
    async def test_a_model_without_a_tariff_says_so(self, async_session: AsyncSession) -> None:
        await ensure_llm_model_async(async_session, "ex-no-price")

        row = await _row(async_session, "ex-no-price")

        assert row["statut"] == "aucun tarif actif"
        assert row["input_unit_price"] is None

    async def test_a_correctly_priced_model_is_reported_ok(
        self, async_session: AsyncSession
    ) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="ex-ok",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )

        assert (await _row(async_session, "ex-ok"))["statut"] == "ok"

    async def test_a_dated_model_billed_under_its_base_name_says_so(
        self, async_session: AsyncSession
    ) -> None:
        """The runtime falls back to the base model; the file must not pretend
        the dated model has a tariff of its own."""
        await create_llm_pricing_async(
            async_session,
            model_name="ex-base",
            input_price=Decimal("2.5"),
            output_price=Decimal("10"),
        )
        await ensure_llm_model_async(async_session, "ex-base-2024-05-13")

        row = await _row(async_session, "ex-base-2024-05-13")

        assert row["statut"] == "facturé sous ex-base"


@pytest.mark.unit
class TestTimeSlotsAreLegible:
    async def test_a_flat_model_states_flat(self, async_session: AsyncSession) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="ex-flat",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )

        row = await _row(async_session, "ex-flat")

        assert row["time_slots_mode"] == "flat"
        assert row["time_slots_summary"] in (None, "")

    async def test_a_windowed_model_states_its_windows_on_the_row_itself(
        self, async_session: AsyncSession
    ) -> None:
        """The defect the owner found: the windows existed only on another sheet."""
        pricing = await create_llm_pricing_async(
            async_session,
            model_name="ex-windowed",
            input_price=Decimal("0.22"),
            output_price=Decimal("0.66"),
        )
        pricing.time_slots = PEAK
        await async_session.flush()

        row = await _row(async_session, "ex-windowed")

        assert row["time_slots_mode"] == "windows"
        assert row["time_slots_summary"] == "2 fenêtres : 01:00-04:00, 06:00-10:00"

    async def test_the_export_never_writes_the_neutral_mode(
        self, async_session: AsyncSession
    ) -> None:
        """``inherit`` is an instruction, not a state: a file says what IS."""
        await create_llm_pricing_async(
            async_session,
            model_name="ex-never-inherit",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        payload = await build_export_rows(async_session, labels=LABELS)
        assert all(row["time_slots_mode"] != "inherit" for row in payload.models)

    async def test_each_window_becomes_a_row_of_the_slots_sheet(
        self, async_session: AsyncSession
    ) -> None:
        pricing = await create_llm_pricing_async(
            async_session,
            model_name="ex-slots-sheet",
            input_price=Decimal("0.22"),
            output_price=Decimal("0.66"),
        )
        pricing.time_slots = PEAK
        await async_session.flush()

        payload = await build_export_rows(async_session, labels=LABELS)

        mine = [row for row in payload.slots if row["model_name"] == "ex-slots-sheet"]
        assert len(mine) == 2
        assert mine[0]["start_utc"] == "01:00"
        assert mine[0]["input_unit_price"] == Decimal("0.44")


@pytest.mark.unit
class TestReasoning:
    async def test_a_model_carries_a_readable_reasoning_shape(
        self, async_session: AsyncSession
    ) -> None:
        await ensure_llm_model_async(async_session, "ex-shape")

        row = await _row(async_session, "ex-shape")

        assert isinstance(row["reasoning_shape"], str) and row["reasoning_shape"]

    async def test_a_model_matching_no_template_is_marked_custom(
        self, async_session: AsyncSession
    ) -> None:
        """Templates are built from ACTIVE models, so an inactive one can match
        nothing — the file must say so rather than assign a wrong template."""
        model = await ensure_llm_model_async(async_session, "ex-orphan")
        model.is_active = False
        model.reasoning_doc_i18n_key = "a-shape-nobody-else-has"
        await async_session.flush()

        payload = await build_export_rows(async_session, labels=LABELS)
        row = next(r for r in payload.models if r["model_name"] == "ex-orphan")

        assert row["reasoning_template"] in {CUSTOM_TEMPLATE_MARKER, *payload.templates}

    async def test_the_templates_offered_are_returned_for_the_dropdown(
        self, async_session: AsyncSession
    ) -> None:
        await ensure_llm_model_async(async_session, "ex-template-source")

        payload = await build_export_rows(async_session, labels=LABELS)

        assert payload.templates


@pytest.mark.unit
class TestFingerprints:
    async def test_every_exported_model_has_a_fingerprint(
        self, async_session: AsyncSession
    ) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="ex-fp",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )

        payload = await build_export_rows(async_session, labels=LABELS)

        assert payload.fingerprints["ex-fp"]

    async def test_the_fingerprint_is_stable_across_two_exports(
        self, async_session: AsyncSession
    ) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="ex-stable",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )

        first = await build_export_rows(async_session, labels=LABELS)
        second = await build_export_rows(async_session, labels=LABELS)

        assert first.fingerprints["ex-stable"] == second.fingerprints["ex-stable"]

    async def test_the_fingerprint_changes_when_the_tariff_changes(
        self, async_session: AsyncSession
    ) -> None:
        """This is what lets an import refuse rows edited underneath the admin."""
        await create_llm_pricing_async(
            async_session,
            model_name="ex-moves",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        before = (await build_export_rows(async_session, labels=LABELS)).fingerprints["ex-moves"]

        await create_llm_pricing_async(
            async_session,
            model_name="ex-moves",
            input_price=Decimal("9"),
            output_price=Decimal("9"),
        )
        after = (await build_export_rows(async_session, labels=LABELS)).fingerprints["ex-moves"]

        assert before != after

    async def test_a_derived_column_does_not_move_the_fingerprint(
        self, async_session: AsyncSession
    ) -> None:
        """Only what the admin can edit takes part; otherwise a diagnostic
        changing elsewhere would refuse an untouched row."""
        await create_llm_pricing_async(
            async_session,
            model_name="ex-derived",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        payload = await build_export_rows(async_session, labels=LABELS)
        row = next(r for r in payload.models if r["model_name"] == "ex-derived")

        from src.domains.llm.pricing_sheet_rows import fingerprint_row

        mutated = {**row, "statut": "something else", "reasoning_shape": "x"}
        assert fingerprint_row(mutated) == fingerprint_row(row)


@pytest.mark.unit
class TestLabelContract:
    def test_the_module_publishes_the_label_keys_it_needs(self) -> None:
        """The route resolves these from i18n; a missing key must be findable."""
        assert set(EXPORT_LABEL_KEYS) == set(LABELS)


@pytest.mark.unit
class TestStatusSeverityOrder:
    """Inheritance is not an anomaly; absence is. The order must not invert."""

    async def test_a_model_with_neither_tariff_nor_fallback_is_the_real_alarm(
        self, async_session: AsyncSession
    ) -> None:
        await ensure_llm_model_async(async_session, "ex-truly-unpriced")

        assert (await _row(async_session, "ex-truly-unpriced"))["statut"] == "aucun tarif actif"

    async def test_a_dated_model_inheriting_a_tariff_is_not_reported_as_unpriced(
        self, async_session: AsyncSession
    ) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="ex-parent",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        await ensure_llm_model_async(async_session, "ex-parent-2024-01-01")

        row = await _row(async_session, "ex-parent-2024-01-01")

        assert row["statut"] == "facturé sous ex-parent"
        assert "aucun" not in row["statut"]


@pytest.mark.unit
class TestFingerprintTravelsInTheFile:
    """The stamp must reach the import, and must not hash itself."""

    async def test_the_row_carries_its_own_fingerprint(self, async_session: AsyncSession) -> None:
        from src.domains.llm.pricing_sheet import FINGERPRINT_COLUMN

        await create_llm_pricing_async(
            async_session,
            model_name="ex-stamped",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )

        payload = await build_export_rows(async_session, labels=LABELS)
        row = next(r for r in payload.models if r["model_name"] == "ex-stamped")

        assert row[FINGERPRINT_COLUMN] == payload.fingerprints["ex-stamped"]

    async def test_the_stamp_is_not_part_of_what_it_hashes(
        self, async_session: AsyncSession
    ) -> None:
        """Otherwise stamping a row would change the value being stamped."""
        from src.domains.llm.pricing_sheet import FINGERPRINT_COLUMN
        from src.domains.llm.pricing_sheet_rows import fingerprint_row

        await create_llm_pricing_async(
            async_session,
            model_name="ex-not-circular",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        payload = await build_export_rows(async_session, labels=LABELS)
        row = next(r for r in payload.models if r["model_name"] == "ex-not-circular")

        assert fingerprint_row(row) == row[FINGERPRINT_COLUMN]
        assert fingerprint_row({**row, FINGERPRINT_COLUMN: "tampered"}) == row[FINGERPRINT_COLUMN]
