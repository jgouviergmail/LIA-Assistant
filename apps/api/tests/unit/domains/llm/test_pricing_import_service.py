"""Unit tests for the transactional application of a change plan.

The rule that governs everything here: an import is **all or nothing**. A
half-applied tariff table is worse than no import at all, because nobody can
tell which half took. The second rule is almost as important: what did not
change is not written — otherwise a 124-row import would leave 124 useless
tariff versions behind and the cost history would become unreadable.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import LLMModel, LLMModelPricing
from src.domains.llm.pricing_change_plan import build_change_plan
from src.domains.llm.pricing_import_service import PricingImportService
from src.domains.llm.pricing_sheet import FINGERPRINT_COLUMN
from src.domains.llm.pricing_sheet_rows import build_export_rows
from src.infrastructure.tabular_io.report import ParsedRow
from tests.helpers.llm_helpers import create_llm_pricing_async

LABELS = {
    "settings.admin.llm.sheet.status.ok": "ok",
    "settings.admin.llm.sheet.status.no_pricing": "aucun tarif actif",
    "settings.admin.llm.sheet.status.multiple": "{count} tarifs actifs",
    "settings.admin.llm.sheet.status.shadowed": "facture sous {name}",
    "settings.admin.llm.sheet.slots_summary": "{count} fenetres : {windows}",
    "settings.admin.llm.sheet.reasoning_prefix": "raisonnement",
}


async def _export(db: AsyncSession):
    return await build_export_rows(db, labels=LABELS)


def _row_for(payload: Any, model_name: str, **edits: Any) -> ParsedRow:
    """Build the parsed row an untouched — or edited — export would yield."""
    source = next(r for r in payload.models if r["model_name"] == model_name)
    values = {k: v for k, v in {**source, **edits}.items() if k != FINGERPRINT_COLUMN}
    return ParsedRow(
        row_number=3,
        key=model_name,
        values=values,
        derived={FINGERPRINT_COLUMN: source[FINGERPRINT_COLUMN]},
    )


async def _apply(db: AsyncSession, payload: Any, rows: list[ParsedRow], slots: Any = ()):
    plan = build_change_plan(db_rows=payload.models, sheet_rows=rows, sheet_slots=slots)
    return plan, await PricingImportService(db).apply(plan, sheet_rows=rows, sheet_slots=slots)


async def _active_pricing_count(db: AsyncSession, model_name: str) -> int:
    model = (await db.scalars(select(LLMModel).where(LLMModel.model_name == model_name))).first()
    assert model is not None
    return (
        await db.scalar(
            select(func.count())
            .select_from(LLMModelPricing)
            .where(LLMModelPricing.model_id == model.id)
        )
        or 0
    )


@pytest.mark.unit
class TestNothingChangesNothingWrites:
    async def test_an_untouched_plan_writes_no_tariff_version(
        self, async_session: AsyncSession
    ) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="imp-quiet",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        payload = await _export(async_session)
        before = await _active_pricing_count(async_session, "imp-quiet")

        _, outcome = await _apply(async_session, payload, [_row_for(payload, "imp-quiet")])

        assert outcome.unchanged == 1
        assert await _active_pricing_count(async_session, "imp-quiet") == before

    async def test_an_untouched_plan_reports_nothing_done(
        self, async_session: AsyncSession
    ) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="imp-silent",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        payload = await _export(async_session)

        _, outcome = await _apply(async_session, payload, [_row_for(payload, "imp-silent")])

        assert outcome.created == () and outcome.updated == ()
        assert outcome.deactivated == () and outcome.reactivated == ()


@pytest.mark.unit
class TestWrites:
    async def test_a_price_edit_supersedes_the_tariff(self, async_session: AsyncSession) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="imp-price",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        payload = await _export(async_session)

        _, outcome = await _apply(
            async_session,
            payload,
            [_row_for(payload, "imp-price", input_unit_price=Decimal("9"))],
        )
        await async_session.flush()

        assert outcome.updated == ("imp-price",)
        after = await _export(async_session)
        row = next(r for r in after.models if r["model_name"] == "imp-price")
        assert row["input_unit_price"] == Decimal("9")

    async def test_the_previous_tariff_survives_as_history(
        self, async_session: AsyncSession
    ) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="imp-history",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        payload = await _export(async_session)
        before = await _active_pricing_count(async_session, "imp-history")

        await _apply(
            async_session,
            payload,
            [_row_for(payload, "imp-history", output_unit_price=Decimal("8"))],
        )
        await async_session.flush()

        assert await _active_pricing_count(async_session, "imp-history") == before + 1

    async def test_a_capability_edit_is_applied_in_place(self, async_session: AsyncSession) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="imp-caps",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        payload = await _export(async_session)
        current = next(r for r in payload.models if r["model_name"] == "imp-caps")

        await _apply(
            async_session,
            payload,
            [_row_for(payload, "imp-caps", supports_vision=not current["supports_vision"])],
        )
        await async_session.flush()

        after = await _export(async_session)
        row = next(r for r in after.models if r["model_name"] == "imp-caps")
        assert row["supports_vision"] != current["supports_vision"]

    async def test_a_deactivation_is_applied(self, async_session: AsyncSession) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="imp-off",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        payload = await _export(async_session)

        _, outcome = await _apply(
            async_session, payload, [_row_for(payload, "imp-off", is_active=False)]
        )
        await async_session.flush()

        assert outcome.deactivated == ("imp-off",)
        model = (
            await async_session.scalars(select(LLMModel).where(LLMModel.model_name == "imp-off"))
        ).first()
        assert model is not None and model.is_active is False

    async def test_a_reactivation_is_applied(self, async_session: AsyncSession) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="imp-on",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        payload = await _export(async_session)
        await _apply(async_session, payload, [_row_for(payload, "imp-on", is_active=False)])
        await async_session.flush()

        payload = await _export(async_session)
        _, outcome = await _apply(
            async_session, payload, [_row_for(payload, "imp-on", is_active=True)]
        )
        await async_session.flush()

        assert outcome.reactivated == ("imp-on",)

    async def test_clearing_a_cached_price_reaches_the_database(
        self, async_session: AsyncSession
    ) -> None:
        """The whole point of the explicit clear: an emptied cell means NULL."""
        await create_llm_pricing_async(
            async_session,
            model_name="imp-clear",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
            cached_input_price=Decimal("0.5"),
        )
        payload = await _export(async_session)

        await _apply(
            async_session,
            payload,
            [_row_for(payload, "imp-clear", cached_input_unit_price=None)],
        )
        await async_session.flush()

        after = await _export(async_session)
        row = next(r for r in after.models if r["model_name"] == "imp-clear")
        assert row["cached_input_unit_price"] is None


@pytest.mark.unit
class TestAllOrNothing:
    async def test_a_plan_carrying_an_issue_writes_nothing(
        self, async_session: AsyncSession
    ) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="imp-refused",
            input_price=Decimal("1"),
            output_price=Decimal("2"),
        )
        payload = await _export(async_session)
        rows = [_row_for(payload, "imp-refused", provider="anthropic")]
        plan = build_change_plan(db_rows=payload.models, sheet_rows=rows)
        assert not plan.is_applicable

        with pytest.raises(ValueError):
            await PricingImportService(async_session).apply(plan, sheet_rows=rows)

        after = await _export(async_session)
        row = next(r for r in after.models if r["model_name"] == "imp-refused")
        assert row["provider"] == "openai"

    async def test_a_failure_midway_leaves_nothing_applied(
        self, async_session: AsyncSession
    ) -> None:
        """The second row cannot be created; the first must not survive alone."""
        payload = await _export(async_session)
        good = ParsedRow(
            row_number=3,
            key="imp-atomic-a",
            values={
                "model_name": "imp-atomic-a",
                "provider": "openai",
                "kind": "chat",
                "is_active": True,
                "max_input_tokens": 10,
                "max_output_tokens": 10,
                "pricing_unit": "per_1m_tokens",
                "input_unit_price": Decimal("1"),
                "output_unit_price": Decimal("2"),
                "reasoning_template": "does-not-exist-anywhere",
            },
            derived={},
        )
        plan = build_change_plan(db_rows=payload.models, sheet_rows=[good])

        with pytest.raises(Exception):
            await PricingImportService(async_session).apply(plan, sheet_rows=[good])
        await async_session.rollback()

        found = (
            await async_session.scalars(
                select(LLMModel).where(LLMModel.model_name == "imp-atomic-a")
            )
        ).first()
        assert found is None


@pytest.mark.unit
class TestOutcomeIsHonest:
    async def test_the_outcome_names_every_model_it_touched(
        self, async_session: AsyncSession
    ) -> None:
        for name in ("imp-sum-a", "imp-sum-b", "imp-sum-c"):
            await create_llm_pricing_async(
                async_session,
                model_name=name,
                input_price=Decimal("1"),
                output_price=Decimal("2"),
            )
        payload = await _export(async_session)

        _, outcome = await _apply(
            async_session,
            payload,
            [
                _row_for(payload, "imp-sum-a", input_unit_price=Decimal("5")),
                _row_for(payload, "imp-sum-b", is_active=False),
                _row_for(payload, "imp-sum-c"),
            ],
        )

        assert outcome.updated == ("imp-sum-a",)
        assert outcome.deactivated == ("imp-sum-b",)
        assert outcome.unchanged == 1

    async def test_the_total_matches_the_plan(self, async_session: AsyncSession) -> None:
        """A count shown to an administrator is a claim: it is exact."""
        for name in ("imp-tot-a", "imp-tot-b"):
            await create_llm_pricing_async(
                async_session,
                model_name=name,
                input_price=Decimal("1"),
                output_price=Decimal("2"),
            )
        payload = await _export(async_session)
        rows = [
            _row_for(payload, "imp-tot-a", input_unit_price=Decimal("3")),
            _row_for(payload, "imp-tot-b"),
        ]

        plan, outcome = await _apply(async_session, payload, rows)

        assert outcome.total_touched == len(plan.pricing_changes) + len(outcome.deactivated)
