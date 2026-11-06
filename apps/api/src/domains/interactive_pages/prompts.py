"""Versioned prompt loading for the interactive pages domain.

The prompt FILE lives in the central store with every other prompt, entry mirrored
in the agents ``PromptName`` Literal. Read by path through ``core.prompt_store``:
``agents.tools.interactive_page_tools`` imports this domain, so importing the
agents package from here would close a runtime cycle (F009 ratchet).
"""

from __future__ import annotations

from src.core.prompt_store import read_prompt_file

PAGE_PROMPT_NAME = "interactive_page_prompt"


def load_page_prompt() -> str:
    """Load the page writer's prompt from the central store.

    Returns:
        The prompt text.

    Raises:
        PromptFileError: When the file does not exist or cannot be read.
    """
    return read_prompt_file(PAGE_PROMPT_NAME, "v1")
