"""Recording a consultation without depending on the register that keeps it.

The consultation register lives in ``domains/agents/effects``, and ``agents``
already imports ``relations`` (the debrief joins the chat's peer block,
ADR-269). A domain that imported the register back would close a cycle — and
the coupling ratchet counts LOCAL imports too, so hiding it inside a function
would not help; it would only make the edge harder to see.

So the dependency is inverted, which is what ``CLAUDE.md`` prescribes for
exactly this case: this module holds a seam, the register INSTALLS itself into
it at import, and any domain may call the seam. Nothing here imports anything.

With no sink installed the call is a no-op rather than an error: a script, a
probe or a narrow unit test has no register open, and a helper that raised
there would turn an observability concern into an outage.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol


class ConsultationSink(Protocol):
    """What the register offers a domain that opened one of its sources.

    The fields are named rather than opaque: a seam that accepted ``**Any``
    would let a caller misspell one and record a row with a missing column,
    which is precisely the silence this whole registry exists to end.
    """

    def __call__(
        self,
        *,
        user_id: object,
        capability: str,
        source: str,
        succeeded: bool,
        duration_ms: int,
        run_id: str | None = None,
    ) -> None:
        """Record one consultation.

        Args:
            user_id: Whose data was read.
            capability: What was consulted, in a bounded vocabulary.
            source: Who set the turn in motion.
            succeeded: Whether the source answered.
            duration_ms: Wall-clock duration of the read.
            run_id: The run, or None to take the collector's own.
        """


def _ignore(
    *,
    user_id: object,
    capability: str,
    source: str,
    succeeded: bool,
    duration_ms: int,
    run_id: str | None = None,
) -> None:
    """The sink before the register installs itself: it keeps nothing."""


_sink: ConsultationSink = _ignore


def install_consultation_sink(sink: ConsultationSink) -> None:
    """Let the register receive what the domains record.

    Called once, by the register's own module at import.

    Args:
        sink: The register's recording function.
    """
    global _sink  # noqa: PLW0603 — one seam, installed once, by its owner
    _sink = sink


def record_consultation(
    *,
    user_id: object,
    capability: str,
    source: str,
    succeeded: bool,
    duration_ms: int,
    run_id: str | None = None,
) -> None:
    """Record one consultation through the installed sink, or do nothing.

    Args:
        user_id: Whose data was read.
        capability: What was consulted, in a bounded vocabulary.
        source: Who set the turn in motion.
        succeeded: Whether the source answered.
        duration_ms: Wall-clock duration of the read.
        run_id: The run, or None to take the collector's own.
    """
    _sink(
        user_id=user_id,
        capability=capability,
        source=source,
        succeeded=succeeded,
        duration_ms=duration_ms,
        run_id=run_id,
    )


class CollectorFactory(Protocol):
    """What opens a collector for one run."""

    def __call__(self, *, run_id: str) -> AbstractAsyncContextManager[list[Any]]:
        """Open the collector.

        Args:
            run_id: The run every collected row is filed under.
        """


#: Installed by the register's recorder, for the same reason as the sink: a
#: domain must be able to publish a collector without importing the package
#: that keeps it.
_collector_factory: CollectorFactory | None = None


def install_collector_factory(factory: CollectorFactory) -> None:
    """Let the register provide the collector a run publishes.

    Args:
        factory: Takes a run id, yields the live list rows are appended to.
    """
    global _collector_factory  # noqa: PLW0603 — one seam, installed by its owner
    _collector_factory = factory


@asynccontextmanager
async def consultation_collector(run_id: str) -> AsyncIterator[list[Any]]:
    """Publish a collector for the duration of one out-of-turn run.

    With no register installed this yields an empty list and writes nothing —
    a probe or a narrow unit test keeps working, and records nothing, which is
    the truth in that case.

    Args:
        run_id: The run every collected row is filed under.

    Yields:
        The live list the sources append to.
    """
    if _collector_factory is None:
        yield []
        return
    async with _collector_factory(run_id=run_id) as rows:
        yield rows


def sink_is_installed() -> bool:
    """Whether a register has claimed the seam — for guards, not for callers."""
    return _sink is not _ignore


__all__ = [
    "CollectorFactory",
    "ConsultationSink",
    "consultation_collector",
    "install_collector_factory",
    "install_consultation_sink",
    "record_consultation",
    "sink_is_installed",
]
