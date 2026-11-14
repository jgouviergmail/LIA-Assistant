"""A privileged recovery command requires an explicit exact-boot stop attestation."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from scripts.data import recover_execution as command
from src.core.conversation_execution import ExecutionPhase

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("confirmation", [None, "different"])
def test_close_without_exact_stop_attestation_never_connects(
    monkeypatch: pytest.MonkeyPatch, confirmation: str | None
) -> None:
    run = AsyncMock()
    monkeypatch.setattr(command, "_run", run)
    args = ["close", "--activity", str(uuid4()), "--worker", str(uuid4())]
    if confirmation:
        args.extend(["--confirm-worker-stopped", str(uuid4())])
    with pytest.raises(SystemExit) as refused:
        command.main(args)
    assert refused.value.code == 2
    run.assert_not_called()


@pytest.mark.parametrize("operation", ["inspect", "quarantine", "close"])
@pytest.mark.parametrize("failure", [False, True])
async def test_every_command_closes_its_owned_pools_even_on_failure(
    monkeypatch: pytest.MonkeyPatch, operation: str, failure: bool
) -> None:
    selected = AsyncMock(
        return_value=ExecutionPhase.CLOSED,
        side_effect=ConnectionError("unavailable") if failure else None,
    )
    functions = {
        "inspect": "inspect_execution",
        "quarantine": "quarantine",
        "close": "close_stopped",
    }
    monkeypatch.setattr(command, functions[operation], selected)
    monkeypatch.setattr(command, "import_all_models", lambda: None)
    redis, db = AsyncMock(), AsyncMock()
    monkeypatch.setattr(command, "close_redis", redis)
    monkeypatch.setattr(command, "close_db", db)
    activity, worker = uuid4(), uuid4()
    assert await command._run(operation, activity, worker) == int(failure)
    selected.assert_awaited_once_with(activity, worker)
    redis.assert_awaited_once()
    db.assert_awaited_once()
