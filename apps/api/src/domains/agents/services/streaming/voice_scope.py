"""What the spoken comment of a tool turn may speak of: what the answer retained.

The agent-mode voice is written by a model of its own (the ``voice_comment`` slot)
while the answer is still being written, so that the first audio comes early
(ADR-082). It was handed the turn's records as the tools left them — before the
answer had chosen among them — and it chose for itself. Measured 2026-10-14 on a
dev instance: a written answer retained four places of twenty-two records and led
with the one its own computation favoured; the voice, handed all twenty-two, named
one the text never did (5 replays in 5). What it was handed also depended on WHEN
the records were captured — read at the end of the stream they are the response
node's own selection, read when the tools finished they are all of them — and the
voice could start before the answer existed, on a step event while the response
model was still reasoning (4 voiced tool turns of 22).

The answer declares what it retains at character 0, in ``<relevant_ids>``, and the
tag filter has read that declaration before the answer's first visible character.
The scope holds the turn's latest records until then, offers nothing before, and
decides once:

- a declaration naming known records: those records, in the declared order,
  introduced to the comment as the answer's selection, its lead first;
- anything else — a declaration naming none, ids no record matches, or no
  declaration at all: nothing, and the voice reads the answer itself, as it already
  did when the end-of-stream records were empty. A record the answer did not
  declare is never spoken of, whatever the display mode shows.

The order alone did not carry the answer's choice: measured on the same turn, the
comment handed the four places in the answer's order ranked them by rating and led
with another one 9 times in 9; told as well that the answer puts the first
forward, it led with the answer's choice 4 times in 4 (``voice_comment_context_lines.txt``).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Final, Literal

from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.agents.utils.registry_filtering import (
    relevant_ids_declared_in,
    select_registry_in_declared_order,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: When the scope decided: on the answer's first visible character, or at the end
#: of the stream when no records were held before the answer.
Moment = Literal["answer_start", "stream_end"]

#: The versioned lines file telling the comment what its results are.
VOICE_CONTEXT_LINES: Final[str] = "voice_comment_context_lines"


def voice_context_of(records: dict[str, Any], language: str) -> str:
    """The context the spoken comment reads for the records it may speak of.

    Records only ever reach the comment as the answer's declared selection
    (:class:`VoiceScope`), so they are always introduced as such.

    Args:
        records: The records the scope decided the comment may speak of.
        language: The listener's language, for the summary's labels.

    Returns:
        The records' summary under the line naming them the answer's selection,
        or an empty string when there is nothing to summarise.
    """
    from src.domains.agents.formatters.text_summary import generate_text_summary_for_llm

    summary = generate_text_summary_for_llm(records, language)
    if not summary:
        return summary
    lines = dict(parse_prompt_sections(read_prompt_file(VOICE_CONTEXT_LINES), 2))
    return f"{lines['answer_selection']}\n\n{summary}"


class VoiceScope:
    """The records one answer's spoken comment may speak of, decided once.

    One instance per stream, beside the tag filter that hands it the declaration.
    ``registry`` stays None until the decision, and the voice coordinator starts
    only once it is set — so the voice never speaks ahead of the answer.
    """

    def __init__(self) -> None:
        #: What the spoken comment may speak of: None until decided, and when nothing.
        self.registry: dict[str, Any] | None = None
        self._records: dict[str, Any] | None = None
        self._declared: list[str] | None = None
        self._decided = False

    @property
    def decided(self) -> bool:
        """Whether the scope already decided what the comment may speak of."""
        return self._decided

    def capture(self, records: dict[str, Any]) -> bool:
        """Hold the turn's latest records until the answer begins.

        The latest wins: the initiative node merges its own records into the turn
        after the tools, and the answer may declare them.

        Args:
            records: The current turn's registry, serialized.

        Returns:
            Whether the held records changed (an empty set changes nothing).
        """
        if self._decided or not records or records.keys() == (self._records or {}).keys():
            return False
        self._records = records
        return True

    def read(self, declarations: Iterable[str]) -> None:
        """Keep the first ``<relevant_ids>`` declaration the answer makes.

        Args:
            declarations: The paired tags the tag filter removed since it was last asked.
        """
        for declaration in declarations:
            if self._declared is None:
                self._declared = relevant_ids_declared_in(declaration)

    def answer_began(self, text: str) -> None:
        """Decide on the answer's first visible character, its declaration read.

        Args:
            text: What the reader receives of the answer now; whitespace alone is
                not the answer yet (a model may open on a newline before the tag).
        """
        if self._records is not None and text.strip():
            self._decide(self._records, "answer_start")

    def settle(self, records: dict[str, Any]) -> None:
        """The end of the stream: decide from its records if nothing was decided.

        Args:
            records: The current turn's records at the end of the stream.
        """
        if records:
            self._decide(records, "stream_end")

    def _decide(self, records: dict[str, Any], moment: Moment) -> None:
        if self._decided:
            return
        self._decided = True
        self._records = None
        retained = (
            select_registry_in_declared_order(records, self._declared) if self._declared else {}
        )
        self.registry = retained or None
        logger.info(
            "voice_comment_scope_decided",
            moment=moment,
            source="answer_selection" if retained else "answer_text",
            declaration=(
                "absent" if self._declared is None else "declared" if self._declared else "empty"
            ),
            records_count=len(records),
            spoken_count=len(retained),
        )
