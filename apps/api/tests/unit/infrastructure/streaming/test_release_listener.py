"""The release seam is claimed at boot and hands each release outside the ended run."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from src.core.conversation_execution import ExecutionKind, RunAdmission, RunEnd
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.run_authority import RunAuthority, current_run_authority, run_authority_scope
from src.infrastructure.streaming import release_listener

pytestmark = pytest.mark.unit


def test_the_boot_step_installs_the_departure(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.domains.agents.api.waiting_departure import depart_after_release
    from src.infrastructure.startup.registries import _install_release_listener

    monkeypatch.setattr(release_listener, "_listener", None)
    _install_release_listener()
    assert release_listener._listener is depart_after_release


def test_the_boot_refuses_a_seam_nobody_claimed() -> None:
    from src.infrastructure.startup.registries import _install_release_listener

    with (
        patch(
            "src.infrastructure.streaming.release_listener.release_listener_installed",
            return_value=False,
        ),
        pytest.raises(RuntimeError, match="release seam"),
    ):
        _install_release_listener()


def test_the_registry_step_calls_the_installation() -> None:
    tree = ast.parse(Path("src/infrastructure/startup/registries.py").read_text(encoding="utf-8"))
    callers = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_install_release_listener"
    }
    siblings = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_install_ticket_releaser"
    }
    assert callers and callers == siblings


async def test_a_release_is_heard_outside_the_run_that_ended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heard: list[tuple[UUID, RunEnd, RunAuthority | None]] = []
    done = asyncio.Event()

    async def listener(owner_id: UUID, end: RunEnd) -> None:
        heard.append((owner_id, end, current_run_authority()))
        done.set()

    monkeypatch.setattr(release_listener, "_listener", listener)
    owner = uuid4()
    target = ConversationRef(owner, uuid4(), ConversationKind.MAIN, 0, uuid4())
    admission = RunAdmission(
        uuid4(), target, ExecutionKind.GRAPH, "run", "stream", uuid4(), uuid4(), 1, False
    )
    with run_authority_scope(RunAuthority(admission)):
        release_listener.announce_release(owner, RunEnd.NORMAL)
    async with asyncio.timeout(5):
        await done.wait()
    assert heard == [(owner, RunEnd.NORMAL, None)]


def test_a_release_with_no_listener_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_listener, "_listener", None)
    release_listener.announce_release(uuid4(), RunEnd.INTERRUPTED)
    assert not release_listener.release_listener_installed()
