"""Typed graph authority for units; SQL admission is tested on real PostgreSQL."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

from src.core.conversation_execution import ExecutionKind, RunAdmission
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.run_authority import RunAuthority, run_authority_scope


@contextmanager
def unit_run_authority(
    owner: UUID, conversation: UUID, runtime: UUID, *, revision: int = 0
) -> Iterator[RunAuthority]:
    """Install and restore the exact coordinates of a unit's producer."""
    target = ConversationRef(owner, conversation, ConversationKind.MAIN, revision, runtime)
    admission = RunAdmission(
        activity_id=uuid4(),
        target=target,
        kind=ExecutionKind.GRAPH,
        run_id=str(uuid4()),
        stream_id=str(uuid4()),
        worker_id=uuid4(),
        owner_token=uuid4(),
        fence=1,
        relayed=False,
    )
    authority = RunAuthority(admission)
    with run_authority_scope(authority):
        yield authority
