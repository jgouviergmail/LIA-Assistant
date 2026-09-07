"""A notification LIA decided to send is an ACTION, and it is recorded.

Reported from production, 2026-09-07: a proactive notification arrived and
« Actions menées d'elle-même » showed nothing. It was not a filter defect —
``agent_effects`` had never held a single ``proactive`` row, on any deployment,
because the effect register is fed by the tool gate alone and the proactive
pipeline calls no tool.

So the tab was empty BY CONSTRUCTION, and would have stayed empty however many
notifications LIA sent. That is the sharpest possible version of the gap this
whole programme exists to close: a notification is the one act of LIA's own
initiative a person actually experiences.

The oracles below are ADR-263's two stages, on the path that now claims them.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.effects.out_of_turn_effects import (
    NOTIFICATION_CAPABILITY,
    NOTIFICATION_POLICY,
    proactive_notification_effect,
)

pytestmark = pytest.mark.unit


class _Ticket:
    effect_id = uuid.uuid4()
    claim_token = uuid.uuid4()


def _ledger(claim_returns: object = _Ticket()) -> tuple[AsyncMock, AsyncMock]:
    """Patch the ledger's two doors and hand them back."""
    return AsyncMock(return_value=claim_returns), AsyncMock()


class TestTheNotificationIsClaimedBeforeItLeaves:
    """A claim written afterwards is lost by the crash it exists to survive."""

    async def test_the_claim_is_taken_before_the_body_runs(self) -> None:
        claim, close = _ledger()
        order: list[str] = []
        claim.side_effect = lambda _r: order.append("claim") or _Ticket()

        with (
            patch("src.domains.agents.effects.runtime._LEDGER.claim", claim),
            patch("src.domains.agents.effects.runtime._LEDGER.close", close),
        ):
            async with proactive_notification_effect(
                user_id=uuid.uuid4(), run_id="sweep-1", task_type="heartbeat"
            ):
                order.append("dispatch")

        assert order == ["claim", "dispatch"]

    async def test_the_row_says_LIA_decided_it(self) -> None:
        claim, close = _ledger()
        with (
            patch("src.domains.agents.effects.runtime._LEDGER.claim", claim),
            patch("src.domains.agents.effects.runtime._LEDGER.close", close),
        ):
            async with proactive_notification_effect(
                user_id=uuid.uuid4(), run_id="sweep-2", task_type="heartbeat"
            ) as effect:
                effect.delivered = True

        request = claim.await_args.args[0]
        assert request.source == "proactive", "the tab filters on this exact value"
        assert request.tool_name == NOTIFICATION_CAPABILITY
        assert request.mutation_policy == NOTIFICATION_POLICY
        assert request.execution_mode == "direct"

    async def test_the_run_id_joins_the_three_registers(self) -> None:
        """The same key the sweep's consultations and its decision carry."""
        claim, close = _ledger()
        with (
            patch("src.domains.agents.effects.runtime._LEDGER.claim", claim),
            patch("src.domains.agents.effects.runtime._LEDGER.close", close),
        ):
            async with proactive_notification_effect(
                user_id=uuid.uuid4(), run_id="proactive_heartbeat_abc", task_type="heartbeat"
            ):
                pass

        request = claim.await_args.args[0]
        assert request.run_id == "proactive_heartbeat_abc"
        assert request.thread_id == "proactive_heartbeat_abc"

    async def test_one_sweep_claims_one_notification(self) -> None:
        """A retry must not add a second « LIA notified you » to the register."""
        claim, close = _ledger()
        with (
            patch("src.domains.agents.effects.runtime._LEDGER.claim", claim),
            patch("src.domains.agents.effects.runtime._LEDGER.close", close),
        ):
            for _ in range(2):
                async with proactive_notification_effect(
                    user_id=uuid.uuid4(), run_id="sweep-3", task_type="heartbeat"
                ):
                    pass

        keys = {call.args[0].idempotency_key for call in claim.await_args_list}
        assert keys == {"sweep-3:notification"}

    async def test_the_label_carries_the_sweep_and_no_user_text(self) -> None:
        claim, close = _ledger()
        with (
            patch("src.domains.agents.effects.runtime._LEDGER.claim", claim),
            patch("src.domains.agents.effects.runtime._LEDGER.close", close),
        ):
            async with proactive_notification_effect(
                user_id=uuid.uuid4(), run_id="sweep-4", task_type="interest"
            ):
                pass

        label = claim.await_args.args[0].label
        assert label["i18n_key"] == f"effects.labels.{NOTIFICATION_CAPABILITY}"
        assert label["values"] == {"kind": "interest"}


