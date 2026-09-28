"""A prepared HITL text streams with its lines and its no-break spaces (ADR-323).

Its one-line counterpart, ``one_line``, lives in ``core.text_clip`` and is
tested there.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.domains.agents.services.hitl.interactions.text_tokens import text_tokens

pytestmark = pytest.mark.unit

_NBSP = chr(0xA0)


def test_words_are_split_on_ordinary_spaces_only() -> None:
    text = f"**Éléments concernés{_NBSP}:** deux"

    assert list(text_tokens(text)) == [
        "**Éléments ",
        f"concernés{_NBSP}:** ",
        "deux ",
        "\n",
    ]


def test_every_line_ends_on_a_newline_token() -> None:
    assert list(text_tokens("a b\n\nc")) == ["a ", "b ", "\n", "\n", "c ", "\n"]


def test_the_stream_rebuilds_the_text_s_characters() -> None:
    """Joined, the tokens carry every character of the text but its spacing runs."""
    text = f"- 🔔 Rappel{_NBSP}: Médecin\n- 📧 Email{_NBSP}: Facture"

    joined = "".join(text_tokens(text))

    assert joined.replace(" \n", "\n").rstrip() == text


def test_a_blank_text_streams_nothing() -> None:
    """An empty question must not become a newline the chat archives as a bubble."""
    assert list(text_tokens("")) == []
    assert list(text_tokens(" \n ")) == []


# Every place that streams a PREPARED text word by word goes through
# text_tokens, and every one-line preview through one_line: a bare
# ``.split()`` breaks the no-break space a French colon takes and re-emits an
# ordinary one. Streamed-output tests pin some call sites (the draft batch,
# the draft critique's fallback); this structural check keeps every one — and
# the stream service's two fallbacks — from reverting, whatever shape the loop
# takes: fed through a variable, through ``enumerate``, or joined back (three
# of the loops this replaced took those shapes, and a check that read only a
# direct ``for x in s.split()`` saw none of them).
_STREAM_MODULES = (
    *sorted(
        (
            Path(__file__).resolve().parents[6] / "src/domains/agents/services/hitl/interactions"
        ).glob("*.py")
    ),
    Path(__file__).resolve().parents[6] / "src/domains/agents/services/streaming/service.py",
    # The drafts' own item preview, the one a FOR_EACH or a draft batch prefers,
    # and the card and result renderers that name the same drafts.
    Path(__file__).resolve().parents[6] / "src/core/i18n_drafts.py",
    Path(__file__).resolve().parents[6] / "src/domains/agents/drafts/preview_renderer.py",
    # The ONE reading of a draft's name, which every surface above draws.
    Path(__file__).resolve().parents[6] / "src/domains/agents/drafts/display.py",
    Path(__file__).resolve().parents[6] / "src/domains/agents/drafts/result_renderer.py",
)


#: ``\s``, as a regular expression spells whitespace.
_BACKSLASH_S = chr(92) + "s"


#: The two methods that split a string on all whitespace when no separator
#: is named.
_SPLITS = frozenset({"split", "rsplit"})


def _split_separator(node: ast.Call) -> ast.expr | None:
    """The separator a ``split`` call names — ``str.split(text, sep)`` names it
    second — or None when it names none."""
    func = node.func
    assert isinstance(func, ast.Attribute)
    on_str_type = isinstance(func.value, ast.Name) and func.value.id == "str"
    named = [keyword.value for keyword in node.keywords if keyword.arg == "sep"]
    return next(iter([*(node.args[1:2] if on_str_type else node.args[:1]), *named]), None)


def _is_regex_fold(node: ast.Call) -> bool:
    r"""``re.sub(r"\s+", " ", …)``, ``re.split(r"\s+", …)``, ``re.compile(r"\s+")``."""
    func = node.func
    assert isinstance(func, ast.Attribute)
    if not (isinstance(func.value, ast.Name) and func.value.id in {"re", "regex"}):
        return False
    keywords = {keyword.arg: keyword.value for keyword in node.keywords}
    pattern = node.args[0] if node.args else keywords.get("pattern")
    if not (isinstance(pattern, ast.Constant) and isinstance(pattern.value, str)):
        return False
    if func.attr == "compile":
        return pattern.value == _BACKSLASH_S + "+"
    if func.attr == "split":
        return _BACKSLASH_S in pattern.value
    if func.attr in {"sub", "subn"}:
        repl = node.args[1] if len(node.args) > 1 else keywords.get("repl")
        return (
            _BACKSLASH_S in pattern.value and isinstance(repl, ast.Constant) and repl.value == " "
        )
    return False


def _word_counts(tree: ast.AST) -> set[int]:
    """The nodes a ``len(...)`` counts: a word COUNT re-emits nothing."""
    return {
        id(node.args[0])
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
        and len(node.args) == 1
    }


def _splits_on_whitespace(node: ast.Call) -> bool:
    """A ``split`` or ``rsplit`` naming no separator, or naming ``None``."""
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in _SPLITS):
        return False
    separator = _split_separator(node)
    return separator is None or (isinstance(separator, ast.Constant) and separator.value is None)


def _whitespace_folds(path: Path) -> list[int]:
    r"""Every fold on ALL whitespace a module holds, in the spellings read here.

    ``split``/``rsplit`` naming no separator (``text.split()``,
    ``split(None)``, ``split(sep=None)``, ``split(maxsplit=1)``,
    ``str.split(text)``), and the regular expressions that do the same through
    a module named ``re`` or ``regex``: ``sub``/``subn`` replacing a pattern
    that reads ``\s`` with one space, ``split`` on a pattern that reads ``\s``
    (``[\s,]+`` included), and a compiled ``re.compile(r"\s+")``, whose
    ``.sub`` the check cannot follow. A word COUNT (``len(text.split())``)
    re-emits nothing, and is not one. NOT read, so left to review: an aliased
    module (``import re as x``, ``from re import sub``) and a compiled pattern
    spelled otherwise (``[\s]+``, ``\s`` then ``.sub``).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    counted = _word_counts(tree)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and ((_splits_on_whitespace(node) and id(node) not in counted) or _is_regex_fold(node))
    )


