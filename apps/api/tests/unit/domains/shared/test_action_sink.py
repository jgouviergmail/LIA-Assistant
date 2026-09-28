"""Recording an act a person asked for, without importing the register (ADR-263).

A share of an image with a connection (ADR-316) and a send by e-mail (ADR-321)
communicate to a third party at the person's click, outside any turn and
through no tool — so the gate that fills the action register never saw them,
and neither ever reached « Actions ». The domains that perform them cannot
import the register (``agents`` imports ``peers``), so the edge is inverted:
this seam holds the call, the register INSTALLS itself, and:

- **nothing in the seam imports anything** — a convenience import would put
  back the cycle the inversion took away;
- **the act is claimed BEFORE it happens and settled from its RESULT** — left
  unset, it settles as a failure, the safe direction;
- **an uninstalled seam records nothing and never raises** — a script or a
  narrow test keeps working;
- **and the boot refuses that silence** (ADR-270).
"""

from __future__ import annotations

import ast
import inspect
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.shared import action_sink
from src.domains.shared.action_sink import (
    EMAIL_SHARE_CAPABILITY,
    PEER_IMAGE_SHARE_CAPABILITY,
    action_recorder_is_installed,
    install_action_recorder,
    recorded_action,
)

pytestmark = pytest.mark.unit

USER = uuid.UUID("00000000-0000-4000-8000-0000000000a1")


@pytest.fixture(autouse=True)
def _restore_seam() -> Any:
    """Put the seam back exactly as it was: it is process-global state."""
    previous = action_sink._recorder
    yield
    action_sink._recorder = previous


class Recorder:
    """A register that says what it was asked."""

    def __init__(self, ticket: object | None = "ticket") -> None:
        self.ticket = ticket
        self.claimed: list[dict[str, Any]] = []
        self.settled: list[tuple[object | None, bool]] = []

    async def claim(self, *, user_id: Any, capability: str, arguments: dict[str, str]) -> Any:
        self.claimed.append({"user_id": user_id, "capability": capability, "arguments": arguments})
        return self.ticket

    async def settle(self, ticket: object | None, *, succeeded: bool) -> None:
        self.settled.append((ticket, succeeded))


class TestTheSeamImportsNothing:
    def test_the_module_has_no_import_at_all(self) -> None:
        tree = ast.parse(inspect.getsource(action_sink))
        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            and not (isinstance(node, ast.ImportFrom) and node.module in {"__future__", "typing"})
        ]
        assert imports == []


class TestWithNothingInstalled:
    async def test_the_act_happens_and_nothing_is_recorded(self) -> None:
        action_sink._recorder = action_sink._IGNORE
        assert action_recorder_is_installed() is False

        async with recorded_action(
            user_id=USER, capability=EMAIL_SHARE_CAPABILITY, arguments={}
        ) as action:
            action.succeeded = True  # nothing to settle, nothing raised


class TestOnceInstalled:
    async def test_the_act_is_claimed_first_and_settled_from_its_result(self) -> None:
        recorder = Recorder()
        install_action_recorder(recorder)
        order: list[str] = []

        async with recorded_action(
            user_id=USER, capability=PEER_IMAGE_SHARE_CAPABILITY, arguments={"count": "1"}
        ) as action:
            order.append(f"act after {len(recorder.claimed)} claim")
            action.succeeded = True

        assert order == ["act after 1 claim"]
        assert recorder.claimed == [
            {"user_id": USER, "capability": "peer_image_share", "arguments": {"count": "1"}}
        ]
        assert recorder.settled == [("ticket", True)]
        assert action_recorder_is_installed() is True

    async def test_an_act_that_never_said_it_succeeded_settles_as_a_failure(self) -> None:
        recorder = Recorder()
        install_action_recorder(recorder)

        with pytest.raises(RuntimeError):
            async with recorded_action(
                user_id=USER, capability=EMAIL_SHARE_CAPABILITY, arguments={}
            ):
                raise RuntimeError("the provider refused")

        assert recorder.settled == [("ticket", False)]

    async def test_a_refused_claim_still_lets_the_act_happen(self) -> None:
        """The register never costs the person their act."""
        recorder = Recorder(ticket=None)
        install_action_recorder(recorder)

        async with recorded_action(
            user_id=USER, capability=EMAIL_SHARE_CAPABILITY, arguments={}
        ) as action:
            action.succeeded = True

        assert recorder.settled == [(None, True)]


