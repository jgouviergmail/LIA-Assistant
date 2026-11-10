"""What LIA writes on words a person is writing (ADR-372).

These words travel in the request: they are the person's own, in a field that is not saved yet, so
nothing is read from a provider and nothing but the spend is filed. They still reach the model as
data, never as instructions. What comes back is a proposal: an empty one is a failure, never words
to paste.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from src.core.i18n import get_language_name
from src.domains.agents.prompts import load_prompt
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import ask_slot
from src.domains.workbench.errors import ASSIST_FAILED, refuse


class RewriteTone(str, Enum):
    """One change a person can ask of their own words; the prompt defines each."""

    FIX = "fix"
    SHORTER = "shorter"
    FORMAL = "formal"
    WARM = "warm"
    FORMAT = "format"


class WritingKind(str, Enum):
    """What a text is for; the prompt defines each."""

    EVENT_DESCRIPTION = "event_description"
    TASK_NOTES = "task_notes"
    CONTACT_NOTES = "contact_notes"
    AUTO_REPLY = "auto_reply"
    SIGNATURE = "signature"
    DOCUMENT = "document"


class WrittenText(BaseModel):
    """What the model answers."""

    text: str = Field(description="The text alone, plain, ready to use.")


def written_words(answer: WrittenText) -> str:
    """The words of an answer; an empty one is no proposal.

    Args:
        answer: What the model answered.

    Returns:
        Its words, trimmed.

    Raises:
        BaseAPIException: The answer holds no words (``assist_failed``).
    """
    words = answer.text.strip()
    if not words:
        refuse(ASSIST_FAILED)
    return words


async def rewrite_text(run: AssistRun, text: str, tone: RewriteTone) -> str:
    """The person's words with one change.

    Args:
        run: The assist's run.
        text: Their words.
        tone: The change asked.

    Returns:
        The words proposed.
    """
    prompt = load_prompt("tool_assist_rewrite_prompt").format(tone=tone.value, text=text)
    return written_words(await ask_slot(run, prompt, WrittenText))


async def translate_text(run: AssistRun, text: str, target_language: str) -> str:
    """Words in another language.

    Args:
        run: The assist's run.
        text: The words.
        target_language: The language asked, as a person names it.

    Returns:
        The translation.
    """
    prompt = load_prompt("tool_assist_translate_prompt").format(
        target_language=target_language, text=text
    )
    return written_words(await ask_slot(run, prompt, WrittenText))


async def write_text(run: AssistRun, kind: WritingKind, instruction: str) -> str:
    """A short text written from the person's instruction.

    Args:
        run: The assist's run.
        kind: What it is for.
        instruction: What it should say.

    Returns:
        The words proposed.
    """
    prompt = load_prompt("tool_assist_write_prompt").format(
        language_name=get_language_name(run.language), kind=kind.value, instruction=instruction
    )
    return written_words(await ask_slot(run, prompt, WrittenText))