class TestTheRowIsClosedFromAnExplicitResult:
    """Absence of an exception is not proof of delivery (ADR-263)."""

    async def test_a_delivered_notification_closes_as_a_success(self) -> None:
        claim, close = _ledger()
        with (
            patch("src.domains.agents.effects.runtime._LEDGER.claim", claim),
            patch("src.domains.agents.effects.runtime._LEDGER.close", close),
        ):
            async with proactive_notification_effect(
                user_id=uuid.uuid4(), run_id="sweep-5", task_type="heartbeat"
            ) as effect:
                effect.delivered = True

        assert close.await_args.kwargs["outcome"].succeeded is True

    async def test_a_dispatch_that_reached_nobody_closes_as_a_failure(self) -> None:
        claim, close = _ledger()
        with (
            patch("src.domains.agents.effects.runtime._LEDGER.claim", claim),
            patch("src.domains.agents.effects.runtime._LEDGER.close", close),
        ):
            async with proactive_notification_effect(
                user_id=uuid.uuid4(), run_id="sweep-6", task_type="heartbeat"
            ) as effect:
                effect.delivered = False

        assert close.await_args.kwargs["outcome"].succeeded is False

    async def test_a_caller_that_says_nothing_closes_as_a_failure(self) -> None:
        """The safe direction: an act that may not have landed is not « done »."""
        claim, close = _ledger()
        with (
            patch("src.domains.agents.effects.runtime._LEDGER.claim", claim),
            patch("src.domains.agents.effects.runtime._LEDGER.close", close),
        ):
            async with proactive_notification_effect(
                user_id=uuid.uuid4(), run_id="sweep-7", task_type="heartbeat"
            ):
                pass

        assert close.await_args.kwargs["outcome"].succeeded is False

    async def test_a_raising_dispatch_still_closes_the_row(self) -> None:
        """A crash mid-send must not leave a claim open for ever."""
        claim, close = _ledger()
        with (
            patch("src.domains.agents.effects.runtime._LEDGER.claim", claim),
            patch("src.domains.agents.effects.runtime._LEDGER.close", close),
            pytest.raises(RuntimeError),
        ):
            async with proactive_notification_effect(
                user_id=uuid.uuid4(), run_id="sweep-8", task_type="heartbeat"
            ):
                raise RuntimeError("fcm exploded")

        assert close.await_count == 1
        assert close.await_args.kwargs["outcome"].succeeded is False


class TestTheRegisterNeverCostsTheNotification:
    """Observing must never break the observed."""

    async def test_a_ledger_that_cannot_claim_lets_the_notification_through(self) -> None:
        claim = AsyncMock(side_effect=RuntimeError("ledger down"))
        with patch("src.domains.agents.effects.runtime._LEDGER.claim", claim):
            async with proactive_notification_effect(
                user_id=uuid.uuid4(), run_id="sweep-9", task_type="heartbeat"
            ) as effect:
                effect.delivered = True

    async def test_nothing_is_closed_when_nothing_was_claimed(self) -> None:
        claim = AsyncMock(return_value=None)
        close = AsyncMock()
        with (
            patch("src.domains.agents.effects.runtime._LEDGER.claim", claim),
            patch("src.domains.agents.effects.runtime._LEDGER.close", close),
        ):
            async with proactive_notification_effect(
                user_id=uuid.uuid4(), run_id="sweep-10", task_type="heartbeat"
            ) as effect:
                effect.delivered = True

        assert close.await_count == 0

    async def test_a_ledger_that_cannot_close_never_raises(self) -> None:
        claim, _ = _ledger()
        close = AsyncMock(side_effect=RuntimeError("ledger down"))
        with (
            patch("src.domains.agents.effects.runtime._LEDGER.claim", claim),
            patch("src.domains.agents.effects.runtime._LEDGER.close", close),
        ):
            async with proactive_notification_effect(
                user_id=uuid.uuid4(), run_id="sweep-11", task_type="heartbeat"
            ) as effect:
                effect.delivered = True


class TestTheWordingExistsWhereverItIsRead:
    """A register that shows a raw key has failed at its one job."""

    def test_the_label_is_worded_in_all_six_languages(self) -> None:
        import json
        from pathlib import Path

        locales = Path(__file__).resolve().parents[6] / "web" / "locales"
        for language in ("en", "fr", "de", "es", "it", "zh"):
            bundle = json.loads((locales / language / "translation.json").read_text("utf-8"))
            wording = bundle["effects"]["labels"].get(NOTIFICATION_CAPABILITY)
            assert wording, f"no wording in {language}"
            assert "{{kind}}" in wording, f"{language} drops the sweep that decided"
