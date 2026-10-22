"""Read source ports under fresh discussion authority, with bounded cancellation."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from time import perf_counter
from types import MappingProxyType
from uuid import UUID

import structlog
from pydantic import ValidationError

from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.core.read_budget import ReadCallBudget, ReadCallLimit, read_call_budget
from src.core.tool_outcome import error_code_of
from src.domains.proactive_discussions.backoff import DiscussionBackoff, retry_deadline
from src.domains.proactive_discussions.consultations import record_read
from src.domains.proactive_discussions.policy import effective_sources
from src.domains.proactive_discussions.registry import SOURCE_REGISTRY, assert_registry_complete
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.source_failures import authorization_failure
from src.domains.shared.discussion_sources import (
    DiscussionSource,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    source_snapshot,
)

logger = structlog.get_logger(__name__)
PolicyLoader = Callable[[UUID], Awaitable[DiscussionPolicy]]
UsageSink = Callable[[SourceReadRequest, int], None]


def _permitted(policy: DiscussionPolicy, request: SourceReadRequest) -> bool:
    return (
        policy.revision == request.policy_revision
        and request.request.source in effective_sources(policy, frozenset(SourceKey))
    )


def _matches_requested_scope(snapshot: SourceSnapshot, request: SourceReadRequest) -> bool:
    """A port may narrow its result, never enlarge its owner's requested scope."""
    return (
        snapshot.owner_id == request.owner_id
        and snapshot.source == request.request.source
        and snapshot.physical_calls <= request.call_limit
        and len(snapshot.items) <= request.item_limit
        and snapshot.window_start >= request.window_start
        and snapshot.window_end <= request.window_end
    )


class SourceGateway:
    """Read one source port under the discussion authority, bounded and accounted.

    Every read checks consent before and after the port runs, bounds its time,
    physical calls, items and excerpts, refuses a result outside the requested
    scope, and files a consultation when the source was actually opened. A failure
    becomes a closed or stale snapshot naming its cause; only a provider's backoff
    propagates.
    """

    def __init__(
        self,
        readers: Mapping[SourceKey, DiscussionSource],
        policy_loader: PolicyLoader,
        *,
        usage_sink: UsageSink | None = None,
        call_budget: ReadCallBudget | None = None,
    ) -> None:
        assert_registry_complete(SOURCE_REGISTRY, installed=frozenset(readers))
        self.readers = MappingProxyType(dict(readers))
        self.policy_loader = policy_loader
        self.usage_sink = usage_sink
        self.call_budget = call_budget

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one source page under the run's authority.

        Args:
            request: The read: owner, source, operation, window and bounds.

        Returns:
            The page, or a closed or stale snapshot naming why nothing usable came
            back.

        Raises:
            DiscussionBackoff: The provider asked to retry later; the run defers.
        """
        request = SourceReadRequest.model_validate(request.model_dump())
        started = perf_counter()
        succeeded = False
        with read_call_budget(
            ReadCallBudget(
                owner=request.owner_id, limit=request.call_limit, parent=self.call_budget
            )
        ) as budget:
            try:
                result = await self._read_bounded(request, budget)
                succeeded = result.status in {"ok", "empty", "truncated"}
                return result.model_copy(update={"physical_calls": budget.calls})
            finally:
                record_read(
                    request,
                    budget,
                    succeeded=succeeded,
                    duration_ms=int((perf_counter() - started) * 1000),
                )
                if self.usage_sink is not None:
                    self.usage_sink(request, budget.calls)

    async def _read_bounded(
        self, request: SourceReadRequest, budget: ReadCallBudget
    ) -> SourceSnapshot:
        try:
            async with asyncio.timeout(request.timeout_seconds):
                return await self._read_authorized(request, budget)
        except TimeoutError:
            return closed_source(request, disabled=False, reason="timeout")
        except AuthorizationError as exc:
            return authorization_failure(request, exc)
        except ResourceNotFoundError:
            return source_snapshot(request, status="stale", reason="expired")
        except ResourceConflictError as exc:
            if error_code_of(exc.detail) == "QUERY_TOO_BROAD":
                return closed_source(request, disabled=False, reason="budget")
            return source_snapshot(request, status="stale", reason="expired")
        except ReadCallLimit:
            return closed_source(request, disabled=False, reason="budget")
        except ValidationError, ValueError, TypeError:
            return closed_source(request, disabled=False, reason="malformed")
        except Exception as exc:
            until = retry_deadline(exc, now=request.now)
            if until is not None:
                raise DiscussionBackoff(until) from exc
            logger.warning(
                "discussion_source_unavailable",
                source=request.request.source.value,
                error_type=type(exc).__name__,
            )
            return closed_source(request, disabled=False, reason="provider")

    async def _read_authorized(
        self, request: SourceReadRequest, budget: ReadCallBudget
    ) -> SourceSnapshot:
        policy = await self.policy_loader(request.owner_id)
        if not _permitted(policy, request):
            return closed_source(request, disabled=True, reason="consent")
        source = request.request.source
        if request.request.operation not in SOURCE_REGISTRY[source].operations:
            return closed_source(request, disabled=False, reason="malformed")
        allowed = effective_sources(policy, frozenset(SourceKey))
        actual = request.model_copy(
            update={
                "allowed_sources": tuple(key for key in SourceKey if key in allowed),
                "sensitive_topics": policy.sensitive_topics,
            }
        )
        snapshot = await self.readers[source].read(actual)
        budget.observe(snapshot.physical_calls)
        snapshot = SourceSnapshot.model_validate(snapshot.model_dump())
        if any(not set(item.required_sources).issubset(allowed) for item in snapshot.items):
            return closed_source(request, disabled=True, reason="consent")
        if any(len(item.excerpt) > request.item_max_chars for item in snapshot.items):
            return closed_source(request, disabled=False, reason="budget")
        if not _matches_requested_scope(snapshot, request):
            return closed_source(request, disabled=False, reason="malformed")
        if not _permitted(await self.policy_loader(request.owner_id), request):
            return closed_source(request, disabled=True, reason="consent")
        return snapshot