class TestTheBoot:
    def test_the_boot_calls_the_step(self) -> None:
        from pathlib import Path

        source = Path("src/infrastructure/startup/registries.py").read_text(encoding="utf-8")
        assert "_install_action_recorder()" in source

    def test_the_step_installs_the_register(self) -> None:
        from src.infrastructure.startup.registries import _install_action_recorder

        action_sink._recorder = action_sink._IGNORE
        _install_action_recorder()
        assert action_recorder_is_installed() is True

    def test_it_refuses_to_boot_on_a_seam_nobody_claimed(self) -> None:
        from src.infrastructure.startup.registries import _install_action_recorder

        with patch(
            "src.domains.shared.action_sink.action_recorder_is_installed", return_value=False
        ):
            with pytest.raises(RuntimeError, match="action"):
                _install_action_recorder()


class TestTheRegistersRecorder:
    """What the installed implementation owes ADR-263."""

    async def test_it_claims_the_persons_act_under_its_capability(self) -> None:
        from src.domains.agents.effects.out_of_turn_effects import USER_ACTION_RECORDER

        claim = AsyncMock(return_value="ticket")
        with patch("src.domains.agents.effects.runtime._LEDGER.claim", claim):
            ticket = await USER_ACTION_RECORDER.claim(
                user_id=USER, capability=EMAIL_SHARE_CAPABILITY, arguments={"count": "2"}
            )

        request = claim.await_args.args[0]
        assert ticket == "ticket"
        assert request.source == "user", "« À ta demande »: the person clicked"
        assert request.mutation_policy == "confirm", "it communicates to a third party"
        assert request.execution_mode == "direct"
        assert request.tool_name == "email_share"
        assert request.run_id.startswith("email_share_")
        assert request.thread_id == request.run_id
        assert request.idempotency_key == f"{request.run_id}:email_share"
        assert request.label == {
            "i18n_key": "effects.labels.email_share",
            "values": {"count": "2"},
        }

    async def test_two_acts_are_two_rows(self) -> None:
        from src.domains.agents.effects.out_of_turn_effects import USER_ACTION_RECORDER

        claim = AsyncMock(return_value="ticket")
        with patch("src.domains.agents.effects.runtime._LEDGER.claim", claim):
            for _ in range(2):
                await USER_ACTION_RECORDER.claim(
                    user_id=USER, capability=PEER_IMAGE_SHARE_CAPABILITY, arguments={}
                )

        keys = {call.args[0].idempotency_key for call in claim.await_args_list}
        assert len(keys) == 2

    async def test_a_capability_nobody_declared_is_refused(self) -> None:
        from src.domains.agents.effects.out_of_turn_effects import USER_ACTION_RECORDER

        claim = AsyncMock(return_value="ticket")
        with patch("src.domains.agents.effects.runtime._LEDGER.claim", claim):
            ticket = await USER_ACTION_RECORDER.claim(
                user_id=USER, capability="anything", arguments={}
            )

        assert ticket is None
        claim.assert_not_awaited()

    async def test_a_ledger_that_fails_answers_no_ticket(self) -> None:
        from src.domains.agents.effects.out_of_turn_effects import USER_ACTION_RECORDER

        claim = AsyncMock(side_effect=RuntimeError("down"))
        with patch("src.domains.agents.effects.runtime._LEDGER.claim", claim):
            ticket = await USER_ACTION_RECORDER.claim(
                user_id=USER, capability=EMAIL_SHARE_CAPABILITY, arguments={}
            )

        assert ticket is None

    async def test_it_settles_from_the_result(self) -> None:
        from src.domains.agents.effects.out_of_turn_effects import USER_ACTION_RECORDER

        class Ticket:
            effect_id = uuid.uuid4()
            claim_token = uuid.uuid4()

        close = AsyncMock()
        with patch("src.domains.agents.effects.runtime._LEDGER.close", close):
            await USER_ACTION_RECORDER.settle(Ticket(), succeeded=False)
            await USER_ACTION_RECORDER.settle(None, succeeded=True)  # nothing was claimed

        assert close.await_count == 1
        assert close.await_args.kwargs["outcome"].succeeded is False
