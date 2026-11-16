"""The execution-mode vocabulary exists in two languages and must say the same thing.

TypeScript cannot import a Python ``Literal``: the chat header's menu, the
ticket and routine field and the badge under an automatic answer read
``apps/web/src/lib/execution-mode.ts``, while the API validates against
``core.constants`` (ADR-070, ADR-390). Twice is where a drift lives: a mode
offered by the frontend only is a choice the API refuses with a 422, a mode the
API accepts that the frontend does not know is one the menu cannot show, and an
engine named on one side only is a badge that never appears.

The backend is the authority; this test holds the frontend copy to it. It
reads the TypeScript source rather than a generated artefact: a generator would
be a third place to keep in step.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from src.core.constants import (
    EXECUTION_ENGINES,
    EXECUTION_MODE_CHOICES,
    AutoModeResolution,
    ExecutionMode,
)
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit


def _frontend_source() -> str:
    """The frontend module that declares the execution vocabularies."""
    path = Path(repo_root_or_skip()) / "apps" / "web" / "src" / "lib" / "execution-mode.ts"
    if not path.exists():  # pragma: no cover - the frontend tree is absent
        pytest.skip("apps/web is not checked out beside apps/api")
    return path.read_text(encoding="utf-8")


def _tuple_values(source: str, name: str) -> set[str]:
    """Read one ``export const NAME = [...] as const`` tuple."""
    match = re.search(rf"export const {name} = \[(.*?)\] as const", source, re.S)
    assert match, f"{name} is not declared as an `as const` tuple"
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


def _union_values(source: str, name: str) -> set[str]:
    """Read one ``export type NAME = 'a' | 'b'`` union of string literals."""
    match = re.search(rf"export type {name} = (.*?);", source, re.S)
    assert match, f"{name} is not declared as a union of string literals"
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


class TestTheFrontendSpeaksTheApiVocabulary:
    def test_the_choices_are_the_api_choices(self) -> None:
        """Every mode a surface offers is one the API stores, and no other."""
        assert _tuple_values(_frontend_source(), "EXECUTION_MODES") == set(EXECUTION_MODE_CHOICES)
        assert set(EXECUTION_MODE_CHOICES) == set(get_args(ExecutionMode))

    def test_the_engines_are_the_api_engines(self) -> None:
        """The badge names exactly the engines a turn can run on."""
        assert _tuple_values(_frontend_source(), "EXECUTION_ENGINES") == set(EXECUTION_ENGINES)

    def test_what_auto_does_here_is_said_alike(self) -> None:
        """The menu has a sentence for every verdict the API can give."""
        assert _union_values(_frontend_source(), "AutoModeResolution") == set(
            get_args(AutoModeResolution)
        )
