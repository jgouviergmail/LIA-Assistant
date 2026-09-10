"""Notifying without importing what notifies (ADR-276, ADR-263, ADR-270).

The seam exists to invert one edge: the dispatcher imports ``agents``, and
``agents`` imports ``workboard``, so a domain reaching for the dispatcher would
close a runtime cycle. What matters is therefore not only that the seam works
but that it CANNOT be bypassed and cannot go quiet:

- **nothing in the seam imports anything** — checked over its own AST, because
  a single convenience import would put the cycle back exactly where the
  inversion took it from;
- **an uninstalled seam answers False rather than raising**, so a probe or a
  narrow test keeps working;
- **and the boot refuses that silence**. ADR-270 measured the alternative on
  the consultation register: a no-op along the exact path a sweep used, with no
  signal anywhere.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.shared import proactive_sink
from src.domains.shared.proactive_sink import (
    install_proactive_notifier,
    notifier_is_installed,
    send_proactive_notification,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _restore_seam() -> Any:
    """Put the seam back exactly as it was: it is process-global state."""
    previous = proactive_sink._notifier
    yield
    proactive_sink._notifier = previous


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "db": MagicMock(),
        "user": MagicMock(),
        "content": "A ticket has been handed to you.",
        "task_type": "workboard",
        "target_id": "t-1",
        "metadata": {"event": "assigned"},
        "run_id": "r-1",
    }
    payload.update(overrides)
    return payload


class TestTheSeamImportsNothing:
    def test_the_module_has_no_import_at_all(self) -> None:
        """One convenience import would put back the cycle the inversion took
        away — and the coupling ratchet counts local imports too, so hiding it
        inside a function would only hide the edge."""
        tree = ast.parse(inspect.getsource(proactive_sink))
        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            # `from __future__` and `typing` carry no runtime dependency.
            and not (isinstance(node, ast.ImportFrom) and node.module in {"__future__", "typing"})
        ]
        assert imports == []


class TestWithNothingInstalled:
    def test_it_answers_that_nobody_was_reached(self) -> None:
        """A probe, a script or a narrow test has no dispatcher; raising there
        would turn an observability concern into an outage."""
        proactive_sink._notifier = proactive_sink._ignore

        assert notifier_is_installed() is False

    async def test_the_call_is_a_no_op_rather_than_an_error(self) -> None:
        proactive_sink._notifier = proactive_sink._ignore

        assert await send_proactive_notification(**_payload()) is False


class TestOnceInstalled:
    async def test_every_field_reaches_the_dispatcher_by_name(self) -> None:
        """A seam accepting ``**Any`` would let a caller misspell one and send
        a notification with a missing piece."""
        notifier = AsyncMock(return_value=True)
        install_proactive_notifier(notifier)

        delivered = await send_proactive_notification(
            **_payload(run_id="r-9", title="Board", occurrence="run_started")
        )

        assert delivered is True
        assert notifier_is_installed() is True
        call = notifier.await_args.kwargs
        assert call["task_type"] == "workboard"
        assert call["target_id"] == "t-1"
        assert call["metadata"] == {"event": "assigned"}
        assert call["run_id"] == "r-9"
        assert call["title"] == "Board"
        assert call["occurrence"] == "run_started"

    async def test_an_act_names_its_run_or_is_refused(self) -> None:
        """The run is the sweep's, or the act's own (a ticket event): the
        registers join on it. A default would file rows under a placeholder —
        the adapter used to substitute the target id in silence."""
        install_proactive_notifier(AsyncMock(return_value=True))
        payload = _payload()
        payload.pop("run_id")

        with pytest.raises(TypeError):
            await send_proactive_notification(**payload)

    async def test_a_dispatch_that_reached_nobody_reads_as_such(self) -> None:
        install_proactive_notifier(AsyncMock(return_value=False))

        assert await send_proactive_notification(**_payload()) is False


class TestTheAdapter:
    """What the seam's installed implementation owes ADR-263."""

    @staticmethod
    def _effect() -> tuple[Any, Any]:
        from contextlib import asynccontextmanager

        effect = MagicMock()

        @asynccontextmanager
        async def claim(**_kwargs: Any) -> Any:
            yield effect

        return effect, claim

    async def test_it_claims_before_sending_and_settles_from_the_result(self) -> None:
        from src.infrastructure.proactive.notification_sink import (
            dispatch_proactive_notification,
        )

        effect, claim = self._effect()
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock(return_value=MagicMock(success=True))

        with (
            patch(
                "src.infrastructure.proactive.notification.NotificationDispatcher",
                return_value=dispatcher,
            ),
            patch(
                "src.domains.agents.effects.out_of_turn_effects.proactive_notification_effect",
                claim,
            ),
        ):
            delivered = await dispatch_proactive_notification(**_payload())

        assert delivered is True
        assert effect.delivered is True

    async def test_the_occurrence_reaches_the_claim(self) -> None:
        """What a run says twice is claimed twice (ADR-276): the adapter hands
        the claim the run AND which of its notifications this is."""
        from contextlib import asynccontextmanager

        from src.infrastructure.proactive.notification_sink import (
            dispatch_proactive_notification,
        )

        seen: dict[str, Any] = {}

        @asynccontextmanager
        async def claim(**kwargs: Any) -> Any:
            seen.update(kwargs)
            yield MagicMock()

        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock(return_value=MagicMock(success=True))
        with (
            patch(
                "src.infrastructure.proactive.notification.NotificationDispatcher",
                return_value=dispatcher,
            ),
            patch(
                "src.domains.agents.effects.out_of_turn_effects.proactive_notification_effect",
                claim,
            ),
        ):
            await dispatch_proactive_notification(
                **_payload(run_id="r-9", occurrence="run_finished")
            )

        assert seen["run_id"] == "r-9"
        assert seen["occurrence"] == "run_finished"
        assert seen["task_type"] == "workboard"

    async def test_a_dispatch_that_reached_no_channel_is_not_a_delivery(self) -> None:
        """Never the absence of an exception: a dispatch that reached nobody is
        a notification nobody got."""
        from src.infrastructure.proactive.notification_sink import (
            dispatch_proactive_notification,
        )

        effect, claim = self._effect()
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock(return_value=MagicMock(success=False))

        with (
            patch(
                "src.infrastructure.proactive.notification.NotificationDispatcher",
                return_value=dispatcher,
            ),
            patch(
                "src.domains.agents.effects.out_of_turn_effects.proactive_notification_effect",
                claim,
            ),
        ):
            delivered = await dispatch_proactive_notification(**_payload())

        assert delivered is False
        assert effect.delivered is False

    async def test_a_broken_dispatcher_never_undoes_a_durable_write(self) -> None:
        """The caller has already settled a ticket or accepted an assignment;
        a notification that cannot leave must not raise into that."""
        from src.infrastructure.proactive.notification_sink import (
            dispatch_proactive_notification,
        )

        _effect, claim = self._effect()
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock(side_effect=RuntimeError("redis is gone"))

        with (
            patch(
                "src.infrastructure.proactive.notification.NotificationDispatcher",
                return_value=dispatcher,
            ),
            patch(
                "src.domains.agents.effects.out_of_turn_effects.proactive_notification_effect",
                claim,
            ),
        ):
            assert await dispatch_proactive_notification(**_payload()) is False


