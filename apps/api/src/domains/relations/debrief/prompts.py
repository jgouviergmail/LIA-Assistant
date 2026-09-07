"""Versioned prompt loading for the relationship debrief.

The prompt FILES live in the central store with every other prompt
(``src/domains/agents/prompts/v1/``, mirrored in the agents ``PromptName``
Literal). They are read by PATH through ``core.prompt_store``, so the relations
domain does NOT import the agents package — ``agents.tools.person_tools`` and
``agents.middleware.peer_context_injection`` both import this domain, and the
reverse edge would close an ``agents ↔ relations`` runtime cycle (F009
ratchet). A local import inside a function would only hide that edge, which the
coupling doctrine forbids by name.

Same doctrine, same shape, as ``meetings/prompts.py``,
``document_generation/prompts.py`` and ``telephony/prompts/loader.py``.
"""

from __future__ import annotations

from typing import Literal

from src.core.prompt_store import PromptFileError, read_prompt_file

DebriefPromptName = Literal[
    # What the model is asked to write.
    "relation_debrief_prompt",
    # How a written debrief is framed when it reaches a chat turn.
    "relation_debrief_context_template",
    # The labels and line wording of the injected blocks.
    "relation_debrief_context_sections",
]


class DebriefPromptError(Exception):
    """Raised when a debrief prompt file cannot be loaded."""


def load_debrief_prompt(name: DebriefPromptName, version: str = "v1") -> str:
    """Load a debrief prompt from ``prompts/<version>/<name>.txt``.

    Args:
        name: Prompt file stem (without ``.txt``).
        version: Prompt version directory (default ``v1``).

    Returns:
        The prompt text.

    Raises:
        DebriefPromptError: When the file does not exist or cannot be read.
    """
    try:
        return read_prompt_file(name, version)
    except PromptFileError as exc:
        raise DebriefPromptError(f"Cannot load prompt {name!r}: {exc}") from exc
