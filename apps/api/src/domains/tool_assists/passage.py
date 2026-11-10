"""What LIA does on a passage the person selected in what they read (owner, 2026-11-07).

The Tools' selection bubble sends the passage it shows: a message's text or a file's words, a third
party's words either way. It reaches the model wrapped as external content below the marker, so a
passage addressed to an assistant is read, never obeyed. Explain, simplify and ask are one versioned
prompt, the question being the person's own words; a translation goes through the one translation
door (`text.translate_text`), into the reader's language. Nothing is read from a provider: the page
sent what it shows, the person's own selection.
"""

from __future__ import annotations

from enum import Enum
from typing import Final, Literal, get_args

from src.core.external_content import wrap_external_content
from src.core.i18n import get_language_name
from src.domains.agents.prompts import load_prompt
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import ask_slot, assist_line
from src.domains.tool_assists.text import WrittenText, translate_text, written_words

#: Where a passage was read: what the Tools show.
PassageOrigin = Literal["mail", "file", "chat", "page"]

#: How the wrapper names a passage's source to the model.
_SOURCE_TYPE: Final[dict[str, str]] = {
    "mail": "email",
    "file": "document",
    "chat": "conversation",
    "page": "page",
}


def assert_passage_origins_complete() -> None:
    """Every declared origin has exactly one external-content label."""
    assert set(_SOURCE_TYPE) == set(get_args(PassageOrigin)), "Passage origins are incomplete"


class PassageAct(str, Enum):
    """What the person asks of a passage."""

    EXPLAIN = "explain"
    TRANSLATE = "translate"
    SIMPLIFY = "simplify"
    ASK = "ask"
    SUMMARIZE = "summarize"


async def act_on_passage(
    run: AssistRun,
    passage: str,
    act: PassageAct,
    question: str | None,
    *,
    origin: PassageOrigin,
) -> str:
    """One act on a passage, in the reader's language.

    Args:
        run: The assist's run.
        passage: The words the person selected, as the page shows them.
        act: What they ask of it.
        question: Their question, for ``ask`` alone.
        origin: Where the passage was read.

    Returns:
        The words proposed.

    Raises:
        BaseAPIException: No usable answer came.
    """
    language_name = get_language_name(run.language)
    received = wrap_external_content(
        passage, source_url=f"selection:{origin}", source_type=_SOURCE_TYPE[origin]
    )
    if act is PassageAct.TRANSLATE:
        return await translate_text(run, received, language_name)
    prompt = load_prompt("tool_assist_passage_prompt").format(
        act=act.value,
        language=language_name,
        question=(
            f"{assist_line('passage_question')} {question}\n"
            if act is PassageAct.ASK and question
            else ""
        ),
        passage=received,
    )
    return written_words(await ask_slot(run, prompt, WrittenText))


__all__ = ["PassageAct", "PassageOrigin", "act_on_passage"]
