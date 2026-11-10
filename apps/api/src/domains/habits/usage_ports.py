"""Facts other domains own, offered to the habits domain (ADR-375).

The proposal rules need two facts habits does not own: what a routine's runs
READ (the treatments register, ``agents``) and what proactive notifications
met (``heartbeat``). Both of those domains already import habits, so habits
importing them back would close two runtime cycles the coupling ratchet
forbids. They OFFER the facts instead, through the two named ports below — the
``domains/shared/consultation_sink`` doctrine: the owner installs its reader
at import, the boot installs it again explicitly and refuses to start without
both (``assert_usage_ports_installed``).

A port nobody installed reads as absent, never as an empty answer: the rules
then HOLD the kinds the fact feeds (``proposal_rules``), they never conclude.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.habits.proposal_rules import ProactiveFeedback


class RoutineReadsReader(Protocol):
    """What routine runs read, by run id."""

    async def __call__(
        self, db: AsyncSession, user_id: UUID, run_ids: Sequence[str]
    ) -> Mapping[str, frozenset[str]]:
        """Return, for each run id found, the registered domains it read.

        Args:
            db: The caller's session (the reader opens none of its own).
            user_id: The owner of the runs.
            run_ids: The runs asked about.

        Returns:
            ``{run_id: domains}``; a run that read nothing is absent.
        """
        ...


class ProactiveFeedbackReader(Protocol):
    """What proactive notifications met since an instant."""

    async def __call__(self, db: AsyncSession, user_id: UUID, since: datetime) -> ProactiveFeedback:
        """Return the notifications sent since ``since`` and how many got a reaction.

        Args:
            db: The caller's session.
            user_id: The person.
            since: The window's start (UTC).

        Returns:
            The counts.
        """
        ...


@dataclass(slots=True)
class _Ports:
    routine_reads: RoutineReadsReader | None = None
    proactive_feedback: ProactiveFeedbackReader | None = None


_PORTS = _Ports()


def install_routine_reads_reader(reader: RoutineReadsReader) -> None:
    """Install the reader of what routine runs read (``agents`` owns it).

    Args:
        reader: The reader.
    """
    _PORTS.routine_reads = reader


def install_proactive_feedback_reader(reader: ProactiveFeedbackReader) -> None:
    """Install the reader of proactive notifications and reactions (``heartbeat``).

    Args:
        reader: The reader.
    """
    _PORTS.proactive_feedback = reader


def routine_reads_reader() -> RoutineReadsReader | None:
    """The installed reader of routine reads, or None."""
    return _PORTS.routine_reads


def proactive_feedback_reader() -> ProactiveFeedbackReader | None:
    """The installed reader of proactive feedback, or None."""
    return _PORTS.proactive_feedback


def assert_usage_ports_installed() -> None:
    """Refuse to boot with a port nobody installed (ADR-085).

    Raises:
        AssertionError: Naming each missing port.
    """
    missing = [
        name
        for name, reader in (
            ("routine_reads", _PORTS.routine_reads),
            ("proactive_feedback", _PORTS.proactive_feedback),
        )
        if reader is None
    ]
    # Raised, never ``assert``-ed: an optimised interpreter strips assertions.
    if missing:
        raise AssertionError(f"habits usage ports not installed: {missing}")
