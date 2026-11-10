"""The boot wires what habits reads and does, and refuses an incomplete wiring (ADR-375).

Two registries other domains fill: the usage ports (facts ``agents`` and
``heartbeat`` own) and the proposal handlers (two of them ``heartbeat`` owns).
"""

from __future__ import annotations

import ast
import inspect

import pytest

from src.domains.habits import proposal_actions, usage_ports
from src.domains.habits.models import ProposalKind
from src.infrastructure.startup import registries
from src.infrastructure.startup.errors import StartupCompletenessError

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolated_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(usage_ports, "_PORTS", usage_ports._Ports())
    monkeypatch.setattr(proposal_actions, "_ACTIONS", {})


def test_the_boot_declares_both_ports() -> None:
    registries._install_habit_usage_ports()
    assert usage_ports.routine_reads_reader() is not None
    assert usage_ports.proactive_feedback_reader() is not None


def test_the_boot_installs_every_proposal_handler() -> None:
    registries._install_habit_usage_ports()
    assert set(proposal_actions.installed_proposal_actions()) == set(ProposalKind)


def test_the_boot_refuses_a_kind_nobody_carries_out(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.domains.heartbeat import proposal_handlers

    monkeypatch.setattr(proposal_handlers, "install", lambda: None)
    with pytest.raises(StartupCompletenessError, match="review_notifications"):
        registries._install_habit_usage_ports()


def test_the_boot_refuses_an_undecided_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.domains.agents.registry import domain_taxonomy

    monkeypatch.setitem(domain_taxonomy.DOMAIN_REGISTRY, "brand_new", object())  # type: ignore[arg-type]
    with pytest.raises(StartupCompletenessError, match="brand_new"):
        registries._install_habit_usage_ports()


def test_the_step_runs_in_the_registry_boot_segment() -> None:
    """Declared AND called: a step nobody calls guards nothing."""
    called = {
        node.func.id
        for node in ast.walk(ast.parse(inspect.getsource(registries)))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_install_habit_usage_ports" in called
