"""The progressive dashboard's world: the page-load rig, plus what an act files.

``page_load_harness.Rig`` already gives a Redis that honours TTL and NX,
fetchers that count their calls and connector latency. The progressive routes
add three things a test must observe — the consultations a run collects, the
decision rows it files, and the run its spend is accounted under — and two
caches the rig does not reach (the text cache and the text claim). This module
installs those over the rig, so every test reads one ``Register``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack, asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

from src.core.llm_usage import LLMUsage
from tests.unit.domains.briefing.page_load_harness import Rig

#: A morning instant, far from the local midnight the act's context watches.
MORNING = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)

#: What a real greeting call reports: a model answer carries its usage.
MODEL_USAGE = LLMUsage(tokens_in=120, tokens_out=20, cost_eur=0.0001, model_name="stub")


@dataclass
class Register:
    """What the act filed: consultations per run, decision rows, accounted runs."""

    #: The rows each collector held, keyed by the run the collector was opened for.
    consulted: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    decisions: list[tuple[str, str, bool]] = field(default_factory=list)
    spend_runs: list[str] = field(default_factory=list)

    def rows(self) -> list[dict[str, Any]]:
        """Every consultation row collected, whichever collector held it."""
        return [row for rows in self.consulted.values() for row in rows]

    def opened(self, run_id: str) -> list[str]:
        """The sources a run opened — read from the run id each ROW carries, as the register files it."""
        return [name for row in self.rows() if row["run_id"] == run_id for name in row["opened"]]


_current_rows: ContextVar[list[dict[str, Any]] | None] = ContextVar("rows", default=None)


@contextmanager
def progressive_installed(rig: Rig) -> Iterator[Register]:
    """Install the rig and the act's observable collaborators.

    Args:
        rig: The page-load rig (its Redis also backs the text cache and claim).

    Yields:
        The register the act files into.
    """
    register = Register()

    @asynccontextmanager
    async def collector(run_id: str) -> AsyncIterator[list[dict[str, Any]]]:
        rows = register.consulted.setdefault(run_id, [])
        token = _current_rows.set(rows)
        try:
            yield rows
        finally:
            _current_rows.reset(token)

    def record(**row: Any) -> None:
        rows = _current_rows.get()
        if rows is not None:
            rows.append(row)

    @asynccontextmanager
    async def spend(run_id: str, _user_id: UUID, _session_id: str) -> AsyncIterator[None]:
        register.spend_runs.append(run_id)
        yield

    async def file_act(*, user_id: UUID, run_id: str, route: str, once: bool = False) -> None:
        register.decisions.append((run_id, route, once))

    with ExitStack() as stack:
        stack.enter_context(rig.installed())
        redis = AsyncMock(return_value=rig.redis)
        for target, value in (
            ("src.domains.briefing.progressive.consultation_collector", collector),
            ("src.domains.briefing.service.record_surface_consultations", record),
            ("src.domains.briefing.progressive.out_of_turn_spend", spend),
            ("src.domains.briefing.progressive.file_briefing_act", file_act),
            ("src.domains.briefing.text_cache.get_redis_cache", redis),
            ("src.domains.briefing.progressive.get_redis_cache", redis),
            ("src.domains.briefing.progressive.TEXT_POLL_SECONDS", 0.01),
            (
                "src.domains.briefing.progressive.person_inputs_digest",
                AsyncMock(return_value="person"),
            ),
            (
                "src.domains.briefing.service.generate_greeting",
                AsyncMock(return_value=("Bonjour.", MODEL_USAGE)),
            ),
        ):
            stack.enter_context(patch(target, value))
        yield register


__all__ = ["MODEL_USAGE", "MORNING", "Register", "progressive_installed"]