class TestTheBootRefusesASilentSeam:
    def test_importing_the_adapter_is_what_installs_it(self) -> None:
        """The wiring IS the import — reloaded here so the side effect really
        runs rather than being satisfied by a module another test imported."""
        import importlib

        import src.infrastructure.proactive.notification_sink as adapter

        proactive_sink._notifier = proactive_sink._ignore
        assert notifier_is_installed() is False

        importlib.reload(adapter)

        assert notifier_is_installed() is True

    def test_the_boot_actually_calls_the_step(self) -> None:
        """A step nobody calls is the same silence as no step at all — and it
        is the one thing a test of the step itself cannot show."""
        from src.infrastructure.startup import registries

        tree = ast.parse(inspect.getsource(registries))
        called_in = {
            parent.name
            for parent in ast.walk(tree)
            if isinstance(parent, ast.FunctionDef)
            for node in ast.walk(parent)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_install_proactive_notifier"
        }
        assert called_in, "the declared step is never called"
        # Beside the seam it mirrors: both are wiring the boot owes.
        assert any(
            "_install_consultation_sink" in ast.dump(node)
            for name in called_in
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        )

    def test_it_refuses_to_boot_on_a_seam_nobody_claimed(self) -> None:
        """ADR-270's lesson, applied before it can cost anything: an import
        side effect nobody declares is one a reorder can stop performing."""
        from src.infrastructure.startup import registries

        with (
            patch.object(registries, "__name__", registries.__name__),
            patch(
                "src.domains.shared.proactive_sink.notifier_is_installed",
                return_value=False,
            ),
            pytest.raises(RuntimeError, match="did not claim its seam"),
        ):
            registries._install_proactive_notifier()
