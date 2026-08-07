"""A spend ceiling that cannot see the spend is not a ceiling.

Measured on the running demonstrator, 2026-08-07: five real messages burned
59 344 tokens and the ledger recorded 0,000025 EUR. Every LLM type pointed at
``deepseek-v4-flash``, a model absent from that database's catalogue, so
``get_cached_cost_usd_eur`` returned ``(0.0, 0.0)`` 88 times and the instance
ledger stayed flat. ``INSTANCE_DAILY_BUDGET_EUR=1.00`` — the owner's
non-negotiable financial protection — would have let roughly 400 EUR of real
spend through before the counter read one euro.

The catalogue is incomplete because this database is built by MIGRATIONS
alone — 91 prices where development holds 242. Applying the reference seed
bundle on top is correctly refused: the migrations already inserted the
personalities and the bundle deletes before it inserts (ADR-215 gate). So the
invariant is not "seed more", it is that the configured model must be one THIS
database prices, and provisioning REFUSES anything else — the same way it
already refuses a populated database.

A provider that bills nothing (local inference) is the one legitimate way to
have no price, and it is named rather than inferred.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _session_with_price(price_rows: list[object]) -> MagicMock:
    """A session whose pricing lookup returns ``price_rows``."""
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=lambda: (price_rows[0] if price_rows else None))
    )
    return session


class TestAModelThisDatabaseCannotPriceIsRefused:
    async def test_it_names_the_model_when_no_active_price_exists(self) -> None:
        from src.infrastructure.provisioning.demo_llm import unbillable_model

        session = _session_with_price([])

        assert (
            await unbillable_model(session, provider="deepseek", model="deepseek-v4-flash")
            == "deepseek-v4-flash"
        )

    async def test_it_accepts_a_model_with_an_active_token_price(self) -> None:
        from src.infrastructure.provisioning.demo_llm import unbillable_model

        session = _session_with_price([MagicMock()])

        assert await unbillable_model(session, provider="deepseek", model="deepseek-chat") is None

    async def test_a_provider_that_bills_nothing_needs_no_price(self) -> None:
        """Local inference costs the operator no provider euro.

        Refusing it would forbid the one deployment where a missing price is
        the truth rather than a hole.
        """
        from src.infrastructure.provisioning.demo_llm import unbillable_model

        session = _session_with_price([])

        assert await unbillable_model(session, provider="ollama", model="qwen3:8b") is None
        session.execute.assert_not_awaited()

    async def test_no_configured_provider_is_not_a_pricing_problem(self) -> None:
        """An instance that configures nothing keeps the registry's providers."""
        from src.infrastructure.provisioning.demo_llm import unbillable_model

        session = _session_with_price([])

        assert await unbillable_model(session, provider="", model="") is None
        session.execute.assert_not_awaited()

    async def test_a_misspelled_provider_is_not_reported_as_an_unpriced_model(self) -> None:
        """Two faults, two diagnoses.

        ``build_demo_overrides`` already refuses a provider this codebase does
        not know, with a message that lists the valid ones. Answering here
        would put "this model has no price" in front of an operator whose real
        mistake is a typo in the provider name — the invented diagnosis this
        codebase keeps removing.
        """
        from src.infrastructure.provisioning.demo_llm import unbillable_model

        session = _session_with_price([])

        assert await unbillable_model(session, provider="deepsek", model="deepseek-chat") is None
        session.execute.assert_not_awaited()


