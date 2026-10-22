"""Hydrate cached metadata through the native reader, never through a stored source body."""

from datetime import UTC, datetime, time, timedelta

from src.core.config import settings
from src.core.constants import (
    DISCUSSION_FULL_EXCERPT_CHARS,
    DISCUSSION_REREAD_ITEM_LIMIT,
)
from src.domains.proactive_discussions.context_store.schemas import ContextEvidenceLink
from src.domains.proactive_discussions.contextualization.loop import SourceReader
from src.domains.proactive_discussions.registry import SOURCE_REGISTRY
from src.domains.proactive_discussions.run_types import RunClaim
from src.domains.shared.discussion_catalogue import reread_operation
from src.domains.shared.discussion_sources import (
    RESEARCH_FUTURE_DAYS_MAX,
    RESEARCH_HISTORY_DAYS_MAX,
    ResearchRequest,
    SourceReadRequest,
    SourceSnapshot,
)

#: A proof is re-read around its own instant, never across its whole source.
_PROOF_WINDOW_DAYS = 2


async def hydrate_proofs(
    claim: RunClaim,
    proofs: tuple[ContextEvidenceLink, ...],
    gateway: SourceReader,
    *,
    now: datetime,
) -> tuple[SourceSnapshot, ...]:
    """Read stored proofs again through their native readers, keeping the unchanged ones.

    Args:
        claim: The run's claim.
        proofs: The stored proofs.
        gateway: The bounded source reader.
        now: The current instant.

    Returns:
        One page per proof still present at the same version, holding only it.
    """
    pages: list[SourceSnapshot] = []
    for proof in proofs:
        request = proof_request(claim, proof, now=now)
        if request is None:
            continue
        page = await gateway.read(request)
        fresh = tuple(
            item
            for item in page.items
            if item.reference == proof.reference
            and item.source_account == proof.source_account
            and item.object_id == proof.object_id
            and item.version == proof.version
        )
        if fresh:
            pages.append(page.model_copy(update={"items": fresh}))
    return tuple(pages)


def proof_request(
    claim: RunClaim, proof: ContextEvidenceLink, *, now: datetime
) -> SourceReadRequest | None:
    """Build the bounded read that finds one proof again around its own instant.

    Args:
        claim: The run's claim.
        proof: The stored proof.
        now: The current instant.

    Returns:
        The read, or None when the proof expired or its window lies outside the
        research bounds.
    """
    if proof.expires_at <= now:
        return None
    window = proof_window(proof, now=now)
    if window is None:
        return None
    start, end = window
    operation = reread_operation(
        proof.source, planned=proof.assertion == "planned", around_instant=True
    )
    dated = operation in {"history", "future"}
    request = ResearchRequest(
        source=proof.source,
        operation=operation,
        reference=proof.reference if operation == "detail" else None,
        start=start if dated else None,
        end=end if dated else None,
    )
    return SourceReadRequest(
        owner_id=claim.owner_id,
        run_id=claim.run_id,
        policy_revision=claim.policy_revision,
        request=request,
        now=now,
        window_start=start,
        window_end=end,
        item_limit=DISCUSSION_REREAD_ITEM_LIMIT,
        item_max_chars=DISCUSSION_FULL_EXCERPT_CHARS,
        call_limit=settings.discussion_read_call_limit,
        timeout_seconds=settings.discussion_read_timeout_seconds,
    )


def proof_window(proof: ContextEvidenceLink, *, now: datetime) -> tuple[datetime, datetime] | None:
    """Return the window around a proof's own instant, within the research bounds.

    A current object is read around now; any other around its original start,
    occurrence or record date, two days either side.

    Args:
        proof: The stored proof.
        now: The current instant.

    Returns:
        The window, or None when it is empty.
    """
    pivot = (
        now
        if SOURCE_REGISTRY[proof.source].current_object
        else proof.original_start or proof.occurred_at or proof.recorded_at or now
    )
    if proof.original_date is not None:
        pivot = datetime.combine(proof.original_date, time.min, tzinfo=UTC)
    start = max(
        pivot - timedelta(days=_PROOF_WINDOW_DAYS), now - timedelta(days=RESEARCH_HISTORY_DAYS_MAX)
    )
    end = min(
        pivot + timedelta(days=_PROOF_WINDOW_DAYS), now + timedelta(days=RESEARCH_FUTURE_DAYS_MAX)
    )
    if start >= end:
        return None
    return start, end
