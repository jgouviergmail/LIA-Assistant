"""Unknown file writers require an explicit exact-boot stop attestation."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from scripts.data import recover_file_writes as command

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("confirmation", [None, "different"])
def test_retire_without_exact_stop_attestation_never_connects(
    monkeypatch: pytest.MonkeyPatch,
    confirmation: str | None,
) -> None:
    run = AsyncMock()
    monkeypatch.setattr(command, "_run", run)
    args = ["retire", "--worker", str(uuid4())]
    if confirmation:
        args.extend(["--confirm-worker-stopped", str(uuid4())])
    with pytest.raises(SystemExit) as refused:
        command.main(args)
    assert refused.value.code == 2
    run.assert_not_called()


@pytest.mark.parametrize("failure", [False, True])
async def test_recovery_closes_its_pool_on_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
    failure: bool,
) -> None:
    recover = AsyncMock(
        return_value=command.RecoveryCounts(3, 2),
        side_effect=OSError("injected") if failure else None,
    )
    close = AsyncMock()
    monkeypatch.setattr(command, "_recover", recover)
    monkeypatch.setattr(command, "close_db", close)
    monkeypatch.setattr(command, "import_all_models", lambda: None)
    worker = uuid4()
    assert await command._run("retire", worker) == int(failure)
    recover.assert_awaited_once_with("retire", worker)
    close.assert_awaited_once()
