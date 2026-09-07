"""Versioned prompt loading for the telephony domain.

The prompt FILES live in the central store with every other prompt
(``src/domains/agents/prompts/v1/`` — absolute repo rule: one store for all
prompts, entries mirrored in the agents ``PromptName`` Literal). This loader
reads them by FILESYSTEM PATH only, so telephony still does NOT import the
agents package — the ``agents ↔ telephony`` import cycle stays broken (audit
T2). It is a minimal cached file reader; telephony has only two prompts and
needs none of the agents loader's hash-validation / metrics machinery.

This loader delegates the FILE READ to ``core.prompt_store``: the same
byte-identical reader had grown in three domains, and a fourth was about to
join them. What stays here is what is domain-specific — which prompts this
domain may ask for, and the exception its callers catch.
"""

from __future__ import annotations

from typing import Literal

from src.core.prompt_store import PromptFileError, read_prompt_file

TelephonyPromptName = Literal[
    "telephony_agent_system_prompt",
    "telephony_synthesis_prompt",
]


class TelephonyPromptError(Exception):
    """Raised when a telephony prompt file cannot be loaded."""


def load_telephony_prompt(name: TelephonyPromptName, version: str = "v1") -> str:
    """Load a telephony prompt from ``prompts/<version>/<name>.txt``.

    Args:
        name: Prompt file stem (without ``.txt``).
        version: Prompt version directory (default ``v1``).

    Returns:
        The prompt text.

    Raises:
        TelephonyPromptError: If the file does not exist or cannot be read.
    """
    try:
        return read_prompt_file(name, version)
    except PromptFileError as exc:
        raise TelephonyPromptError(f"Telephony prompt {name!r}: {exc}") from exc
