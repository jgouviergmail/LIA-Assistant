"""Re-read selected native objects and permissions before paid decisions or delivery."""

from datetime import UTC, datetime

import structlog

from src.core.config import settings
from src.core.constants import (
    DISCUSSION_FULL_EXCERPT_CHARS,
    DISCUSSION_REREAD_ITEM_LIMIT,
)
from src.domains.proactive_discussions.context_store.preparation import proof_of
from src.domains.proactive_discussions.contextualization.loop import ContextResult, SourceReader
from src.domains.proactive_discussions.run_types import RunClaim, StopReason
from src.domains.shared.discussion_catalogue import reread_operation
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    ResearchRequest,
    SourceReadRequest,
    SourceSnapshot,
    evidence_identity,
)
from src.infrastructure.proactive.discussion_attention import InitiativeStopped
from src.infrastructure.proactive.discussion_proofs import proof_request

logger = structlog.get_logger(__name__)

#: The pages a re-read can answer from: anything else was never read again.
_READABLE = frozenset({"ok", "empty", "truncated"})


async def revalidate_evidence(
    claim: RunClaim, result: ContextResult, gateway: SourceReader
) -> tuple[SourceSnapshot, ...]:
    """Read every selected fact again before a paid decision.

    Each fact is read again on its page's window, by the read that finds it
    (``reread_operation``: an expanded read for calendar occurrences, the future
    for a planned fact of a source with no detail read), and must come back at the
    same version; topics qualified earlier are kept. Facts asking for the same read
    share it: one page of a source is read again once, never once per fact, inside
    the run's read budget (measured 2026-10-21: one read per fact spent a run's whole
    budget on three passes, and its last re-read came back closed). A fact that
    shared page stopped before (truncated) is read again around its own instant:
    only a page that covered it can say it changed.

    Args:
        claim: The run's claim.
        result: The ready context.
        gateway: The bounded source reader.

    Returns:
        One fresh page per fact, holding only that fact.

    Raises:
        InitiativeStopped: A fact's page is missing; a re-read could not be made
            (refused by the person's controls, out of the run's read budget, or
            unreadable); or the fact changed or disappeared.
    """
    reads: dict[str, SourceSnapshot] = {}
    pages: list[SourceSnapshot] = []
    for fact in result.evidence:
        page = next(
            (
                page
                for page in result.snapshots
                if any(item.reference == fact.reference for item in page.items)
            ),
            None,
        )
        if page is None:
            raise InitiativeStopped("evidence_page_missing")
        request = _request(fact, page)
        key = f"{request.model_dump_json()}|{page.window_start}|{page.window_end}"
        fresh = reads.get(key)
        if fresh is None:
            fresh = reads[key] = await gateway.read(
                SourceReadRequest(
                    owner_id=claim.owner_id,
                    run_id=claim.run_id,
                    policy_revision=claim.policy_revision,
                    request=request,
                    now=datetime.now(UTC),
                    window_start=page.window_start,
                    window_end=page.window_end,
                    item_limit=DISCUSSION_REREAD_ITEM_LIMIT,
                    item_max_chars=DISCUSSION_FULL_EXCERPT_CHARS,
                    call_limit=settings.discussion_read_call_limit,
                    timeout_seconds=settings.discussion_read_timeout_seconds,
                )
            )
        if fresh.status not in _READABLE:
            raise InitiativeStopped(_unread(fresh))
        current = _found(fresh, fact)
        if current is None and fresh.status == "truncated":
            # The page stopped before the fact (a busy window, a fact found by a
            # search): its absence proves no change, so the fact is read again
            # around its own instant, the way a stored proof is.
            fresh = await _read_around(claim, fact, gateway)
            current = _found(fresh, fact)
            if current is None and fresh.status == "truncated":
                raise InitiativeStopped("evidence_page_missing")
        if current is None or current.version != fact.version:
            # Which source moved, and how — never what it said: the stop is a fact.
            logger.info(
                "discussion_evidence_changed",
                user_id=str(claim.owner_id),
                run_id=str(claim.run_id),
                source=fact.source.value,
                missing=current is None,
            )
            raise InitiativeStopped("evidence_changed")
        # A fresh provider projection cannot erase a previously qualified topic.
        current = current.model_copy(
            update={
                "sensitive_topics": tuple(
                    sorted(set(current.sensitive_topics) | set(fact.sensitive_topics))
                )
            }
        )
        pages.append(fresh.model_copy(update={"items": (current,)}))
    return tuple(pages)


def _found(page: SourceSnapshot, fact: DiscussionEvidence) -> DiscussionEvidence | None:
    """The fact as the page read it again, by its object's identity, if the page holds it."""
    return next(
        (item for item in page.items if evidence_identity(item) == evidence_identity(fact)),
        None,
    )


async def _read_around(
    claim: RunClaim, fact: DiscussionEvidence, gateway: SourceReader
) -> SourceSnapshot:
    """Read one fact again around its own instant, as its stored proof would be.

    Raises:
        InitiativeStopped: No window around the fact lies within the research bounds,
            or the read could not be made.
    """
    now = datetime.now(UTC)
    request = proof_request(claim, proof_of(fact, {fact.reference: fact}, now=now), now=now)
    if request is None:
        raise InitiativeStopped("evidence_page_missing")
    page = await gateway.read(request)
    if page.status not in _READABLE:
        raise InitiativeStopped(_unread(page))
    return page


def _unread(page: SourceSnapshot) -> StopReason:
    """Why a re-read answered nothing: a page that was not read proves no change."""
    if page.reason in {"consent", "feature"}:
        return "evidence_refused"
    if page.reason == "budget":
        return "read_budget_exhausted"
    return "evidence_page_missing"


def _request(fact: DiscussionEvidence, page: SourceSnapshot) -> ResearchRequest:
    operation = reread_operation(
        fact.source, planned=fact.assertion == "planned", around_instant=False
    )
    dated = operation in {"history", "future"}
    return ResearchRequest(
        source=fact.source,
        operation=operation,
        reference=fact.reference if operation == "detail" else None,
        start=page.window_start if dated else None,
        end=page.window_end if dated else None,
    )
