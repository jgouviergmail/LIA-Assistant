"""Versioned prompt loading for the meetings domain (ADR-258).

The prompt FILE lives in the central store with every other prompt
(``src/domains/agents/prompts/v1/``, mirrored in the agents ``PromptName``
Literal). This loader reads it by FILESYSTEM PATH only, so the meetings domain
does NOT import the agents package — ``agents.tools.meetings_tools`` imports
this domain, and the reverse edge would close a runtime cycle (F009 ratchet).
Same doctrine as ``document_generation/prompts.py`` and the telephony loader.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

# Central prompt store, reached by path (never by importing the agents package).
_PROMPTS_DIR = Path(__file__).parents[1] / "agents" / "prompts"

MeetingPromptName = Literal[
    "meeting_synthesis_prompt",
    "meeting_condense_prompt",
    "meeting_template_selection_prompt",
    "meeting_transcript_rewrite_prompt",
]


class MeetingPromptError(Exception):
    """Raised when a meetings prompt file cannot be loaded."""


@lru_cache(maxsize=4)
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
    path = _PROMPTS_DIR / version / f"{name}.txt"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MeetingPromptError(f"Cannot load prompt {name!r} ({path})") from exc


def build_messages(system: str, human: str) -> list[BaseMessage]:
    """The system + human pair every meetings model call sends."""
    return [SystemMessage(content=system), HumanMessage(content=human)]
