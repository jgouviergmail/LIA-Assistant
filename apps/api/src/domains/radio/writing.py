"""The model calls of a segment: the analyst's reading, the writer's script, the check.

Both go through the platform's ONE structured-output door, which the orchestrator
hands in already bound to the radio's own LLM slot, the session's run config and
its tracker — so every token lands on the listener's session (ADR-272) and every
call answers to the spending ceilings (a refusal RAISES and ends the session; it is
never taken for a bad script). The prompt is rendered by
:mod:`~src.domains.radio.prompting` and sent as its static part plus the segment's
data (ADR-309).

A call that does not come back with a usable answer — a truncated one is a refusal
(ADR-275), a malformed one too — gives no script, no analysis and no verdict: the
segment is skipped and the antenna moves on. Nothing here retries: the door already did, and a
second paid attempt at the same prompt is the orchestrator's call, not this one's.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import structlog
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from src.core.prompt_layout import single_call_messages
from src.domains.radio.analysis import AnalysisDraft, analysis_facts
from src.domains.radio.checking import CheckDraft, checked_positions, unsupported_positions
from src.domains.radio.constants import SOURCE_LABEL_MAX_CHARS
from src.domains.radio.facts import FactPack, RadioFact, SourceRef
from src.domains.radio.production import WritingRequest
from src.domains.radio.prompting import (
    AnalysisRequest,
    ListenerTaste,
    StationVoice,
    render_analyst_prompt,
    render_verifier_prompt,
    render_writer_prompt,
)
from src.domains.radio.script import ScriptDraft
from src.domains.radio.verification import VerifiedLine
from src.infrastructure.llm.structured_output_errors import (
    StructuredOutputError,
    StructuredOutputTruncatedError,
)

logger = structlog.get_logger(__name__)


class StructuredCall(Protocol):
    """The structured-output door, bound to a slot, a run and a tracker."""

    async def __call__[M: BaseModel](self, messages: list[BaseMessage], schema: type[M]) -> M:
        """Ask the model for an instance of ``schema``."""
        ...


def _refusal(error: StructuredOutputError) -> str:
    return "truncated" if isinstance(error, StructuredOutputTruncatedError) else "unusable"


class ModelScriptWriter:
    """Writes a segment's script with the radio's writer slot."""

    def __init__(
        self,
        *,
        template: str,
        station: StationVoice,
        call: StructuredCall,
        quote_max_chars: int,
        taste: ListenerTaste = ListenerTaste(),
    ) -> None:
        self._template = template
        self._station = station
        self._call = call
        self._quote_max_chars = quote_max_chars
        self._taste = taste

    async def write(self, request: WritingRequest) -> ScriptDraft | None:
        """Write the script, or ``None`` when no usable answer came back."""
        prompt = render_writer_prompt(
            self._template,
            request,
            self._station,
            quote_max_chars=self._quote_max_chars,
            taste=self._taste,
        )
        try:
            return await self._call(single_call_messages(prompt), ScriptDraft)
        except StructuredOutputError as error:
            logger.info("radio_writer_refused", format=request.format.value, reason=_refusal(error))
            return None


class ModelAnalyst:
    """Reads one story's full text with the radio's analyst slot."""

    def __init__(self, *, template: str, station: StationVoice, call: StructuredCall) -> None:
        self._template = template
        self._station = station
        self._call = call

    async def analyse(
        self,
        request: AnalysisRequest,
        *,
        story_key: str,
        min_points: int,
        max_points: int,
    ) -> tuple[RadioFact, ...]:
        """The analysis facts, or none when no usable reading came back.

        Args:
            request: The story and its full text.
            story_key: The story's ledger key.
            min_points: The fewest points asked for.
            max_points: The most points kept.

        Returns:
            The points whose figures the article states, as facts.
        """
        prompt = render_analyst_prompt(
            self._template,
            request,
            self._station,
            min_points=min_points,
            max_points=max_points,
        )
        try:
            draft = await self._call(single_call_messages(prompt), AnalysisDraft)
        except StructuredOutputError as error:
            logger.info("radio_analyst_refused", reason=_refusal(error))
            return ()
        source = SourceRef(
            label=request.outlet[:SOURCE_LABEL_MAX_CHARS],
            url=request.url,
            published_at=request.published_at,
            story_key=story_key,
        )
        return analysis_facts(
            draft,
            article=f"{request.title}\n{request.article}",
            source=source,
            story_key=story_key,
            max_points=max_points,
        )


class ModelLineChecker:
    """Reads a script's sourced lines against their facts with the radio's verifier slot."""

    def __init__(self, *, template: str, station: StationVoice, call: StructuredCall) -> None:
        self._template = template
        self._station = station
        self._call = call

    async def unsupported(
        self, lines: Sequence[VerifiedLine], pack: FactPack
    ) -> frozenset[int] | None:
        """The places of the lines the verifier did not vouch for; ``None`` on no answer."""
        if not checked_positions(lines):
            return frozenset()  # nothing cites a fact: nothing to check, nothing paid
        prompt = render_verifier_prompt(
            self._template, lines, pack, station_name=self._station.station_name
        )
        try:
            draft = await self._call(single_call_messages(prompt), CheckDraft)
        except StructuredOutputError as error:
            logger.info("radio_verifier_refused", format=pack.format.value, reason=_refusal(error))
            return None
        return unsupported_positions(lines, draft.verdicts)


__all__ = ["ModelAnalyst", "ModelLineChecker", "ModelScriptWriter", "StructuredCall"]
