"""Rewriting a whole transcript, part by part (ADR-259, the ``transcript`` section kind).

A section of kind ``transcript`` is not filled by the single synthesis call:
its output is as long as the meeting, and the synthesis slot caps its output
(``max_tokens``). The transcript is therefore cut into parts AT TURN
BOUNDARIES, each part rewritten by one structured call under the section's
instruction, and the answers stitched back in order.

Two rules the model is not trusted with:

- **A missing index is a truncation signal, not a gap to paper over.**
  ``extract_json_payload`` salvages a cut-off answer as a VALID but short list,
  so when an index of the input is absent from the answer the part is split in
  two and each half rewritten once more; only after that do the still-missing
  turns keep their original text — counted and logged, never silent.
- **A short answer lost content.** A part whose rewritten text is under
  ``MEETINGS_REWRITE_MIN_RATIO`` of its input is retried once, then kept.

The part size follows the EFFECTIVE slot configuration (an administrator may
lower ``max_tokens`` in the database), never the default alone.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.constants import (
    MEETINGS_CHARS_PER_TOKEN_ESTIMATE,
    MEETINGS_LLM_TYPE,
    MEETINGS_REWRITE_MIN_RATIO,
    MEETINGS_REWRITE_OUTPUT_SAFETY,
    MEETINGS_REWRITE_PART_CHARS,
)
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.meetings.prompts import build_messages, load_meeting_prompt
from src.domains.meetings.schemas import (
    SectionKind,
    TemplateSection,
    TranscriptLine,
    TranscriptTurn,
)
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output_with_retry
from src.infrastructure.llm.token_capture import TokenCaptureHandler

logger = structlog.get_logger(__name__)

#: ``TranscriptLine.text`` bound (schemas.py).
_LINE_MAX_CHARS = 4000


class RewrittenTurn(BaseModel):
    """One rewritten turn, keyed by the index it was given."""

    index: int = Field(description="The input index, copied.")
    text: str = Field(description="The rewritten turn.")


class RewrittenTurns(BaseModel):
    """The model's answer for one part: one entry per input turn."""

    turns: list[RewrittenTurn] = Field(default_factory=list)


def part_chars_for(config: Any) -> int:
    """Characters one part may hold so its OUTPUT stays under the slot's ``max_tokens``.

    A rewrite is about as long as its input; the safety factor keeps JSON framing
    and a verbose run under the cap.
    """
    from_config = int(
        int(config.max_tokens) * MEETINGS_CHARS_PER_TOKEN_ESTIMATE * MEETINGS_REWRITE_OUTPUT_SAFETY
    )
    return min(MEETINGS_REWRITE_PART_CHARS, from_config)


def split_turns(
    turns: Sequence[TranscriptTurn], *, part_chars: int | None = None
) -> list[list[int]]:
    """Cut the turn indexes into parts of at most ``part_chars`` characters, never inside a turn.

    A single turn longer than ``part_chars`` is its own part. ``part_chars``
    defaults to the constant AT CALL TIME.
    """
    limit = part_chars or MEETINGS_REWRITE_PART_CHARS
    parts: list[list[int]] = []
    current: list[int] = []
    size = 0
    for index, turn in enumerate(turns):
        length = len(turn.text)
        if current and size + length > limit:
            parts.append(current)
            current, size = [], 0
        current.append(index)
        size += length
    if current:
        parts.append(current)
    return parts


def _render_part(turns: Sequence[TranscriptTurn], indexes: Sequence[int]) -> str:
    return "\n".join(f"{i} | {turns[i].speaker}: {turns[i].text}" for i in indexes)


