"""An invocation identity survives native coordinates, never a prior run's authority."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from src.core.conversation_execution import ExecutionKind, ExecutionRevoked, RunAdmission
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.run_authority import RunAuthority, run_authority_scope, track_graph_writer
from src.domains.conversations.runtime_identity import (
    checkpoint_config,
    checkpoint_execution,
    retain_checkpoint_identity,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def admission() -> RunAdmission:
    """Wire serialization needs distinct coordinates, not a database test double."""
    return RunAdmission(
        activity_id=uuid4(),
        target=ConversationRef(uuid4(), uuid4(), ConversationKind.SECONDARY, 8, uuid4()),
        kind=ExecutionKind.GRAPH,
        run_id=str(uuid4()),
        stream_id=str(uuid4()),
        worker_id=uuid4(),
        owner_token=uuid4(),
        fence=123,
        relayed=False,
    )


def test_native_coordinates_preserve_every_invocation_field(admission: RunAdmission) -> None:
    with run_authority_scope(RunAuthority(admission)):
        config = checkpoint_config(admission.target)
    saved = retain_checkpoint_identity(config, {"configurable": {"checkpoint_id": "native-id"}})
    assert checkpoint_execution(saved) == admission.identity
    assert saved["configurable"]["checkpoint_id"] == "native-id"


def test_a_restored_checkpoint_cannot_replace_the_current_invocation(
    admission: RunAdmission,
) -> None:
    with run_authority_scope(RunAuthority(admission)):
        previous = checkpoint_config(admission.target)
    current = replace(admission, activity_id=uuid4(), owner_token=uuid4(), fence=124)
    with run_authority_scope(RunAuthority(current)):
        config = checkpoint_config(current.target)
    assert checkpoint_execution(retain_checkpoint_identity(config, previous)) == current.identity
    read_only = checkpoint_config(current.target)
    with pytest.raises(ExecutionRevoked):
        checkpoint_execution(retain_checkpoint_identity(read_only, previous))


@pytest.mark.parametrize("field", ["activity_id", "worker_id", "owner_token", "fence"])
@pytest.mark.parametrize("invalid", [None, True, -1, {}, "unreadable"])
def test_incomplete_or_malformed_private_identity_refuses_writes(
    admission: RunAdmission,
    field: str,
    invalid: object,
) -> None:
    with run_authority_scope(RunAuthority(admission)):
        config = checkpoint_config(admission.target)
    config["configurable"]["execution_scope"][field] = invalid
    with pytest.raises(ExecutionRevoked):
        checkpoint_execution(config)


def test_another_target_is_only_readable_under_a_running_invocation(
    admission: RunAdmission,
) -> None:
    other = replace(admission.target, id=uuid4(), runtime_id=uuid4())
    with run_authority_scope(RunAuthority(admission)), pytest.raises(ExecutionRevoked):
        checkpoint_execution(checkpoint_config(other))


async def test_a_late_registered_task_cannot_escape_a_revoked_owner(
    admission: RunAdmission,
) -> None:
    authority = RunAuthority(admission, revoked=True)
    executed = False

    async def writer() -> None:
        nonlocal executed
        executed = True

    with run_authority_scope(authority):
        task = asyncio.create_task(writer())
        try:
            retained = track_graph_writer(task)
            assert retained is task and task in authority.writers
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not executed
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
