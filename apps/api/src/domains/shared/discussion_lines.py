"""The model-facing words of the discussion source adapters, read from the prompt store.

An evidence's excerpt frame and its usage nuance are what a discussion model reads
beside the facts, so they live in a versioned prompt file, never in a ``.py``
(ADR-284). The store is read by path through ``core`` (``read_prompt_file``), so no
adapter domain imports the agents package to reach it.
"""

from functools import lru_cache

from src.core.prompt_store import parse_prompt_sections, read_prompt_file

#: The evidence lines' prompt file; each source adapter renders only its own keys.
DISCUSSION_EVIDENCE_LINES = "discussion_evidence_lines"


@lru_cache(maxsize=1)
def evidence_lines() -> dict[str, str]:
    """Return the evidence frames and nuances (``key|template``), read once.

    Returns:
        The templates by key.

    Raises:
        PromptFileError: The prompt file cannot be read.
    """
    return dict(parse_prompt_sections(read_prompt_file(DISCUSSION_EVIDENCE_LINES), 2))
