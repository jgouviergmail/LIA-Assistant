"""Facts other domains own, offered to habits through named ports (ADR-375)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest

from src.domains.habits import usage_ports
from src.domains.habits.proposal_rules import ProactiveFeedback

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolated_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(usage_ports, "_PORTS", usage_ports._Ports())


async def _reads(db: Any, user_id: UUID, run_ids: Sequence[str]) -> Mapping[str, frozenset[str]]:
    return {}


async def _feedback(db: Any, user_id: UUID, since: datetime) -> ProactiveFeedback:
    return ProactiveFeedback(sent=0, reacted=0)


def test_an_uninstalled_port_is_absent_never_a_default() -> None:
    assert usage_ports.routine_reads_reader() is None
    assert usage_ports.proactive_feedback_reader() is None


def test_installed_ports_are_read_back() -> None:
    usage_ports.install_routine_reads_reader(_reads)
    usage_ports.install_proactive_feedback_reader(_feedback)
    assert usage_ports.routine_reads_reader() is _reads
    assert usage_ports.proactive_feedback_reader() is _feedback


def test_the_boot_refuses_a_missing_port() -> None:
    usage_ports.install_routine_reads_reader(_reads)
    with pytest.raises(AssertionError, match="proactive_feedback"):
        usage_ports.assert_usage_ports_installed()


def test_the_boot_accepts_both_ports() -> None:
    usage_ports.install_routine_reads_reader(_reads)
    usage_ports.install_proactive_feedback_reader(_feedback)
    usage_ports.assert_usage_ports_installed()
