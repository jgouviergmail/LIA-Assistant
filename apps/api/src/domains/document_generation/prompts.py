"""Versioned prompt loading for the document_generation domain.

The prompt FILE lives in the central store with every other prompt
(``src/domains/agents/prompts/v1/`` — absolute repo rule: one store for all
prompts, entries mirrored in the agents ``PromptName`` Literal). This loader
reads it by FILESYSTEM PATH only, so document_generation does NOT import the
agents package — otherwise ``agents.tools.document_generation_tools`` (which
imports this domain's service) would close an ``agents ↔ document_generation``
runtime import cycle (F009 ratchet). Same doctrine as
``telephony/prompts/loader.py`` (audit T2).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

# Central prompt store, reached by path (never by importing the agents package).
_PROMPTS_DIR = Path(__file__).parents[1] / "agents" / "prompts"

DocumentPromptName = Literal["document_generation_prompt"]


class DocumentPromptError(Exception):
    """Raised when a document-generation prompt file cannot be loaded."""


@lru_cache(maxsize=4)
def load_document_prompt(name: DocumentPromptName, version: str = "v1") -> str:
    """Load a document-generation prompt from ``prompts/<version>/<name>.txt``.

    Args:
        name: Prompt file stem (without ``.txt``).
        version: Prompt version directory (default ``v1``).

    Returns:
        The prompt text.

    Raises:
        DocumentPromptError: When the file does not exist or cannot be read.
    """
    path = _PROMPTS_DIR / version / f"{name}.txt"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocumentPromptError(f"Cannot load prompt {name!r} ({path})") from exc
