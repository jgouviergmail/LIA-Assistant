"""Request-local source expectations for native cards, checked on the acquired client."""

from collections.abc import AsyncGenerator
from contextvars import ContextVar
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Query

from src.core.constants import WORKBENCH_CARD_SOURCE_HEADER
from src.core.content_source import content_source_binding
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.connectors.active_client import ActiveClient
from src.domains.users.models import User
from src.domains.workbench.card_targets import (
    CARD_TOKEN_MAX_CHARS,
    CARD_TOOLS,
    SignedCardTarget,
    read_card_target,
)
from src.domains.workbench.errors import CARD_SOURCE_CHANGED, refuse
from src.domains.workbench.features import WorkbenchTool

_EXPECTED: ContextVar[tuple[UUID, SignedCardTarget] | None] = ContextVar(
    "workbench_card_source", default=None
)


async def card_source_scope(
    user: Annotated[User, Depends(get_current_active_session_for_stream)],
    source: Annotated[
        str | None, Header(alias=WORKBENCH_CARD_SOURCE_HEADER, max_length=CARD_TOKEN_MAX_CHARS)
    ] = None,
    card_source: Annotated[str | None, Query(max_length=CARD_TOKEN_MAX_CHARS)] = None,
) -> AsyncGenerator[None]:
    """Read an optional source proof without holding a database session or lock.

    The proof adds a constraint, never authority. A request without it retains
    ordinary Tools navigation. Direct downloads carry it in the query; contradictory
    header/query proofs are refused. Resetting in ``finally`` covers failure and cancellation.
    """
    if source is not None and card_source is not None and source != card_source:
        refuse(CARD_SOURCE_CHANGED)
    source = source if source is not None else card_source
    envelope = read_card_target(source, user.id) if source is not None else None
    if source is not None and envelope is None:
        refuse(CARD_SOURCE_CHANGED)
    token = _EXPECTED.set((user.id, envelope) if envelope is not None else None)
    try:
        yield
    finally:
        _EXPECTED.reset(token)


def expected_card_source(tool: WorkbenchTool, user_id: UUID) -> SignedCardTarget | None:
    """Return the expectation for this family alone; auxiliary tools keep their own source."""
    expected = _EXPECTED.get()
    if expected is None:
        return None
    owner, envelope = expected
    if CARD_TOOLS[envelope.target.kind] != tool:
        return None
    if user_id != owner:
        refuse(CARD_SOURCE_CHANGED)
    return envelope


def require_card_source(envelope: SignedCardTarget | None, opened: ActiveClient) -> None:
    """Refuse a replacement source before any read or mutation can use this client."""
    if envelope is not None and (
        opened.connector_type != envelope.provider
        or content_source_binding(opened.client) != envelope.source_binding
    ):
        refuse(CARD_SOURCE_CHANGED)
