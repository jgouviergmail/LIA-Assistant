"""Reading a versioned prompt file without importing the agents package.

Every prompt in this codebase lives in ONE store,
``src/domains/agents/prompts/<version>/<name>.txt`` — an absolute repo rule, so
a prompt is always found in the same place and always reviewed as text.

But several domains that need a prompt are themselves IMPORTED by the agents
layer: ``agents.tools.meetings_tools`` imports ``meetings``,
``agents.tools.document_generation_tools`` imports ``document_generation``, and
``agents.tools.person_tools`` imports ``relations``. Reaching for the agents
prompt loader from any of them closes a runtime import cycle (F009 ratchet),
and a local import inside a function would only HIDE that edge, which the
coupling doctrine forbids explicitly.

So they read the file by PATH. Three of them had grown their own byte-identical
copy of that reader (telephony, meetings, document_generation) before the
relationship debrief was about to add a fourth. This is that reader, once, in
``core`` — the layer everything already imports, so no domain has to create an
edge to another to use it (the argument ``resolve_user_timezone`` settled for
the timezone helper).

Each domain keeps its own typed wrapper and its own exception: what a caller
may ask for is a domain question, and *this* module only answers "here is the
text, or I could not read it".
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, overload

#: The one prompt store. Reached by path, never by importing the agents package.
PROMPT_STORE = Path(__file__).parents[1] / "domains" / "agents" / "prompts"


class PromptFileError(Exception):
    """A prompt file could not be read (absent, unreadable, wrong version)."""


@lru_cache(maxsize=64)
def read_prompt_file(name: str, version: str = "v1") -> str:
    """Read one prompt from the central store.

    Cached: a prompt file is immutable for the life of a process, and the
    domains calling this render one on every turn.

    Args:
        name: Prompt file stem, without ``.txt``.
        version: Version directory (default ``v1``).

    Returns:
        The prompt text.

    Raises:
        PromptFileError: When the file does not exist or cannot be read.
    """
    path = PROMPT_STORE / version / f"{name}.txt"
    if not path.is_file():
        raise PromptFileError(f"prompt not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptFileError(f"cannot read prompt {name!r} ({path}): {exc}") from exc


@overload
def parse_prompt_sections(text: str, columns: Literal[2]) -> list[tuple[str, str]]: ...


@overload
def parse_prompt_sections(text: str, columns: Literal[3]) -> list[tuple[str, str, str]]: ...


@overload
def parse_prompt_sections(text: str, columns: int) -> list[tuple[str, ...]]: ...


def parse_prompt_sections(
    text: str, columns: int
) -> list[tuple[str, ...]] | list[tuple[str, str]] | list[tuple[str, str, str]]:  # noqa: E501
    """Parse a ``key|Header|template`` prompt file into its rows, in file order.

    The one implementation of a shape three modules had each written for
    themselves (the memory profile headers, the peer-context sections and the
    relationship-debrief sections — prompt audit 2026-09-12). Blank lines and
    ``#`` comments are ignored; a line short of a column is not a section and
    is skipped rather than completed by guesswork; the LAST cell keeps any
    later ``|`` (a line template may legitimately contain one).

    Args:
        text: The file content (LF or CRLF).
        columns: Number of cells per row, at least 2.

    Returns:
        One tuple of ``columns`` stripped cells per section line.

    Raises:
        ValueError: When ``columns`` is below 2 — a one-column file is not a table.
    """
    if columns < 2:
        raise ValueError(f"a sections file has at least 2 columns, got {columns}")
    rows: list[tuple[str, ...]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.count("|") < columns - 1:
            continue
        rows.append(tuple(cell.strip() for cell in line.split("|", columns - 1)))
    return rows
