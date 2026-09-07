"""Versioned prompt loading for the document_generation domain.

The prompt FILE lives in the central store with every other prompt
(``src/domains/agents/prompts/v1/`` — absolute repo rule: one store for all
prompts, entries mirrored in the agents ``PromptName`` Literal). This loader
reads it by FILESYSTEM PATH only, so document_generation does NOT import the
agents package — otherwise ``agents.tools.document_generation_tools`` (which
imports this domain's service) would close an ``agents ↔ document_generation``
runtime import cycle (F009 ratchet). Same doctrine as
``telephony/prompts/loader.py`` (audit T2).

This loader delegates the FILE READ to ``core.prompt_store``: the same
byte-identical reader had grown in three domains, and a fourth was about to
join them. What stays here is what is domain-specific — which prompts this
domain may ask for, and the exception its callers catch.
"""

from __future__ import annotations

from typing import Literal

from src.core.prompt_store import PromptFileError, read_prompt_file

DocumentPromptName = Literal["document_generation_prompt"]


class DocumentPromptError(Exception):
    """Raised when a document-generation prompt file cannot be loaded."""


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
    try:
        return read_prompt_file(name, version)
    except PromptFileError as exc:
        raise DocumentPromptError(f"Cannot load prompt {name!r}: {exc}") from exc
