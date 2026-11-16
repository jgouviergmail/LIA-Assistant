"""A learning's words exist on both sides, and every outcome can be read (ADR-383).

The settings page tells a learning by its ``outcome`` (``apps/web/src/types/writing-style.ts``)
and says it in the six languages (``settings.writing_style.outcome.<outcome>``). An outcome
the API sends that the page does not know is a learning nobody is told about; a field
renamed on one side is a page reading ``undefined``. The API is the authority (amendment
2026-11-16): this test holds the web copy to it, reading the TypeScript source rather than
a generated artefact, which would be a third place to keep in step.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import get_args

import pytest
from pydantic import BaseModel

from src.domains.agents.emails.writing_style import LearningOutcome
from src.domains.tool_assists.style_learning import WritingStyleLearning
from src.domains.writing_style.schemas import WritingStyleResponse
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

LOCALES = ("en", "fr", "de", "es", "it", "zh")


def _web() -> Path:
    return Path(repo_root_or_skip()) / "apps" / "web"


def _types_source() -> str:
    return (_web() / "src" / "types" / "writing-style.ts").read_text(encoding="utf-8")


def _union(source: str, name: str) -> set[str]:
    """Read one ``export type NAME = 'a' | 'b';`` union of string literals."""
    match = re.search(rf"export type {name} =(.*?);", source, re.S)
    assert match, f"{name} is not declared as a union of string literals"
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


def _interface_fields(source: str, name: str) -> set[str]:
    """Read the field names of one ``export interface NAME { ... }``."""
    match = re.search(rf"export interface {name} \{{(.*?)\n\}}", source, re.S)
    assert match, f"{name} is not declared as an interface"
    return set(re.findall(r"^\s+([a-z_]+): ", match.group(1), re.M))


def test_the_web_knows_exactly_the_outcomes_the_api_sends() -> None:
    known = _union(_types_source(), "WritingStyleLearningOutcome")

    assert known == set(get_args(LearningOutcome))


@pytest.mark.parametrize(
    ("interface", "model"),
    [("WritingStyle", WritingStyleResponse), ("WritingStyleLearning", WritingStyleLearning)],
)
def test_the_web_reads_exactly_the_fields_the_api_answers(
    interface: str, model: type[BaseModel]
) -> None:
    assert _interface_fields(_types_source(), interface) == set(model.model_fields)


@pytest.mark.parametrize("locale", LOCALES)
def test_every_outcome_is_said_in_every_language(locale: str) -> None:
    raw = (_web() / "locales" / locale / "translation.json").read_text(encoding="utf-8")
    said = json.loads(raw)["settings"]["writing_style"]["outcome"]

    missing = [name for name in get_args(LearningOutcome) if not str(said.get(name) or "").strip()]

    assert not missing, f"{locale}: outcomes the API sends and nobody can read: {missing}"
