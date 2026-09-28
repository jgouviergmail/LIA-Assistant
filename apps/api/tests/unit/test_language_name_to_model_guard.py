"""Guard: a language told to a model is its NAME, never its code (ADR-323).

A prompt reads ``Respond ONLY in {user_language}``. Given ``fr`` instead of
``French``, the instruction is one a model may or may not decode — sixteen
prompts received the code until the ADR-323 review, found by assembling the
real prompts (the journal's extraction and the briefing's greeting and
synthesis among them). Run on 4f19469b, this guard flags 24 sites: the
sixteen prompts at 17 of them (the semantic validator's line names the
language twice), two that held no code (a language NAME kept in a variable
called ``language``, and a literal ``{user_language}`` placeholder forwarded
to another template) and the five Wikipedia edition codes it declares.
``core.i18n.get_language_name`` is the one reader of a code into a name (it
normalises first, so ``zh`` reads « Simplified Chinese »).

Rule, over every ``src/**/*.py``, for a value that is not a
``get_language_name(...)`` call or a name holding one (``language_name``,
``source_name``…):

* a keyword of ``.format(...)`` or of a template call (``.partial``,
  ``.format_messages``, ``.format_prompt``, ``.format_map``, ``.invoke``),
  or a key of a mapping literal splatted into one, named after a language
  (``language``, ``user_language``, ``language_code``, ``language_hint``,
  ``language_tag``, ``languages``, ``userLanguage``…);
* a ``.replace("{…language…}", value)`` substitution;
* an f-string that INTERPOLATES a language-named value — a name, an
  attribute or a constant-key subscript (``{state['user_language']}``) —
  right after a language instruction (``LANGUAGE: {code}``, ``Respond in
  {code}``, ``Translate to {code}``) — four of the sixteen prompts were
  f-strings in a ``.py``, where one-line scaffolds live;
* a language-named key of a mapping handed to a template or a model
  (``prompt_vars=``, ``.invoke``/``.ainvoke``, ``.format_map``, ``.partial``,
  ``.format_messages``, a ``%`` template).

What it does NOT read: a positional ``.format(code)`` (the placeholder has no
name), a mapping built elsewhere and splatted (``.format(**variables)`` — its
keys are not in the call), a template built at run time, a code interpolated
WITHOUT an instruction
before it (a URL's edition, a cache key, a ``repr``) — a code there is data —
and an f-string inside a raised exception or a log call, read by no model.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from functools import cache
from pathlib import Path

import pytest

from tests._language_names import is_language_name, snake

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

_LANGUAGE_PLACEHOLDER = re.compile(
    r"\{\w*(lang|language|languages|locale)(_code|_codes|_hint)?\}", re.IGNORECASE
)
#: The words a prompt puts right before the language it asks for.
_INSTRUCTION = re.compile(r"(?i)(\blanguage\s*:|\b(in|into|to)\s*:?)\s*$")
#: Calls that hand a mapping to a template or a model.
_TEMPLATE_CALLS = frozenset(
    {"invoke", "ainvoke", "format_map", "partial", "format_messages", "format_prompt"}
)
#: Keywords whose mapping is a template's variables.
_TEMPLATE_KEYWORDS = frozenset({"prompt_vars", "variables", "template_vars", "inputs"})

#: (path under src/, keyword or placeholder, value source) -> (sites, reason).
ALLOWED: dict[tuple[str, str, str], tuple[int, str]] = {
    ("domains/agents/tools/wikipedia_tools.py", "language", "language"): (
        5,
        "the Wikipedia EDITION a tool message names (``fr`` for fr.wikipedia.org) — "
        "a host, not a language the model is asked to write in",
    ),
}


def _is_language_named(identifier: str) -> bool:
    return is_language_name(identifier)


def _identifier(value: ast.expr) -> str:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    if (  # state["user_language"] reads as its key
        isinstance(value, ast.Subscript)
        and isinstance(value.slice, ast.Constant)
        and isinstance(value.slice.value, str)
    ):
        return value.slice.value
    return ""


def _is_name(value: ast.expr) -> bool:
    """A ``get_language_name(...)`` call, or a variable named after the name it holds."""
    if isinstance(value, ast.Call):
        func = value.func
        called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        return called == "get_language_name"
    return _identifier(value).lower().endswith("name")


def _mapping_sites(mapping: ast.Dict, line: int) -> list[tuple[int, str, str]]:
    """Language-named keys of a literal mapping whose value is a code."""
    return [
        (line, key.value, ast.unparse(value))
        for key, value in zip(mapping.keys, mapping.values, strict=True)
        if isinstance(key, ast.Constant)
        and isinstance(key.value, str)
        and _is_language_named(key.value)
        and not _is_name(value)
    ]


def _call_sites(node: ast.Call) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    attr = node.func.attr if isinstance(node.func, ast.Attribute) else ""
    # .partial / .format_messages take their variables as KEYWORDS, like .format
    if attr == "format" or attr in _TEMPLATE_CALLS:
        found.extend(_keyword_sites(node))
    elif attr == "replace" and len(node.args) >= 2:
        found.extend(_replace_sites(node))
    if attr in _TEMPLATE_CALLS:
        for argument in node.args:
            if isinstance(argument, ast.Dict):
                found.extend(_mapping_sites(argument, node.lineno))
    for keyword in node.keywords:
        if keyword.arg in _TEMPLATE_KEYWORDS and isinstance(keyword.value, ast.Dict):
            found.extend(_mapping_sites(keyword.value, node.lineno))
    return found


def _keyword_sites(node: ast.Call) -> list[tuple[int, str, str]]:
    """A template's variables: an unpacked mapping, or a language-named keyword
    handed something that is not a name."""
    found: list[tuple[int, str, str]] = []
    for keyword in node.keywords:
        if keyword.arg is None and isinstance(keyword.value, ast.Dict):
            found.extend(_mapping_sites(keyword.value, node.lineno))
        elif (
            keyword.arg is not None
            and _is_language_named(keyword.arg)
            and not _is_name(keyword.value)
        ):
            found.append((node.lineno, keyword.arg, ast.unparse(keyword.value)))
    return found


def _replace_sites(node: ast.Call) -> list[tuple[int, str, str]]:
    """``text.replace("{language}", code)``: a language placeholder filled by
    something that is not a name."""
    placeholder, value = node.args[0], node.args[1]
    if (
        isinstance(placeholder, ast.Constant)
        and isinstance(placeholder.value, str)
        and _LANGUAGE_PLACEHOLDER.search(snake(placeholder.value))
        and not _is_name(value)
    ):
        return [(node.lineno, placeholder.value, ast.unparse(value))]
    return []


def _fstring_sites(node: ast.JoinedStr) -> list[tuple[int, str, str]]:
    """A language-named value interpolated right after a language instruction."""
    found: list[tuple[int, str, str]] = []
    for before, part in zip(node.values, node.values[1:], strict=False):
        if not (
            isinstance(part, ast.FormattedValue)
            and isinstance(before, ast.Constant)
            and isinstance(before.value, str)
        ):
            continue
        name = _identifier(part.value)
        if (
            name
            and _is_language_named(name)
            and not _is_name(part.value)
            and _INSTRUCTION.search(before.value)
        ):
            found.append((node.lineno, "f-string", ast.unparse(part.value)))
    return found


_LOGGERS = frozenset({"logger", "log", "_logger", "_log", "LOGGER", "LOG"})


def _unread(tree: ast.AST) -> set[int]:
    """Every node of a raised exception or a log call: read by no model."""
    unread: set[int] = set()
    for node in ast.walk(tree):
        is_log = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and _identifier(node.func.value) in _LOGGERS
        )
        if is_log or isinstance(node, ast.Raise):
            unread.update(id(child) for child in ast.walk(node))
    return unread


def _sites(tree: ast.AST) -> list[tuple[int, str, str]]:
    """``(line, keyword or placeholder, value source)`` of every language told as a code."""
    found: list[tuple[int, str, str]] = []
    unread = _unread(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            found.extend(_call_sites(node))
        elif isinstance(node, ast.JoinedStr) and id(node) not in unread:
            found.extend(_fstring_sites(node))
        elif (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Mod)
            and isinstance(node.right, ast.Dict)
        ):
            found.extend(_mapping_sites(node.right, node.lineno))
    return found


@cache
def _src_sites() -> tuple[tuple[str, int, str, str], ...]:
    return tuple(
        (path.relative_to(SRC).as_posix(), line, keyword, value)
        for path in sorted(SRC.rglob("*.py"))
        for line, keyword, value in _sites(ast.parse(path.read_text(encoding="utf-8")))
    )


def test_every_language_told_to_a_model_is_a_name() -> None:
    counts = Counter((module, keyword, value) for module, _line, keyword, value in _src_sites())
    offenders = [
        f"  {module}:{line} {keyword}={value}"
        for module, line, keyword, value in _src_sites()
        if counts[(module, keyword, value)] != ALLOWED.get((module, keyword, value), (0, ""))[0]
    ]
    assert not offenders, (
        "A language told to a model as a CODE — pass get_language_name(code) "
        "(core.i18n), or declare the site with its reason:\n" + "\n".join(offenders)
    )


def test_every_allowance_still_matches_its_sites() -> None:
    counts = Counter((module, keyword, value) for module, _line, keyword, value in _src_sites())
    stale = sorted(key for key, (sites, _reason) in ALLOWED.items() if counts[key] < sites)
    assert not stale, f"allowances covering sites that no longer exist — shrink them: {stale}"


@pytest.mark.parametrize(
    "source",
    [
        'load_prompt("x").format(user_language=user_language)',
        "template.format(language=lang)",
        'template.format(target_language=settings.default_language, text="t")',
        'template.replace("{user_language}", user_language)',
        'template.replace("{language}", "fr")',
        'template.replace("{userLanguage}", code, 1)',
        "template.format(userLanguage=code)",
        "template.format(language_hint=code)",
        "template.format(language_code=code)",
        "template.format(**{'user_language': code})",
        'lines = [f"LANGUAGE: {context.language}"]',
        'human = f"Write the summary in: {language}.\\n"',
        'prompt = f"Respond ONLY in {user_language}"',
        "run(prompt_vars={'user_language': _user_lang})",
        "await chain.ainvoke({'language': lang, 'text': text})",
        "template.format_map({'language': lang})",
        "'Answer in %(language)s' % {'language': lang}",
        # Round 6: template calls' keywords, « to », a constant-key subscript.
        "prompt.partial(user_language=code)",
        "chat.format_messages(user_language=code)",
        'text = f"Translate the text to {target_language}:"',
        "text = f\"Respond in {state['user_language']}.\"",
    ],
)
def test_the_rule_sees_a_code_told_to_a_model(source: str) -> None:
    assert _sites(ast.parse(source)), source


@pytest.mark.parametrize(
    "source",
    [
        'load_prompt("x").format(user_language=get_language_name(user_language))',
        "template.format(user_language=language_name)",
        "template.format(language=get_language_name(normalize_language(x)))",
        "template.format(source_language=source_name, target_language=target_name)",
        'template.replace("{user_language}", get_language_name(lang))',
        "template.format(language_model=model)",
        'template.replace("{name}", name)',
        'lines = [f"LANGUAGE: {get_language_name(context.language)}"]',
        'url = f"https://{language}.wikipedia.org/wiki/{title}"',
        'key = f"{prefix}:{user_id}:{language}"',
        "run(prompt_vars={'user_language': get_language_name(code)})",
        "prompt.partial(user_language=language_name)",
        'text = f"Sent to {recipient}"',
        "text = f\"Respond in {state['language_name']}.\"",
    ],
)
def test_a_name_and_an_unrelated_field_pass(source: str) -> None:
    assert _sites(ast.parse(source)) == [], source
