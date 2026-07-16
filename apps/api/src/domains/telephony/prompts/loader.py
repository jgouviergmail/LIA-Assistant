"""Versioned prompt loading for the telephony domain.

Telephony owns its prompts (``prompts/<version>/*.txt``) and loads them here, so
the domain does NOT import the agents package — this breaks the
``agents ↔ telephony`` import cycle (audit T2). The loader is a minimal cached
file reader; telephony has only two prompts and needs none of the agents
loader's hash-validation / metrics machinery.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

_PROMPTS_DIR = Path(__file__).parent

TelephonyPromptName = Literal[
    "telephony_agent_system_prompt",
    "telephony_synthesis_prompt",
]


class TelephonyPromptError(Exception):
    """Raised when a telephony prompt file cannot be loaded."""


@lru_cache(maxsize=8)
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
    path = _PROMPTS_DIR / version / f"{name}.txt"
    if not path.is_file():
        raise TelephonyPromptError(f"Telephony prompt not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive I/O guard
        raise TelephonyPromptError(f"Failed to read telephony prompt {path}: {exc}") from exc
