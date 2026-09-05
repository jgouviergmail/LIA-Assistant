"""The boot refuses a catalogue that does not say what its tools owe (ADR-263).

``assert_mutation_policy_completeness`` is only useful if the application
actually refuses to start on it — an assert nobody calls is a comment. This
pins the wiring: the guard runs inside ``init_agent_registry``, right after the
catalogue is loaded (the manifests only become checkable there), and its
``AssertionError`` is surfaced as a ``RuntimeError`` that stops the lifespan,
exactly like the two guards it sits behind.

The store is patched at its source module (``domains.agents.context``): the
startup step imports it INSIDE the function, so patching an attribute of
``startup.agents`` would rebind nothing and the test would open a real
PostgreSQL connection — a unit test must not.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.startup import agents as startup_agents
from src.infrastructure.startup.errors import StartupCompletenessError

pytestmark = [pytest.mark.unit]


@pytest.fixture
def scheduler() -> MagicMock:
    """An APScheduler double: the browser cleanup job is registered on it."""
    return MagicMock()


@pytest.fixture
def no_store() -> object:
    """Neutralise the AsyncPostgresStore acquisition for the whole boot step."""
    return patch(
        "src.domains.agents.context.get_tool_context_store",
        AsyncMock(return_value=None),
    )


async def test_boot_refuses_a_catalogue_missing_a_policy(
    scheduler: MagicMock, no_store: object
) -> None:
    """A manifest that declares no policy stops the boot with a named error."""
    with (
        no_store,  # type: ignore[attr-defined]
        patch(
            "src.domains.agents.registry.catalogue.assert_mutation_policy_completeness",
            side_effect=AssertionError("declare no mutation_policy: x_tool"),
        ),
        pytest.raises(RuntimeError, match="Mutation policy registry incomplete"),
    ):
        await startup_agents.init_agent_registry(None, scheduler)


async def test_boot_populates_the_executor_registry_before_asserting(
    scheduler: MagicMock, no_store: object
) -> None:
    """Two boot asserts read the executor registry — it must not be empty.

    Measured 2026-09-04: the draft executors register LAZILY, on the first use
    of ``DraftExecutor``, so at assert time the registry held ZERO entries and
    the executor half of both guards passed on anything. An assert that cannot
    fail is worse than no assert: it is a promise nobody checks.
    """
    from src.domains.agents.services.draft_executor_types import EXECUTOR_REGISTRY

    EXECUTOR_REGISTRY.clear()
    seen: list[int] = []

    def _record() -> None:
        seen.append(len(EXECUTOR_REGISTRY))

    with (
        no_store,  # type: ignore[attr-defined]
        patch(
            "src.domains.agents.effects.runtime.assert_effect_gate_completeness",
            side_effect=_record,
        ),
        patch(
            "src.domains.agents.effects.labels.assert_effect_label_completeness",
            side_effect=_record,
        ),
    ):
        await startup_agents.init_agent_registry(None, scheduler)

    assert seen, "the guards did not run at boot"
    assert all(
        count > 15 for count in seen
    ), f"an assert ran against an empty-ish executor registry: {seen}"


async def test_boot_refuses_an_unlabelled_capability(
    scheduler: MagicMock, no_store: object
) -> None:
    """A capability that can act but cannot say what it did stops the boot."""
    with (
        no_store,  # type: ignore[attr-defined]
        patch(
            "src.domains.agents.effects.labels.assert_effect_label_completeness",
            side_effect=AssertionError("no label builder: x_tool"),
        ),
        pytest.raises(RuntimeError, match="Effect labels incomplete"),
    ):
        await startup_agents.init_agent_registry(None, scheduler)


async def test_boot_refuses_an_unnameable_consultation(
    scheduler: MagicMock, no_store: object
) -> None:
    """A capability a register could only show as a tool name stops the boot.

    The consultation register has no other alarm: nothing fails, nothing is
    logged, a user simply reads ``get_calls_tool`` in their own journal.
    """
    with (
        no_store,  # type: ignore[attr-defined]
        patch(
            "src.domains.agents.effects.treatment_labels." "assert_treatment_domain_completeness",
            side_effect=AssertionError("no readable domain: x_tool"),
        ),
        pytest.raises(RuntimeError, match="Treatment domains incomplete"),
    ):
        await startup_agents.init_agent_registry(None, scheduler)


async def test_boot_succeeds_on_the_real_catalogue(scheduler: MagicMock, no_store: object) -> None:
    """The production catalogue satisfies the guards — no startup regression.

    This is the half that matters most: a guard that refuses the real catalogue
    would be a guard that stops production, which is the defect it exists to
    prevent, pointing the other way.

    The executor registry is repopulated from the production path first: other
    suites legitimately swap an executor for a double (``patch.dict``), and a
    double is not gated — asserting over whatever they left behind would make
    this test fail for a reason that has nothing to do with the boot.
    """
    from src.domains.agents.services.draft_executor_registry import (
        ensure_executors_registered,
    )
    from src.domains.agents.services.draft_executor_types import EXECUTOR_REGISTRY

    EXECUTOR_REGISTRY.clear()
    ensure_executors_registered()

    with no_store:  # type: ignore[attr-defined]
        registry = await startup_agents.init_agent_registry(None, scheduler)
    assert registry is not None
    assert registry.list_tool_manifests()


class TestTheBootActuallyRefuses:
    """The promise the three older guards made and the code did not keep.

    Measured 2026-09-03: ``init_agent_registry`` caught ``RuntimeError`` and
    only logged, so a completeness failure let the boot continue —
    ``set_global_registry`` was never reached and ``get_global_registry()``
    lazily built an EMPTY registry. The instance came up with no catalogue at
    all, announced by one ERROR line. ``StartupCompletenessError`` restores the
    promise without losing the resilience the broad handler exists for.
    """

    async def test_a_completeness_failure_propagates(
        self, scheduler: MagicMock, no_store: object
    ) -> None:
        with (
            no_store,  # type: ignore[attr-defined]
            patch(
                "src.domains.agents.registry.catalogue.assert_tool_category_completeness",
                side_effect=AssertionError("x_tool"),
            ),
            pytest.raises(StartupCompletenessError),
        ):
            await startup_agents.init_agent_registry(None, scheduler)

    async def test_an_unrelated_runtime_error_is_still_survived(self, scheduler: MagicMock) -> None:
        """No resilience regression: a transport that will not open still only logs."""
        with patch(
            "src.domains.agents.context.get_tool_context_store",
            AsyncMock(side_effect=RuntimeError("store transport unavailable")),
        ):
            registry = await startup_agents.init_agent_registry(None, scheduler)
        assert registry is None  # construction never happened, and the boot went on

    async def test_the_completeness_error_is_a_runtime_error(self) -> None:
        """Subclassing keeps every existing ``except RuntimeError`` shape valid."""
        assert issubclass(StartupCompletenessError, RuntimeError)
