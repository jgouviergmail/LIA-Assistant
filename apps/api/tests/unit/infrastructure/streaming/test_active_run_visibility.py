"""SQL occupancy names only transports and cancellation that actually exist.

Actual status/cancel/reattach routes are exercised against PostgreSQL and Redis
in test_chat_http_admission. The retired Redis lease cannot confer authority.
"""

import ast
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.conversation_execution import ExecutionKind, ExecutionPhase, RunBusy
from src.core.conversation_target import ConversationKind, ConversationRef
from src.domains.agents.api.run_schemas import ActiveRunResponse

pytestmark = pytest.mark.unit
RETIRED = {
    "active_run_lease",
    "register_active_run",
    "heartbeat_active_run",
    "public_active_run",
    "active_run_key",
    "ActiveRunLockLost",
}


@pytest.mark.parametrize("phase", list(ExecutionPhase))
@pytest.mark.parametrize("relayed,cancellable", [(False, False), (False, True), (True, True)])
def test_only_a_live_offered_transport_can_be_followed_or_stopped(
    phase: ExecutionPhase, relayed: bool, cancellable: bool
) -> None:
    target = ConversationRef(uuid4(), uuid4(), ConversationKind.SECONDARY, 3, uuid4())
    busy = RunBusy(
        target, ExecutionKind.GRAPH, phase, "billing", "stream" if relayed else None, cancellable
    )
    status = ActiveRunResponse.occupied(busy, "Annex", selected=True)
    assert status.can_resume is (relayed and phase == ExecutionPhase.RUNNING)
    assert status.can_cancel is (cancellable and phase == ExecutionPhase.RUNNING)
    assert status.stream_id == ("stream" if relayed else None)
    assert status.conversation_id == target.id and status.conversation_revision == 3
    assert status.selected and status.run_id == "billing"
    payload = status.model_dump(mode="json")
    assert not {"runtime_id", "activity_id", "owner_token", "fence", "worker_id"} & payload.keys()
    assert str(target.runtime_id) not in repr(payload)


def _retired_symbols(source: str) -> set[str]:
    """Read actual definitions, imports (including aliases) and calls, never comments."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                found.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                found.add(node.func.attr)
    return found & RETIRED


def test_retired_redis_admission_has_no_production_caller_or_definition() -> None:
    source = Path(__file__).resolve().parents[4] / "src"
    offenders = {
        str(path.relative_to(source)): names
        for path in source.rglob("*.py")
        if (names := _retired_symbols(path.read_text(encoding="utf-8")))
    }
    assert source.is_dir() and not offenders, offenders


@pytest.mark.parametrize(
    "body",
    [
        "from broker import active_run_lease as lease",
        "async def register_active_run(): pass",
        "broker.public_active_run(value)",
    ],
)
def test_the_retired_admission_guard_detects_code_but_not_comments(body: str) -> None:
    assert _retired_symbols(body)
    assert not _retired_symbols("# active_run_lease\nvalue = 'register_active_run'")
