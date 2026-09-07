"""Versioned prompt loading for the meetings domain (ADR-258).

The prompt FILE lives in the central store with every other prompt
(``src/domains/agents/prompts/v1/``, mirrored in the agents ``PromptName``
Literal). This loader reads it by FILESYSTEM PATH only, so the meetings domain
does NOT import the agents package — ``agents.tools.meetings_tools`` imports
this domain, and the reverse edge would close a runtime cycle (F009 ratchet).
Same doctrine as ``document_generation/prompts.py`` and the telephony loader.

This loader delegates the FILE READ to ``core.prompt_store``: the same
byte-identical reader had grown in three domains, and a fourth was about to
join them. What stays here is what is domain-specific — which prompts this
domain may ask for, and the exception its callers catch.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.core.prompt_store import PromptFileError, read_prompt_file

MeetingPromptName = Literal[
    "meeting_synthesis_prompt",
    "meeting_condense_prompt",
    "meeting_template_selection_prompt",
    "meeting_transcript_rewrite_prompt",
]


class MeetingPromptError(Exception):
    """Raised when a meetings prompt file cannot be loaded."""


def load_meeting_prompt(name: MeetingPromptName, version: str = "v1") -> str:
    """Load a meetings prompt from ``prompts/<version>/<name>.txt``.

    Args:
        name: Prompt file stem (without ``.txt``).
        version: Prompt version directory (default ``v1``).

    Returns:
        The prompt text.

    Raises:
        MeetingPromptError: When the file does not exist or cannot be read.
    """
    try:
        return read_prompt_file(name, version)
    except PromptFileError as exc:
        raise MeetingPromptError(f"Cannot load prompt {name!r}: {exc}") from exc


def build_messages(system: str, human: str) -> list[BaseMessage]:
    """The system + human pair every meetings model call sends."""
    return [SystemMessage(content=system), HumanMessage(content=human)]
