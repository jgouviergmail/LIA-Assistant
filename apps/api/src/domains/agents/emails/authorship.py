"""Who writes an e-mail sent in the person's name — ONE door (ADR-383 amendment 2026-11-16).

An e-mail LIA sends, saves or edits for the person has two possible authors: the person,
whose own words are kept exactly, or LIA's e-mail writer, which writes in their voice
(``writing_style``). The agent that calls the tool — the planner or the ReAct loop — is
never one: a text it put in ``body`` itself is what the e-mail must SAY, handed to the
writer, never what it IS. Measured 2026-11-15 on production's ReAct model told that
``body`` was the e-mail's content: it wrote the text itself for 14 of 18 requests of
intent and altered 3 of 12 dictations — and an e-mail no writer wrote follows no style.

The person's own words are the ones they MARKED in their message: in quotes, introduced
by a colon or a line break, or the whole message when it IS the e-mail (an answer to
« what should it say? »). Nothing else is read as dictation: « reply yes to Paul » holds
the word « yes » without dictating it. The rule is lexical, decided on the person's
messages of the turn — the run's own (``LiaRuntimeContext.user_message``, the one text
of the person both engines carry) and, on a run that resumes the turn after a question,
the request it began with (``turn_request``) — and linear: each message is read once,
never once per mark.

A proposed text stays as it is in three cases:

- it is the person's marked words;
- no run context exists: the caller is code (a script, a test), not an agent;
- it is longer than the writer can write back whole (``EMAIL_REWRITE_MAX_SHARE`` of the
  e-mail slot's output budget): a rewrite would cut it, which is said in the log.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Final, Literal

import structlog

from src.core.config import settings
from src.core.constants import EMAIL_REWRITE_MAX_SHARE
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.agents.context.runtime_context import tool_runtime_context
from src.domains.agents.display.plain_text import strip_html_if_markup
from src.domains.agents.emails.writing_style import LLM_TYPE as WRITER_SLOT
from src.domains.agents.utils.token_utils import count_tokens

logger = structlog.get_logger(__name__)

#: A word of any script: letters and digits, never the underscore.
_WORD: Final = re.compile(r"[^\W_]+")
#: The pairs a person types around their own words. Straight single quotes are left out:
#: in French and English they are apostrophes far more often than quotes. Each span stops
#: at the next OPENING mark too, so no character is read twice: a run of « with no » cost
#: 3.8 s on 40 000 characters while the span could run past it (measured 2026-11-16).
_QUOTED: Final = re.compile(
    r'«([^«»]*)»|“([^“”]*)”|"([^"]*)"|„([^„“”]*)[“”]|「([^「」]*)」|『([^『』]*)』|‹([^‹›]*)›'
)
#: What introduces the words after it as the e-mail's own (NFKC folds the full-width colon).
_INTRODUCERS: Final = frozenset(":\n")

#: Why a proposed text ended where it did — a closed vocabulary, logged by count only.
Settlement = Literal["dictated", "rewritten", "too_long"]

#: The tools whose text leaves in the person's name for someone else: each one settles
#: its ``body`` here (``test_authorship_tools.py`` drives every one of them).
WRITING_TOOLS: Final = frozenset(
    {
        "send_email_tool",
        "reply_email_tool",
        "create_mailbox_draft_tool",
        "create_mailbox_reply_draft_tool",
        "update_mailbox_draft_tool",
    }
)
#: The catalogue's other tools carrying a ``body``, left as the agent gives it, and why
#: (``test_email_authorship_registry.py`` holds the two lists to the whole catalogue).
TEXTS_LEFT_AS_GIVEN: Final[dict[str, str]] = {
    "send_email_to_me_tool": (
        "a note to the person's own mailbox: no greeting, no sign-off, no voice to follow"
    ),
    "forward_email_tool": "a forward's note is a line above someone else's words (ADR-383)",
    "create_mailbox_forward_draft_tool": (
        "a forward's note is a line above someone else's words (ADR-383)"
    ),
    "comment_ticket_tool": "a comment on a workboard ticket, never an e-mail",
    "set_vacation_responder_tool": (
        "a mailbox setting: the automatic reply is set verbatim from the card the person "
        "confirms, and no writer serves that setting"
    ),
}


@dataclass(frozen=True, slots=True)
class SettledWords:
    """What a writing tool goes on with.

    Attributes:
        body: The words sent as they stand (the person's own, or a text kept), or None.
        instruction: What LIA's writer must write, or None.
    """

    body: str | None
    instruction: str | None


def _words(text: str) -> list[str]:
    """The words of ``text``, case folded, in order."""
    return [match.group().casefold() for match in _WORD.finditer(text)]


def _quoted_words(message: str) -> list[list[str]]:
    """The words of every span the person put in quotes."""
    spans: list[list[str]] = []
    for match in _QUOTED.finditer(message):
        spans.append(_words(next(group for group in match.groups() if group is not None)))
    return spans


def _introduced_tail(words: list[str], message: str) -> bool:
    """Whether ``message`` ends with ``words``, after a mark that introduces them or alone.

    Args:
        words: The proposed text's words.
        message: The person's message, NFKC-folded.

    Returns:
        True when the message's last words are these and what stands just before them
        holds a colon or a line break — or nothing stands before them at all.
    """
    found = list(_WORD.finditer(message))
    if len(found) < len(words):
        return False
    tail = found[len(found) - len(words) :]
    if [match.group().casefold() for match in tail] != words:
        return False
    if len(found) == len(words):
        return True  # the whole message is the e-mail
    gap = message[found[len(found) - len(words) - 1].end() : tail[0].start()]
    return any(char in _INTRODUCERS for char in gap)


def is_dictated(proposed: str, person_words: str) -> bool:
    """Whether ``proposed`` is words the person marked as the e-mail's own (pure).

    Args:
        proposed: The text the agent passed, plain or HTML.
        person_words: The person's message in the run.

    Returns:
        True for words quoted, introduced by a colon or a line break, or making up the
        whole message; False otherwise, and for a text with no word of its own.
    """
    words = _words(unicodedata.normalize("NFKC", strip_html_if_markup(proposed)))
    if not words:
        return False
    message = unicodedata.normalize("NFKC", person_words)
    if any(span == words for span in _quoted_words(message)):
        return True
    return _introduced_tail(words, message)


@lru_cache(maxsize=1)
def _lines() -> dict[str, str]:
    """The door's wordings, read once from the store."""
    return dict(parse_prompt_sections(read_prompt_file("email_authorship_lines"), 2))


def proposed_header() -> str:
    """The line the writer reads above a text the agent drafted."""
    return _lines()["proposed"]


def _framed(proposed: str, instruction: str | None) -> str:
    """What the writer is asked: the agent's own instruction first, then what it drafted."""
    drafted = f"{proposed_header()}\n{proposed}"
    said = (instruction or "").strip()
    return f"{said}\n\n{drafted}" if said else drafted


def _rewritable(text: str) -> bool:
    """Whether the writer can write ``text`` back whole within its output budget."""
    budget = get_llm_config_for_agent(settings, WRITER_SLOT).max_tokens
    return count_tokens(text) <= budget * EMAIL_REWRITE_MAX_SHARE


def _settled(tool: str, how: Settlement, proposed: str) -> None:
    """Say how a proposed text was settled: counts only, the text is the person's (ADR-317)."""
    logger.info("email_words_settled", tool=tool, settled=how, proposed_chars=len(proposed))


def settle_words(
    *,
    tool: str,
    body: str | None,
    instruction: str | None,
    person_words: tuple[str, ...] | None,
) -> SettledWords:
    """Who writes the text a writing tool was given: the person, or LIA's writer.

    Args:
        tool: The tool asking, for the log.
        body: The text the agent passed as the e-mail's words, if any.
        instruction: What the agent said the e-mail must say, if anything.
        person_words: The person's messages in the turn (``person_words_of``); None
            outside any run.

    Returns:
        The words to send as they stand, and what the writer must write — the agent's
        own text becoming part of the latter unless it is the person's or too long.
    """
    proposed = (body or "").strip()
    if not proposed:
        return SettledWords(body=None, instruction=instruction)
    if person_words is None:
        return SettledWords(body=body, instruction=instruction)
    if any(is_dictated(proposed, words) for words in person_words):
        _settled(tool, "dictated", proposed)
        return SettledWords(body=body, instruction=instruction)
    flattened = strip_html_if_markup(proposed).strip()
    if not _rewritable(flattened):
        _settled(tool, "too_long", proposed)
        return SettledWords(body=body, instruction=instruction)
    _settled(tool, "rewritten", proposed)
    return SettledWords(body=None, instruction=_framed(flattened, instruction))


def person_words_of(runtime: object) -> tuple[str, ...] | None:
    """The person's messages in the tool's turn, or None when it runs outside one.

    A run that resumes the turn after a question carries the person's answer as its
    message: the request the turn began with is read too, so words dictated in it
    stay the person's (« send to Paul: “…” », then « which Paul? », then the send).

    Args:
        runtime: The injected ``ToolRuntime`` (or None).

    Returns:
        ``user_message`` and ``turn_request``, the empty and the repeated left out;
        None without a run context.
    """
    context = tool_runtime_context(runtime)
    if context is None:
        return None
    said = (context.user_message, context.turn_request)
    return tuple(dict.fromkeys(text for text in said if text))


__all__ = [
    "TEXTS_LEFT_AS_GIVEN",
    "WRITING_TOOLS",
    "SettledWords",
    "is_dictated",
    "person_words_of",
    "proposed_header",
    "settle_words",
]
