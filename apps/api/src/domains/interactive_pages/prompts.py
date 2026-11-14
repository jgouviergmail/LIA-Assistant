"""Versioned prompt loading for the interactive pages domain.

The prompt FILES live in the central store with every other prompt, entries mirrored
in the agents ``PromptName`` Literal. Read by path through ``core.prompt_store``:
``agents.tools.interactive_page_tools`` imports this domain, so importing the
agents package from here would close a runtime cycle (F009 ratchet).
"""

from __future__ import annotations

from functools import lru_cache

from src.core.prompt_store import parse_prompt_sections, read_prompt_file

PAGE_PROMPT_NAME = "interactive_page_prompt"
PAGE_LINES_NAME = "interactive_page_lines"


def load_page_prompt() -> str:
    """Load the page writer's prompt from the central store.

    Returns:
        The prompt text.

    Raises:
        PromptFileError: When the file does not exist or cannot be read.
    """
    return read_prompt_file(PAGE_PROMPT_NAME, "v1")


@lru_cache(maxsize=1)
def load_page_lines() -> dict[str, str]:
    """Load the one-line scaffolds of the page prompt, by key.

    Returns:
        ``{key: template}``, as the lines file declares them.

    Raises:
        PromptFileError: When the file does not exist or cannot be read.
    """
    return dict(parse_prompt_sections(read_prompt_file(PAGE_LINES_NAME, "v1"), 2))
