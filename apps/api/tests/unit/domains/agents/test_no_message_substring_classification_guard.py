"""Guard: an error is classified by a typed code, never by the words of its message.

``if "forbidden" in str(e)`` couples a branch to a sentence. A vendor rewording
— or one of OUR OWN messages being rephrased — silently changes what the code
decides. Measured on this repository:

* ``browser_tools`` tests ``"Max concurrent" in str(e)`` while the producer
  writes « Maximum concurrent »: the branch can never be true, and pool
  saturation is reported as a CONFIGURATION error instead of a rate limit.
* ``openai_tts_client`` tests ``"rate" in error_str`` — and « generate »
  contains « rate », so any synthesis failure closes the voice websocket with a
  rate-limit code and tells the person to wait.
* The replanner called an anti-bot 403 « transient » because its permanence
  markers never matched the message our own tool had built.

Two structural classifiers already exist in-tree and say the doctrine out loud
(``infrastructure/llm/embedding_errors.py``, ``domains/agents/api/error_messages.py``).
This guard is a shrink-only ratchet over what is left: a new site fails the
build, and the baseline may only go down.

The scan covers the WHOLE of ``src`` and follows the alias an exception message
is usually read through — ``error_str = str(e)`` then ``"rate" in error_str``.
Both are why this file was widened: its first version scanned two directories
and read ``str(e)`` inline only, so of the three defects its own docstring
names it could see exactly ONE (ADR-303 review). A guard that cannot see its
own examples measures nothing.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

API_DIR = Path(__file__).parents[4]
SRC_DIR = API_DIR / "src"
BASELINE_PATH = Path(__file__).parent / "message_classification_baseline.json"

#: Text transforms that keep a message a message.
_TEXT_METHODS = frozenset({"lower", "upper", "strip", "casefold"})


def _exception_names(tree: ast.AST) -> set[str]:
    """Names bound by an ``except … as name`` anywhere in the module."""
    return {
        handler.name
        for handler in ast.walk(tree)
        if isinstance(handler, ast.ExceptHandler) and handler.name
    }


def _is_message_call(node: ast.AST, exc_names: set[str]) -> bool:
    """``str(e)`` or ``str(e).lower()`` — the TEXT of a caught exception."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "str" and node.args:
        arg = node.args[0]
        return isinstance(arg, ast.Name) and arg.id in exc_names
    if isinstance(func, ast.Attribute) and func.attr in _TEXT_METHODS:
        return _is_message_call(func.value, exc_names)
    return False


def _message_aliases(tree: ast.AST, exc_names: set[str]) -> set[str]:
    """Names this module assigns from an exception's text.

    Module-scoped on purpose, like ``_exception_names``: a local named
    ``error_str`` in one function and something else in another makes the scan
    slightly generous, which is the safe direction for a ratchet — a borderline
    site is DECLARED rather than hidden.

    Args:
        tree: The module AST.
        exc_names: Names bound by an ``except … as``.

    Returns:
        Every local name holding an exception message.
    """
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_message_call(node.value, exc_names):
            aliases |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and _is_message_call(node.value, exc_names)
            and isinstance(node.target, ast.Name)
        ):
            aliases.add(node.target.id)
    return aliases


def _is_message_text(node: ast.AST, exc_names: set[str], aliases: set[str]) -> bool:
    """Whether this operand is an exception message, directly or through an alias."""
    if isinstance(node, ast.Name):
        return node.id in aliases
    if isinstance(node, ast.Attribute) and node.attr in _TEXT_METHODS:
        return _is_message_text(node.value, exc_names, aliases)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _TEXT_METHODS:
            return _is_message_text(func.value, exc_names, aliases)
        return _is_message_call(node, exc_names)
    return False


def _violations(tree: ast.AST) -> list[int]:
    """Line numbers where a substring is searched inside an exception message.

    One entry per COMPARISON, not per line: ``"a" in msg or "b" in msg`` is two
    decisions on one line and counts as two, which is what the baseline holds.
    """
    names = _exception_names(tree)
    aliases = _message_aliases(tree, names)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and any(isinstance(op, ast.In | ast.NotIn) for op in node.ops)
        and any(_is_message_text(comparator, names, aliases) for comparator in node.comparators)
    )


def measure() -> dict[str, int]:
    """Sites per file, over the whole of ``src``."""
    counts: dict[str, int] = {}
    for path in sorted(SRC_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        found = _violations(ast.parse(path.read_text(encoding="utf-8")))
        if found:
            counts[path.relative_to(API_DIR).as_posix()] = len(found)
    return counts


class TestShrinkOnlyRatchet:
    """The debt is visible and decreasing — never dormant."""

    def test_message_substring_classification_only_shrinks(self) -> None:
        baseline: dict[str, int] = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        measured = measure()

        grown = {
            path: (baseline.get(path, 0), count)
            for path, count in measured.items()
            if count > baseline.get(path, 0)
        }
        assert not grown, (
            "Classify by a typed code (ToolErrorCode, an HTTP status, a typed "
            "exception), never by the message text. New sites:\n"
            + "\n".join(f"  {path}: {before} -> {now}" for path, (before, now) in grown.items())
        )

        slack = {
            path: (count, measured.get(path, 0))
            for path, count in baseline.items()
            if measured.get(path, 0) < count
        }
        assert (
            not slack
        ), "The baseline is shrink-only — lower it to what is measured:\n" + json.dumps(
            slack, indent=2
        )


class TestTheScanItself:
    """A ratchet nobody checks rots — pin the scanner on synthetic input."""

    def test_the_scan_detects_synthetic_violations(self) -> None:
        snippet = (
            "try:\n"
            "    f()\n"
            "except ValueError as e:\n"
            '    code = "X" if "not found" in str(e) else "Y"\n'
            '    if "Max" in str(e).lower():\n'
            "        pass\n"
        )
        assert _violations(ast.parse(snippet)) == [4, 5]

    def test_the_scan_follows_the_alias_a_message_is_read_through(self) -> None:
        """The shape every real site uses — and the one the first version missed."""
        snippet = (
            "try:\n"
            "    f()\n"
            "except ValueError as exc:\n"
            "    error_str = str(exc).lower()\n"
            '    if "rate" in error_str or "limit" in error_str:\n'
            "        pass\n"
        )
        # Two comparisons on one line — the count is per DECISION.
        assert _violations(ast.parse(snippet)) == [5, 5]

    def test_the_scan_ignores_a_typed_classification(self) -> None:
        snippet = (
            "try:\n"
            "    f()\n"
            "except ValueError as e:\n"
            "    if getattr(e, 'status_code', None) in (401, 403):\n"
            "        pass\n"
            '    if "x" in payload:\n'
            "        pass\n"
        )
        assert _violations(ast.parse(snippet)) == []

    def test_a_string_that_is_not_a_message_is_ignored(self) -> None:
        """A local named like a message but read from elsewhere is not scanned."""
        snippet = 'error_str = request.headers.get("x")\nif "rate" in error_str:\n    pass\n'
        assert _violations(ast.parse(snippet)) == []
