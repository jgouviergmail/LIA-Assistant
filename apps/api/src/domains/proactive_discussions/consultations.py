"""Record only sources actually opened; run scope comes from the native collector.

An opening run reads on LIA's initiative (``proactive_discussions``); a rebuild the
person asked for reads at their request (``proactive_discussion_rebuild``, authored
``user``), like its spend. The runner names which for the length of the run.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from src.core.read_budget import ReadCallBudget
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.domains.shared.discussion_sources import SourceReadRequest

OPENING_SURFACE = "proactive_discussions"
REBUILD_SURFACE = "proactive_discussion_rebuild"
_REQUESTED_BY_PERSON: ContextVar[bool] = ContextVar("discussion_reads_requested", default=False)


@contextmanager
def reads_requested_by_person(requested: bool) -> Iterator[None]:
    """File every read of the block under the rebuild's surface when the person asked.

    Args:
        requested: Whether the run is a rebuild the person asked for.

    Yields:
        Nothing; the surface holds for the block.
    """
    token = _REQUESTED_BY_PERSON.set(requested)
    try:
        yield
    finally:
        _REQUESTED_BY_PERSON.reset(token)


def record_read(
    request: SourceReadRequest, budget: ReadCallBudget, *, succeeded: bool, duration_ms: int
) -> None:
    """File the consultation of a source this run actually opened.

    A read that never reached its source files nothing; one that reached it and
    failed is filed as failed, never read as silence.

    Args:
        request: The source read, carrying its owner and source key.
        budget: The read's call budget; ``opened`` says whether a call reached
            the source.
        succeeded: Whether the read returned its data.
        duration_ms: How long the read took, in milliseconds.
    """
    if budget.opened:
        source = request.request.source.value
        record_surface_consultations(
            surface=REBUILD_SURFACE if _REQUESTED_BY_PERSON.get() else OPENING_SURFACE,
            user_id=request.owner_id,
            opened=(source,),
            failed=() if succeeded else (source,),
            duration_ms=duration_ms,
        )
