"""Prompt loading for the document_generation domain.

The prompt FILES live in the central store with every other prompt
(``src/domains/agents/prompts/v1/`` — absolute repo rule: one store for all
prompts, entries mirrored in the agents ``PromptName`` Literal). This loader
reads them by FILESYSTEM PATH only, so document_generation does NOT import the
agents package — otherwise ``agents.tools.document_generation_tools`` (which
imports this domain's service) would close an ``agents ↔ document_generation``
runtime import cycle (F009 ratchet). Same doctrine as
``telephony/prompts/loader.py`` (audit T2).

This loader delegates the FILE READ to ``core.prompt_store``: the same
byte-identical reader had grown in three domains, and a fourth was about to
join them. What stays here is what is domain-specific — which prompts this
domain may ask for, how one writer's prompt is composed, and the exception its
callers catch.

The writer reads ONE family's rules. The format is known before the call, and a
report writer has no use for the rules of a deck: the three families cost 191,
273 and 289 tokens and were all sent to every call (measured 2026-11-13). The
common rules come first, the family's next, the request last — so every format
of a family shares one cacheable prefix.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from types import MappingProxyType
from typing import Literal

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.core.prompt_store import PromptFileError, parse_prompt_sections, read_prompt_file
from src.domains.document_generation.schemas import (
    SCHEMA_BY_DOC_TYPE,
    DocumentType,
    SectionedContent,
    SlideContent,
    TabularContent,
)

DocumentPromptName = Literal[
    "document_generation_prompt",
    "document_generation_tabular_prompt",
    "document_generation_sectioned_prompt",
    "document_generation_slides_prompt",
    "document_generation_lines",
]

#: The rules each content family adds to the common ones.
FAMILY_PROMPTS: dict[type, DocumentPromptName] = {
    TabularContent: "document_generation_tabular_prompt",
    SectionedContent: "document_generation_sectioned_prompt",
    SlideContent: "document_generation_slides_prompt",
}

# Boot-time completeness (ADR-085): a family without rules would reach the
# writer with only the common ones.
assert set(FAMILY_PROMPTS) == set(
    SCHEMA_BY_DOC_TYPE.values()
), "FAMILY_PROMPTS must cover every content family"


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


@cache
def document_lines() -> Mapping[str, str]:
    """The writer prompt's one-line scaffolds, ``key -> line`` (read once per process).

    Returns:
        Every line of ``document_generation_lines.txt``, read-only: the mapping
        is shared by every caller of the process.
    """
    return MappingProxyType(
        dict(parse_prompt_sections(load_document_prompt("document_generation_lines"), 2))
    )


def format_label(doc_type: DocumentType) -> str:
    """What the writer is told it writes, e.g. « Word document (.docx) ».

    Args:
        doc_type: The requested format.

    Returns:
        The format's line.

    Raises:
        DocumentPromptError: When the lines file has no line for the format.
    """
    key = f"format.{doc_type.value}"
    try:
        return document_lines()[key]
    except KeyError as exc:
        raise DocumentPromptError(f"document_generation_lines has no {key!r}") from exc


def document_prompt_template(doc_type: DocumentType) -> str:
    """The writer's prompt for one format: common rules, the family's, then the request.

    Args:
        doc_type: The requested format; its family selects the rules.

    Returns:
        The template, still to be formatted with ``prompt_values``.

    Raises:
        DocumentPromptError: When a file is missing or the common prompt lost
            its dynamic-context marker.
    """
    common = load_document_prompt("document_generation_prompt")
    family = load_document_prompt(FAMILY_PROMPTS[SCHEMA_BY_DOC_TYPE[doc_type]])
    head, marker, tail = common.partition(DYNAMIC_CONTEXT_MARKER)
    if not marker:
        raise DocumentPromptError("document_generation_prompt lost its dynamic-context marker")
    return f"{head.rstrip()}\n\n{family.strip()}\n\n{marker}{tail}"
