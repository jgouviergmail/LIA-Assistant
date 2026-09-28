"""The draft summaries take each language's own label punctuation (ADR-323).

A summary reaches the reader as a card title's fallback and as the registry
item's summary: its colon is the language's, like every label the door joins —
a no-break space before the French one, the full-width one in Chinese, none
before it elsewhere. Fifteen Chinese rows wrote an ASCII colon.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from src.core.i18n_drafts import DRAFT_SUMMARY_LABELS, label_separator
from src.core.i18n_types import Language

pytestmark = pytest.mark.unit

_NBSP = chr(0xA0)
_FULL_WIDTH_COLON = chr(0xFF1A)

#: What may never appear in a language's summaries.
_FORBIDDEN = {
    "fr": re.compile(f"(?<!{_NBSP})[:{_FULL_WIDTH_COLON}]"),
    "zh-CN": re.compile(":"),
}
_ELSEWHERE = re.compile(rf"\s:|{_FULL_WIDTH_COLON}")


@pytest.mark.parametrize(
    ("language", "separator"),
    [
        ("fr", f"{_NBSP}: "),
        ("en", ": "),
        ("de", ": "),
        ("es", ": "),
        ("it", ": "),
        ("zh-CN", _FULL_WIDTH_COLON),
    ],
)
def test_the_door_s_separator_in_each_language(language: str, separator: str) -> None:
    """Every surface joins a label through this one value: pinned for all six."""
    assert label_separator(language) == separator


@pytest.mark.parametrize("language", sorted(DRAFT_SUMMARY_LABELS))
def test_every_summary_colon_is_the_language_s(language: Language) -> None:
    forbidden = _FORBIDDEN.get(language, _ELSEWHERE)
    wrong = {
        key: value
        for key, value in DRAFT_SUMMARY_LABELS[language].items()
        if forbidden.search(value)
    }
    assert not wrong, f"{language}: {sorted(wrong)}"


# ---------------------------------------------------------------------------
# The French entries of the tables a person reads in a dialog or a register
# ---------------------------------------------------------------------------

_CORE = Path(__file__).resolve().parents[3] / "src" / "core"

#: Tables whose French is read by a MODEL, never by a person (ADR-323 lists
#: them): their typography is not the reader's business.
_MODEL_FACING = frozenset({"_REFORMULATION_TEMPLATES", "_REJECT_ENRICHED_MESSAGE"})

_PLAIN_BEFORE = re.compile(r" [?!:;]")
_PLAIN_INSIDE = re.compile(r"« | »")


def _targets(statement: ast.stmt) -> list[ast.expr]:
    """What an ``=`` or annotated assignment at module level binds (an
    augmented assignment, a loop target or an import binds nothing here)."""
    if isinstance(statement, ast.AnnAssign):
        return [statement.target]
    return list(statement.targets) if isinstance(statement, ast.Assign) else []


def _strings_under_french_keys(table: ast.Dict) -> list[tuple[int, str]]:
    """(line, text) of every string under one table's ``"fr"`` key."""
    return [
        (sub.lineno, sub.value)
        for key, value in zip(table.keys, table.values, strict=True)
        if isinstance(key, ast.Constant) and key.value == "fr"
        for sub in ast.walk(value)
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
    ]


def _french_values(module: str) -> list[tuple[int, str]]:
    """(line, text) of every string reached from a ``"fr"`` key of a table."""
    return _french_values_of((_CORE / module).read_text(encoding="utf-8"))


def _french_values_of(source: str) -> list[tuple[int, str]]:
    """(line, text) of every string a ``"fr"`` key reaches in a module's source."""
    tree = ast.parse(source)
    found: list[tuple[int, str]] = []
    for statement in tree.body:
        if any(isinstance(t, ast.Name) and t.id in _MODEL_FACING for t in _targets(statement)):
            continue
        for node in ast.walk(statement):
            if isinstance(node, ast.Dict):
                found.extend(_strings_under_french_keys(node))
    return found


@pytest.mark.parametrize("module", ["i18n_hitl.py", "i18n_effects.py", "i18n_drafts.py"])
def test_french_takes_a_no_break_space_before_its_high_punctuation(module: str) -> None:
    """A dialog mixing no-break rows with plain-space headers reads broken."""
    wrong = [
        (line, text)
        for line, text in _french_values(module)
        if _PLAIN_BEFORE.search(text) or _PLAIN_INSIDE.search(text)
    ]
    assert not wrong, f"{module}: {wrong}"


@pytest.mark.parametrize("module", ["i18n_hitl.py", "i18n_effects.py", "i18n_drafts.py"])
def test_the_scan_reads_each_table_module(module: str) -> None:
    """Alive, module by module: a scan that read nothing would pass for none."""
    assert _french_values(module)


def test_the_scan_reads_every_string_of_every_french_entry() -> None:
    """A scan reading one level, one table or one entry passed module by module
    (61 strings of 163 in the HITL tables, 1 of 107, 4 of 438): the exact set
    of a known source is what it must read, a model-facing table excepted."""
    source = (
        '_TABLE = {"fr": {"a": "un", "b": {"c": "deux"}}, "en": {"a": "one"}}\n'
        '_OTHER = {"en": "four", "fr": "trois"}\n'
        '_REFORMULATION_TEMPLATES = {"fr": "modèle"}\n'
        "class Messages:\n"
        '    LABELS = {"fr": ("cinq", "six")}\n'
    )

    found = sorted(text for _, text in _french_values_of(source))

    assert found == sorted(["a", "un", "b", "c", "deux", "trois", "cinq", "six"])