@pytest.mark.parametrize("path", _STREAM_MODULES, ids=lambda path: path.name)
def test_no_stream_loops_over_a_whitespace_split(path: Path) -> None:
    assert _whitespace_folds(path) == [], (
        f"{path.name}: stream a prepared text through text_tokens and draw a"
        " one-line preview through one_line, never a fold on all whitespace"
    )


def test_the_structural_check_sees_the_forbidden_loop(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(
        "async def stream(text):\n"
        "    for token in text.split():\n"
        "        yield token\n"
        "    words = text.split()\n"
        "    for i, word in enumerate(text.split()):\n"
        "        yield word\n"
        "    yield ' '.join(text.split())\n"
        "    yield text.split(' ')\n"
        "    return len(text.split())\n",
        encoding="utf-8",
    )

    # A direct loop, a variable, enumerate, a join back — never a split on ' ',
    # nor a word count.
    assert _whitespace_folds(probe) == [2, 4, 5, 7]


def test_the_structural_check_sees_every_spelling_of_the_fold(tmp_path: Path) -> None:
    """The streaming fold this lot replaced was a ``re.sub``: a check that read
    a bare ``.split()`` alone could not have caught its revert."""
    whitespace = chr(92) + "s+"
    either = "[" + chr(92) + "s,]+"
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import re\n"
        "import regex\n"
        "def fold(text):\n"
        "    a = text.split(None)\n"
        "    b = text.split(sep=None)\n"
        "    c = text.split(maxsplit=5)\n"
        "    d = str.split(text)\n"
        f"    e = re.split(r'{whitespace}', text)\n"
        f"    f = re.sub(r'{whitespace}', ' ', text)\n"
        f"    g = re.sub(pattern=r'{whitespace}', repl=' ', string=text)\n"
        f"    H = re.compile(r'{whitespace}')\n"
        "    i = str.split(text, ',')\n"
        f"    j = re.sub(r'^{whitespace}', '', text)\n"
        "    k = re.compile(r'^[-]{3,}$')\n"
        f"    m = regex.sub(r'{whitespace}', ' ', text)\n"
        f"    n = re.subn(r'{whitespace}', ' ', text)\n"
        "    o = text.split(sep=',')\n"
        f"    p = re.split(r'{either}', text)\n"
        "    q = text.rsplit()\n"
        "    r = text.rsplit(',', 1)\n",
        encoding="utf-8",
    )

    # Every fold on all whitespace, through either module and either method —
    # never a split on a separator (positional or named), a regex that removes
    # rather than folds, nor one that matches no whitespace.
    assert _whitespace_folds(probe) == [4, 5, 6, 7, 8, 9, 10, 11, 15, 16, 18, 19]