class TestProvisioningRefusesRatherThanArmingABlindCeiling:
    @staticmethod
    def _db_context(session: object) -> object:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _context():  # type: ignore[no-untyped-def]
            yield session

        return _context

    async def test_a_fresh_database_is_refused_when_the_model_has_no_price(self) -> None:
        from src.infrastructure.provisioning import demo_instance

        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=lambda: None,
                scalars=lambda: MagicMock(all=lambda: []),
            )
        )
        session.commit = AsyncMock()

        applied = AsyncMock(return_value=55)
        with (
            patch.object(demo_instance, "get_db_context", self._db_context(session)),
            patch.object(demo_instance, "apply_demo_llm_configuration", applied),
            patch.object(
                demo_instance, "unbillable_model", AsyncMock(return_value="deepseek-v4-flash")
            ),
            patch.object(demo_instance, "invalidate_setting_cache", AsyncMock()),
        ):
            report = await demo_instance.provision_demo_instance()

        assert report.refused_reason == "model_not_billable"
        assert report.unbillable_model == "deepseek-v4-flash"
        assert report.marker_written is False
        # Nothing was written: arming a nightly purge on an instance whose
        # spend it cannot measure is worse than not provisioning at all.
        applied.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_reprovisioning_a_marked_instance_is_refused_too(self) -> None:
        """The operator revisits the model here — that is exactly the risk."""
        from src.infrastructure.provisioning import demo_instance

        marker = MagicMock()
        marker.value = "true"
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=lambda: marker,
                scalars=lambda: MagicMock(all=lambda: []),
            )
        )
        session.commit = AsyncMock()

        applied = AsyncMock(return_value=55)
        with (
            patch.object(demo_instance, "get_db_context", self._db_context(session)),
            patch.object(demo_instance, "apply_demo_llm_configuration", applied),
            patch.object(
                demo_instance, "unbillable_model", AsyncMock(return_value="mystery-model")
            ),
            patch.object(demo_instance, "invalidate_setting_cache", AsyncMock()),
        ):
            report = await demo_instance.provision_demo_instance()

        assert report.refused_reason == "model_not_billable"
        applied.assert_not_awaited()

    async def test_the_refusal_tells_an_operator_what_to_do(self) -> None:
        from src.infrastructure.provisioning.demo_instance import ProvisionReport

        summary = ProvisionReport(
            refused_reason="model_not_billable", unbillable_model="deepseek-v4-flash"
        ).summary()

        assert "deepseek-v4-flash" in summary
        # A refusal an operator cannot act on is a wall, not a guard — and the
        # action must be one that WORKS here: telling them to apply the seed
        # bundle would send them into a gate that refuses it.
        assert "DEMO_INSTANCE_LLM_MODEL" in summary
        assert "APPLY_SEEDS" not in summary

    async def test_the_populated_database_refusal_still_reads_as_before(self) -> None:
        from src.infrastructure.provisioning.demo_instance import ProvisionReport

        summary = ProvisionReport(refused_reason="database_not_empty", account_count=7).summary()

        assert "7 account(s)" in summary
        assert "--force" in summary


class TestTheCliTurnsItIntoANonZeroExit:
    """Synchronous on purpose: ``main`` owns an ``asyncio.run``."""

    def test_a_refused_provisioning_exits_non_zero(self) -> None:
        from src.infrastructure.provisioning import cli
        from src.infrastructure.provisioning.demo_instance import ProvisionReport

        async def _refused(*, force: bool = False) -> ProvisionReport:
            return ProvisionReport(refused_reason="model_not_billable", unbillable_model="x")

        with (
            patch.object(cli, "provision_demo_instance", _refused),
            patch("src.infrastructure.database.registry.import_all_models"),
        ):
            assert cli.main([]) == 1

    def test_a_successful_provisioning_exits_zero(self) -> None:
        from src.infrastructure.provisioning import cli
        from src.infrastructure.provisioning.demo_instance import ProvisionReport

        async def _written(*, force: bool = False) -> ProvisionReport:
            return ProvisionReport(marker_written=True)

        with (
            patch.object(cli, "provision_demo_instance", _written),
            patch("src.infrastructure.database.registry.import_all_models"),
        ):
            assert cli.main([]) == 0


class TestAnOperatorCanInterrogateARunningInstance:
    """A ceiling nobody can ask about is a ceiling nobody trusts.

    ``--verify`` answers "can this instance measure what it spends" without
    writing anything: it is what ``task demo:verify`` calls next to its
    network-surface check, and what a runbook points at during an incident.
    """

    def test_verify_reports_and_exits_zero_when_the_model_is_priced(self) -> None:
        from src.infrastructure.provisioning import cli

        async def _priced(*, force: bool = False) -> None:
            raise AssertionError("--verify must never provision")

        with (
            patch.object(cli, "provision_demo_instance", _priced),
            patch.object(cli, "verify_spend_ceiling", _verifier(None)),
            patch("src.infrastructure.database.registry.import_all_models"),
        ):
            assert cli.main(["--verify"]) == 0

    def test_verify_exits_non_zero_when_the_ledger_would_stay_flat(self) -> None:
        from src.infrastructure.provisioning import cli

        with (
            patch.object(cli, "verify_spend_ceiling", _verifier("deepseek-v4-flash")),
            patch("src.infrastructure.database.registry.import_all_models"),
        ):
            assert cli.main(["--verify"]) == 1

    def test_verify_writes_nothing(self) -> None:
        """The check runs against a live instance: it must be read-only."""
        from src.infrastructure.provisioning import demo_instance

        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
        session.commit = AsyncMock()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _context():  # type: ignore[no-untyped-def]
            yield session

        configured = MagicMock()
        configured.demo_instance_llm_provider = "deepseek"
        configured.demo_instance_llm_model = "deepseek-v4-flash"

        with (
            patch.object(demo_instance, "get_db_context", _context),
            patch.object(demo_instance, "settings", configured),
        ):
            import asyncio

            unpriced = asyncio.run(demo_instance.verify_spend_ceiling())

        assert unpriced is not None
        session.add.assert_not_called()
        session.commit.assert_not_awaited()


def _verifier(result: str | None):  # type: ignore[no-untyped-def]
    async def _verify() -> str | None:
        return result

    return _verify
