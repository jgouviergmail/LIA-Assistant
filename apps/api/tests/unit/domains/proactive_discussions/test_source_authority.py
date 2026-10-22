"""The actual gateway must gate reads and discard data after authority changes."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.core.exceptions import AuthorizationError
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.source_gateway import SourceGateway
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    ResearchRequest,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
)

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)
OWNER = UUID(int=1)


def request(source: SourceKey) -> SourceReadRequest:
    return SourceReadRequest(
        owner_id=OWNER,
        run_id=UUID(int=2),
        policy_revision=1,
        request=ResearchRequest(source=source, operation="detail", reference=f"{source}:1"),
        now=NOW,
        window_start=NOW - timedelta(hours=72),
        window_end=NOW + timedelta(days=7),
        item_limit=10,
        call_limit=1,
        timeout_seconds=0.02,
    )


class Port:
    def __init__(self, *, foreign: bool = False, slow: bool = False) -> None:
        self.reads = 0
        self.foreign = foreign
        self.slow = slow
        self.closed = False

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        self.reads += 1
        try:
            if self.slow:
                await asyncio.sleep(10)
            source = request.request.source
            return SourceSnapshot(
                source=source,
                owner_id=UUID(int=3) if self.foreign else OWNER,
                status="ok",
                read_at=NOW,
                window_start=request.window_start,
                window_end=request.window_end,
                complete=True,
                items=(
                    DiscussionEvidence(
                        reference=f"{source}:1",
                        source=source,
                        object_id="1",
                        version="v1",
                        observed_at=NOW,
                        excerpt="Fictional evidence",
                    ),
                ),
            )
        finally:
            self.closed = True


@pytest.mark.parametrize("source", list(SourceKey))
async def test_refused_source_invokes_no_live_or_cache_reader(source: SourceKey) -> None:
    port = Port()

    async def policy(owner: UUID) -> DiscussionPolicy:
        return DiscussionPolicy(enabled=True, sources=(), revision=1)

    gateway = SourceGateway(dict.fromkeys(SourceKey, port), policy)
    result = await gateway.read(request(source))
    assert result.status == "disabled" and result.items == () and port.reads == 0


async def test_portrait_permission_does_not_expand_its_historical_supports() -> None:
    port = Port()

    async def policy(owner: UUID) -> DiscussionPolicy:
        return DiscussionPolicy(enabled=True, sources=(SourceKey.PORTRAIT,), revision=1)

    gateway = SourceGateway(dict.fromkeys(SourceKey, port), policy)
    result = await gateway.read(
        request(SourceKey.PORTRAIT).model_copy(
            update={"request": ResearchRequest(source=SourceKey.PORTRAIT, operation="recent")}
        )
    )
    assert result.status == "ok" and port.reads == 1


async def test_revocation_during_read_discards_result() -> None:
    port = Port()
    calls = 0

    async def policy(owner: UUID) -> DiscussionPolicy:
        nonlocal calls
        calls += 1
        return DiscussionPolicy(
            enabled=True, sources=(SourceKey.SMS,) if calls == 1 else (), revision=calls
        )

    result = await SourceGateway(dict.fromkeys(SourceKey, port), policy).read(
        request(SourceKey.SMS)
    )
    assert result.status == "disabled" and result.items == () and port.reads == 1


async def test_foreign_owner_evidence_is_never_admitted() -> None:
    port = Port(foreign=True)

    async def policy(owner: UUID) -> DiscussionPolicy:
        return DiscussionPolicy(enabled=True, sources=(SourceKey.SMS,), revision=1)

    result = await SourceGateway(dict.fromkeys(SourceKey, port), policy).read(
        request(SourceKey.SMS)
    )
    assert result.status == "unavailable" and result.reason == "malformed" and not result.items


async def test_timeout_cancels_reader_and_is_not_empty() -> None:
    port = Port(slow=True)

    async def policy(owner: UUID) -> DiscussionPolicy:
        return DiscussionPolicy(enabled=True, sources=(SourceKey.SMS,), revision=1)

    result = await SourceGateway(dict.fromkeys(SourceKey, port), policy).read(
        request(SourceKey.SMS)
    )
    assert result.status == "unavailable" and result.reason == "timeout" and port.closed


async def test_cancellation_is_propagated() -> None:
    class Cancelled:
        async def read(self, request: SourceReadRequest) -> SourceSnapshot:
            raise asyncio.CancelledError

    async def policy(owner: UUID) -> DiscussionPolicy:
        return DiscussionPolicy(enabled=True, sources=(SourceKey.SMS,), revision=1)

    gateway = SourceGateway({key: Cancelled() for key in SourceKey}, policy)
    with pytest.raises(asyncio.CancelledError):
        await gateway.read(request(SourceKey.SMS))


@pytest.mark.parametrize(
    "code,status,reason",
    [
        ("CAPABILITY_DISABLED", "disabled", "feature"),
        ("SERVICE_UNAVAILABLE", "unavailable", "provider"),
        ("SMS_CONSENT_REQUIRED", "disabled", "consent"),
        # An inactive connection, an account LIA cannot identify, or one that changed
        # mid-read: the source could not be read; the person refused nothing.
        ("FORBIDDEN", "unavailable", "provider"),
        ("ACCOUNT_IDENTITY_UNAVAILABLE", "unavailable", "provider"),
        ("SOURCE_ACCOUNT_CHANGED", "unavailable", "provider"),
        ("AN_UNDECLARED_CODE", "unavailable", "provider"),
    ],
)
async def test_permission_failure_keeps_its_actual_cause(
    code: str, status: str, reason: str
) -> None:
    class Denied:
        async def read(self, scope: SourceReadRequest) -> SourceSnapshot:
            raise AuthorizationError(detail={"error_code": code})

    async def policy(owner: UUID) -> DiscussionPolicy:
        return DiscussionPolicy(enabled=True, sources=(SourceKey.SMS,), revision=1)

    result = await SourceGateway(dict.fromkeys(SourceKey, Denied()), policy).read(
        request(SourceKey.SMS)
    )
    assert result.status == status and result.reason == reason and not result.items