class _Rewriter:
    """One instruction, one model, one transcript: the stateful part of the pipeline."""

    def __init__(
        self,
        turns: Sequence[TranscriptTurn],
        instruction: str,
        *,
        provider: str,
        capture: TokenCaptureHandler,
    ) -> None:
        self.turns = turns
        self.instruction = instruction
        self.provider = provider
        self.capture = capture
        self.llm = get_llm(MEETINGS_LLM_TYPE)
        self.system = load_meeting_prompt("meeting_transcript_rewrite_prompt")
        self.texts: dict[int, str] = {}
        self.kept_original = 0

    async def _ask(self, indexes: Sequence[int]) -> dict[int, str]:
        human = f"INSTRUCTION:\n{self.instruction}\n\nTURNS:\n{_render_part(self.turns, indexes)}"
        answer = await get_structured_output_with_retry(
            self.llm,
            build_messages(self.system, human),
            RewrittenTurns,
            provider=self.provider,
            node_name=f"{MEETINGS_LLM_TYPE}_rewrite",
            config=RunnableConfig(callbacks=[self.capture]),
        )
        wanted = set(indexes)
        return {
            turn.index: turn.text.strip()
            for turn in answer.turns
            if turn.index in wanted and turn.text.strip()
        }

    def _is_short(self, indexes: Sequence[int], texts: dict[int, str]) -> bool:
        expected = sum(len(self.turns[i].text) for i in indexes)
        produced = sum(len(texts.get(i, "")) for i in indexes)
        return produced < MEETINGS_REWRITE_MIN_RATIO * expected

    async def rewrite_part(self, indexes: Sequence[int], *, may_split: bool) -> None:
        texts = await self._ask(indexes)
        missing = [i for i in indexes if i not in texts]
        if missing and may_split and len(indexes) > 1:
            # Truncation signal: halve the part and ask again, once.
            middle = len(indexes) // 2
            await self.rewrite_part(indexes[:middle], may_split=False)
            await self.rewrite_part(indexes[middle:], may_split=False)
            return
        if may_split and not missing and self._is_short(indexes, texts):
            logger.info("meeting_rewrite_part_short", turns=len(indexes))
            texts = await self._ask(indexes)
        for index in indexes:
            if index in texts:
                self.texts[index] = texts[index]
            else:
                self.kept_original += 1

    async def run(self, part_chars: int) -> list[TranscriptLine]:
        for part in split_turns(self.turns, part_chars=part_chars):
            await self.rewrite_part(part, may_split=True)
        if self.kept_original:
            logger.warning(
                "meeting_rewrite_turns_kept_original",
                count=self.kept_original,
                turns=len(self.turns),
            )
        lines: list[TranscriptLine] = []
        for index, turn in enumerate(self.turns):
            text = self.texts.get(index) or turn.text
            lines.append(
                TranscriptLine(
                    speaker=turn.speaker[:40] or "?",
                    start=turn.start,
                    text=text[:_LINE_MAX_CHARS] or "…",
                )
            )
        return lines


async def rewrite_transcript(
    turns: Sequence[TranscriptTurn],
    instruction: str,
    *,
    provider: str,
    capture: TokenCaptureHandler,
) -> list[TranscriptLine]:
    """Rewrite every turn under ``instruction``; the result keeps the speakers and the order.

    Raises:
        StructuredOutputError: When the model never produced a valid answer for
            a part (the job classifies it as a transient synthesis failure).
    """
    config = get_llm_config_for_agent(settings, MEETINGS_LLM_TYPE)
    rewriter = _Rewriter(turns, instruction, provider=provider, capture=capture)
    return await rewriter.run(part_chars_for(config))


async def rewrite_for_template(
    turns: Sequence[TranscriptTurn],
    template: Sequence[TemplateSection],
    *,
    provider: str,
    capture: TokenCaptureHandler,
) -> dict[str, list[TranscriptLine]]:
    """One rewrite per DISTINCT instruction among the template's transcript sections.

    Returns:
        Section key → rewritten lines (sections sharing an instruction share the list).
    """
    by_instruction: dict[str, list[str]] = {}
    for section in template:
        if section.kind is SectionKind.TRANSCRIPT:
            by_instruction.setdefault(section.instruction, []).append(section.key)
    rewritten: dict[str, list[TranscriptLine]] = {}
    for instruction, keys in by_instruction.items():
        lines = await rewrite_transcript(turns, instruction, provider=provider, capture=capture)
        for key in keys:
            rewritten[key] = lines
    return rewritten


__all__ = [
    "RewrittenTurn",
    "RewrittenTurns",
    "part_chars_for",
    "rewrite_for_template",
    "rewrite_transcript",
    "split_turns",
]
