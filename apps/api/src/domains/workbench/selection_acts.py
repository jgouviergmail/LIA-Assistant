"""An act on a selection, item by item — a few at a time, each answered (ADR-369).

A provider throttles a burst, so items are acted on a few at a time. Each is
done, or said with why: gone since it was listed, refused for it alone, or
never answered because the provider stopped mid-way. A provider failure before
ANY item was done is the act's own (reconnect, wait, unavailable) and leaves as
a refusal; after one, the rest are « unavailable », because a refusal would
hide the items already done.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Final

import structlog

from src.core.exceptions import ConnectorAPIError
from src.domains.workbench.schemas.acts import ActFailure, ActOutcome, ActStatus

logger = structlog.get_logger(__name__)

#: Items acted on at once (a mailbox and Drive alike answer a burst with 429).
ACT_CONCURRENCY: Final = 4
UNAVAILABLE: Final[ActStatus] = "unavailable"
#: A provider's « this item is not here ».
_GONE: Final = frozenset({404, 410})

Settled = dict[str, ActStatus | BaseException | None]


async def settle_each(ids: list[str], act: Callable[[str], Awaitable[Any]]) -> Settled:
    """Each item's fate: None when done, a status, or the provider's failure."""
    gate = asyncio.Semaphore(ACT_CONCURRENCY)

    async def one(item_id: str) -> ActStatus | None:
        async with gate:
            try:
                await act(item_id)
            except ConnectorAPIError as refused:
                return "not_found" if refused.upstream_status_code in _GONE else "failed"
            except ValueError:
                # iCloud's « not found »: a handle naming no message of its folder.
                return "not_found"
            return None

    fates = await asyncio.gather(*(one(item_id) for item_id in ids), return_exceptions=True)
    return dict(zip(ids, fates, strict=True))


def act_outcome(ids: list[str], settled: Settled, *, tool: str) -> ActOutcome:
    """The answer — or the provider's failure, raised, when nothing was done."""
    done = [item_id for item_id in ids if settled[item_id] is None]
    failures = [fate for fate in settled.values() if isinstance(fate, BaseException)]
    if failures and not done:
        raise failures[0]
    if failures:
        logger.warning(
            "workbench_act_interrupted",
            tool=tool,
            done=len(done),
            unanswered=len(failures),
            error_type=type(failures[0]).__name__,
        )
    failed = [
        ActFailure(id=item_id, status=UNAVAILABLE if isinstance(fate, BaseException) else fate)
        for item_id, fate in settled.items()
        if fate is not None
    ]
    return ActOutcome(done=done, failed=failed)
