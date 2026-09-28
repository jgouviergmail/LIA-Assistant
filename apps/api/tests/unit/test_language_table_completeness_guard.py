"""AST guard: a table keyed by language holds exactly the six canonical codes (ADR-323).

A language table that misses a language fails nothing: the reader falls back
(to English, to the instance default, to a key it does not have) and a German
or Chinese reader simply gets another language. Measured 2026-09-25 on the
last release before the rule (4f19469b): 835 dict literals keyed by language
codes, 790 canonical. Of the 45 others, 28 were keyed on ``zh``, the
FRONTEND's code: the Telegram formatter (9) and HITL keyboard (6) tables, read
with the canonical ``zh-CN``, served every Chinese account the fallback; the
13 others — telephony (7), automation (2), one table each in
``core/constants``, the briefing, the interests helpers and the browser pool —
held only because a private mapper (``split("-")[0]``, telephony's ``_iso``,
the interests' ``normalize_language_code``) cut the code first, each one a
second authority on the spelling, all removed with the rule. 15 were « SKOS »
label tables carrying ``en``/``fr`` only (dead data, deleted); 2 had no Chinese
at all (the Brave and Perplexity interest sources). The one allowance that came
with the rule, a code map, went when the map started deriving from the
``Language`` literal instead of restating it.

The rule, over every ``src/**/*.py``: a dict literal or a ``dict(...)`` call whose
keys are language codes (at least two, and at least half of its keys) has exactly the
backend's canonical codes — ``fr``, ``en``, ``es``, ``de``, ``it``, ``zh-CN``
(never ``zh``, never a region variant). A table that legitimately differs is
declared in ``ALLOWED`` by file and assigned name, with its reason;
``test_every_allowance_is_still_used`` keeps the list shrink-only.
"""

from __future__ import annotations

import ast
import functools

import pytest

from src.core.i18n_types import LANGUAGE_NAMES
from tests._repo_paths import find_apps_api_root

pytestmark = pytest.mark.unit

SRC = find_apps_api_root() / "src"
CANONICAL: frozenset[str] = frozenset(LANGUAGE_NAMES)

#: Spellings that mark a key as a LANGUAGE (canonical or not).
LANGUAGE_KEYS: frozenset[str] = CANONICAL | {
    "zh",
    "zh_CN",
    "zh-TW",
    "zh-cn",
    "fr-FR",
    "en-US",
    "en-GB",
    "es-ES",
    "de-DE",
    "it-IT",
}

#: (file relative to src, assigned name) -> why the table is not a six-language one.
ALLOWED: dict[tuple[str, str], str] = {}


#: A mapping is a language TABLE when at least two of its keys, and at least this
#: share of them, are language codes — a stray ``"default"`` beside five codes
#: must not hide a missing language.
TABLE_SHARE = 0.5


def _assigned_name(node: ast.expr, parents: dict[int, ast.AST]) -> str | None:
    """The name a mapping is assigned to, when it is the whole value."""
    parent = parents.get(id(node))
    if isinstance(parent, ast.Assign) and len(parent.targets) == 1:
        target = parent.targets[0]
        return target.id if isinstance(target, ast.Name) else None
    if isinstance(parent, ast.AnnAssign) and isinstance(parent.target, ast.Name):
        return parent.target.id
    return None


def _mapping_keys(node: ast.AST) -> tuple[list[str], int] | None:
    """(string keys, number of keys) of a dict literal or a ``dict(fr=…)`` call."""
    if isinstance(node, ast.Dict):
        keys = [
            k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)
        ]
        return keys, len(node.keys)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
        and not node.args
        and node.keywords
    ):
        keys = [kw.arg for kw in node.keywords if kw.arg is not None]
        return keys, len(node.keywords)
    return None


def _tables_in(tree: ast.AST) -> list[tuple[int, str | None, frozenset[str]]]:
    """(line, assigned name, keys) of every language table of a module."""
    parents = {id(c): p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    tables = []
    for node in ast.walk(tree):
        found = _mapping_keys(node)
        if found is None:
            continue
        keys, total = found
        codes = [k for k in keys if k in LANGUAGE_KEYS]
        if len(codes) < 2 or len(codes) < TABLE_SHARE * total:
            continue
        assert isinstance(node, ast.expr)
        tables.append((node.lineno, _assigned_name(node, parents), frozenset(keys)))
    return tables


@functools.cache
def _language_tables() -> tuple[tuple[str, int, str | None, frozenset[str]], ...]:
    """Every language table of src/ — scanned once, when a test first asks."""
    return tuple(
        (path.relative_to(SRC).as_posix(), line, name, keys)
        for path in sorted(SRC.rglob("*.py"))
        for line, name, keys in _tables_in(ast.parse(path.read_text(encoding="utf-8")))
    )


def test_the_scan_sees_the_tables() -> None:
    """Alive: the product's language tables number in the hundreds."""
    assert len(_language_tables()) > 500


def test_every_language_table_holds_the_six_canonical_codes() -> None:
    offenders = [
        f"{rel}:{line} ({name or 'unnamed'}): {sorted(keys)}"
        for rel, line, name, keys in _language_tables()
        if keys != CANONICAL and (rel, name) not in ALLOWED
    ]
    assert offenders == [], (
        "A language table must key the six canonical codes (fr, en, es, de, it, "
        "zh-CN) — a missing language silently reads another one: " + "; ".join(offenders)
    )


def test_every_allowance_is_still_used() -> None:
    seen = {(rel, name) for rel, _line, name, keys in _language_tables() if keys != CANONICAL}
    stale = sorted(set(ALLOWED) - seen)
    assert stale == [], f"allowances no longer needed, remove them: {stale}"


@pytest.mark.parametrize(
    "source",
    [
        # five languages: Chinese reads another one
        'T = {"fr": "a", "en": "b", "es": "c", "de": "d", "it": "e"}',
        # the frontend's code: the backend never reads zh
        'T = {"fr": "a", "en": "b", "es": "c", "de": "d", "it": "e", "zh": "f"}',
        # a stray key beside the codes does not make it a non-table
        'T = {"fr": "a", "en": "b", "de": "c", "default": "d"}',
        # a dict() call cannot even spell zh-CN
        'T = dict(fr="a", en="b", es="c", de="d", it="e")',
    ],
)
def test_the_rule_sees_an_incomplete_table(source: str) -> None:
    tables = _tables_in(ast.parse(source))
    assert tables and all(keys != CANONICAL for _line, _name, keys in tables), source


@pytest.mark.parametrize(
    "source",
    [
        'T = {"fr": "a", "en": "b", "es": "c", "de": "d", "it": "e", "zh-CN": "f"}',
        # a mapping with one code among other keys is no language table
        'T = {"en": "b", "url": "u", "title": "t"}',
        "T = dict(timeout=3, retries=2)",
    ],
)
def test_a_complete_table_and_a_non_table_pass(source: str) -> None:
    assert all(keys == CANONICAL for _line, _name, keys in _tables_in(ast.parse(source))), source
