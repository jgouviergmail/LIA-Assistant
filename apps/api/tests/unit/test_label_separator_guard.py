"""Guard: a label and its value are joined by the READER's punctuation, never a literal.

A ``": "`` written in the code publishes English punctuation in six languages, a
``" : "`` French punctuation: a French colon takes a no-break space before it, a
Chinese one is full-width. Lot 13 of ADR-276 moved the drafts' separator into
their labels; the cards, the FOR_EACH and destructive dialogs, the minutes'
header and the interest notifications kept writing their own, both ways
(measured when this guard was written, on v1.47.4 with the allowances then in
force: 49 sites in 20 modules). Every DECLARED surface joins a label and its value through
``label_separator(language)`` (``core/i18n_drafts.py``).

What the rule reads, on the declared surfaces:

* an f-string where an interpolated value is followed by a colon and a space, a
  line break or markup — or a full-width colon — markup and a closing bracket
  between them included (``**{label}** :``, ``({stamp}):``), or where the colon
  ENDS the f-string (the value is appended after it);
* a label WRITTEN OUT before its value, by its punctuation (``Reason : {x}``,
  ``**Email:** {x}``, a full-width colon) — never a bare ``word: {x}``, which on
  these surfaces is CSS, the SSE wire or a key;
* a bare separator concatenated (``label + ": "``) or used to join
  (``": ".join``), a ``%`` or ``.format`` template joining a placeholder to a
  colon, and a separator substituted in (``re.sub`` or ``regex.sub``, a
  compiled pattern's ``.sub``, positionally or by ``repl=``, ``str.replace``).
  For a bare name, module or compiled pattern is read from the module's own
  statements: a name an ``import re`` or ``import regex`` binds, under any
  alias, is the module (a function's local import counts module-wide, and the
  import wins over any other binding of the same name); a name otherwise
  BOUND to a value — an assignment at any depth of its targets
  (``regex, flags = …``), an annotated one holding a value, ``:=``, a
  ``for`` or ``async for``, ``with`` or comprehension target — is a pattern; any other name (a parameter, a
  ``from … import … as …``, a global nothing binds) is read by its spelling:
  ``re`` and ``regex`` are the module, everything else a pattern. An
  attribute (``self.regex``) is always a pattern.

A clock (``f"{h}:{m:02d}"``) or a URL (``f"{scheme}://"``) has no space after
its colon and is not a separator. A log line (a call on a logger, matched by the
receiver's NAME) or a raised exception is not read by a person.

What it does NOT read: a colon inside a nested expression
(``f"{label}{': ' if c else ''}"``), a string built at run time, ``subn``, a
bare ``sub(…)`` imported by ``from re import sub``, a module reached under
another name than ``re`` or ``regex`` without an ``import re`` of its own
(a parameter ``rx``, ``from compat import regex_module as rx``, ``rx = re``:
each read as a pattern), a pattern a parameter or a ``from … import`` spells
``re`` or ``regex`` (read as the module), and a surface nobody declared — the
model-facing prompts and tool messages are not surfaces.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from collections.abc import Iterable
from functools import cache
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

#: Modules and directories whose text a person reads.
SURFACES = (
    "core/i18n_drafts.py",
    "core/i18n_hitl.py",
    "domains/account_export/",
    "domains/agents/display/components/",
    "domains/agents/drafts/",
    "domains/agents/effects/confirmation.py",
    "domains/agents/services/hitl/interactions/",
    "domains/interests/services/content_sources/",
    "domains/interests/sources.py",
    "domains/meetings/processing.py",
    "domains/meetings/render.py",
    "domains/meetings/synthesis.py",
    "domains/notifications/",
    "domains/reminders/",
    "domains/workboard/",
    "infrastructure/channels/telegram/",
    "infrastructure/email/",
    "infrastructure/scheduler/scheduled_action_executor.py",
)

#: (module, enclosing function, what is joined) → why this colon is not a
#: label's. An allowance names its FUNCTION and covers exactly one site: keyed on
#: the module alone, a common loop name (``key``) would have covered any new
#: join anywhere in a person-read renderer.
ALLOWED: dict[tuple[str, str, str], str] = {
    (
        "domains/agents/drafts/preview_renderer.py",
        "_render_tool_call",
        "_argument_value(str(key))",
    ): (
        "a tool's raw argument names, rendered as data (``key: value``) — never a translated label"
    ),
    ("domains/agents/effects/confirmation.py", "readable_tool_name", "server"): (
        "an MCP server's identifier joined to its tool's name — a technical name the card "
        "shows as it is, like a path"
    ),
    ("domains/meetings/synthesis.py", "render_transcript", "turn.speaker"): (
        "the transcript handed to the model (``speaker: words``) — a prompt, never read"
    ),
    ("domains/meetings/synthesis.py", "_condense", "len(parts)"): (
        "the model's input header — a prompt"
    ),
    (
        "domains/meetings/synthesis.py",
        "synthesize_minutes",
        "'CONDENSED NOTES (from the transcript)' if condensed else 'TRANSCRIPT'",
    ): "the model's input header — a prompt",
    (
        "domains/interests/services/content_sources/content_generator.py",
        "_apply_angle_to_topic",
        "topic",
    ): "the search the sources run (topic, then its diversity angle) — never shown",
    ("domains/agents/display/components/html_flatten.py", "html_to_text", "' : '"): (
        "html_to_text flattens a definition list exactly like the browser's projection "
        "(apps/web/src/lib/html-plain-text.ts) under one shared corpus: both sides change "
        "together or not at all — named in ADR-323 (moved out of components/base.py by "
        "ADR-326)"
    ),
}

_NBSP = chr(0xA0)
_NNBSP = chr(0x202F)
_FULL_WIDTH_COLON = chr(0xFF1A)
_SPACE = f"[ {_NBSP}{_NNBSP}]?"
_CLOSER = r"(\*\*|__|\*|_|`|</(?:strong|b|span|em|a|code|i|th|td)>|\)|\]|\"|”|»|’)?"
#: After a value, mid-string: a colon then a space, markup or a line break.
_SEPARATOR = re.compile(_CLOSER + f"({_SPACE}:(\\s|\\*\\*|</|<br)|{_FULL_WIDTH_COLON})")
#: After the LAST value: a colon ending the f-string, the value appended after it.
_TRAILING = re.compile(_CLOSER + f"{_SPACE}[:{_FULL_WIDTH_COLON}]$")
#: A WRITTEN-OUT label before a value, by its punctuation: a space before the
#: colon (``Reason : {x}``), a colon closed by markup (``**Email:** {x}``,
#: ``<strong>Name :</strong> {x}``), or a full-width colon — right before the
#: interpolation. A bare ``word: {x}`` is NOT read: on these surfaces it is a
#: CSS declaration (``background: {color}``), the SSE wire (``data: {json}``)
#: or a prompt line, and a key (``user:{id}``) has no space at all.
_MARKUP = r"(?:\*\*|__|</(?:strong|b|span|em|th|td|dt|label)>)"
_LABEL_BEFORE = re.compile(
    r"[\w)\]\"”»’]"
    + f"(?:[ {_NBSP}{_NNBSP}]:{_MARKUP}?[ {_NBSP}]"
    + f"|:{_MARKUP}[ {_NBSP}]"
    + f"|{_FULL_WIDTH_COLON}{_MARKUP}?)$"
)
#: A separator on its own (``": "``, ``" : "``, ``"："``, ``":\n"``). An ASCII
#: colon followed by nothing is not one: a clock (``":".join([h, m])``) or a
#: key (``prefix + ":" + user_id``).
_BARE = re.compile(
    f"^(?:{_SPACE}{_FULL_WIDTH_COLON}[ {_NBSP}]?"
    f"|[ {_NBSP}{_NNBSP}]:[ {_NBSP}]?"
    f"|:[ {_NBSP}\\n])$"
)
#: A template placeholder followed by a colon (``{}: ``, ``%s: ``, ``{label}：``).
_TEMPLATE = re.compile(r"(\}|%s|%\(\w+\)s)(\*\*|</\w+>)?" + f"{_SPACE}(:\\s|{_FULL_WIDTH_COLON})")
_LOGGERS = frozenset({"logger", "log", "_logger", "_log", "LOGGER", "LOG"})
_LEVELS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical"})


def _receiver_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_log_call(node: ast.AST) -> bool:
    """A call on a logger — by the receiver's name (``dialog.info`` is not one)."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _LEVELS
        and _receiver_name(node.func.value) in _LOGGERS
    )


def _unread(tree: ast.AST) -> set[int]:
    """The ids of every node inside a log call or a raised exception."""
    unread: set[int] = set()
    for node in ast.walk(tree):
        if _is_log_call(node) or isinstance(node, ast.Raise):
            unread.update(id(child) for child in ast.walk(node))
    return unread


def _text(node: ast.expr) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _separators(node: ast.JoinedStr) -> list[str]:
    """The interpolated expressions a literal label colon follows in one f-string."""
    last = len(node.values) - 1
    found: list[str] = []
    for index, (left, right) in enumerate(zip(node.values, node.values[1:], strict=False)):
        # a written-out label joined to the value that follows it
        before = _text(left) if isinstance(right, ast.FormattedValue) else None
        if before is not None and isinstance(right, ast.FormattedValue):
            if _LABEL_BEFORE.search(before):
                found.append(ast.unparse(right.value))
        text = _text(right) if isinstance(left, ast.FormattedValue) else None
        if text is None or not isinstance(left, ast.FormattedValue):
            continue
        if _SEPARATOR.match(text) or (index + 1 == last and _TRAILING.match(text)):
            found.append(ast.unparse(left.value))
    return found


def _bare_texts(nodes: Iterable[ast.expr]) -> list[str]:
    """The bare separators among some literals, as the finding names them."""
    return [repr(text) for node in nodes if (text := _text(node)) is not None and _BARE.match(text)]


def _operator_joins(node: ast.BinOp) -> list[str]:
    """``label + ": " + value`` and ``"%s: %s" % (label, value)``."""
    if isinstance(node.op, ast.Add):
        return _bare_texts((node.left, node.right))
    template = _text(node.left) if isinstance(node.op, ast.Mod) else None
    return [repr(template)] if template is not None and _TEMPLATE.search(template) else []


def _method_joins(
    node: ast.Call, method: str, owner: str | None, modules: frozenset[str]
) -> list[str]:
    """``"{}: {}".format(…)``, ``": ".join(…)``, ``"".join([label, ": ", value])``,
    ``re.sub(…, ": ", …)`` (``regex.sub`` too, ``repl=`` too), ``PATTERN.sub(": ", …)``,
    ``text.replace(…, ": ")`` — ``modules`` names what the module's regular
    expression modules are bound to."""
    if method == "format":
        return [repr(owner)] if owner is not None and _TEMPLATE.search(owner) else []
    if method == "join":
        if owner is not None and _BARE.match(owner):
            return [repr(owner)]
        listed = node.args[0] if node.args else None
        return _bare_texts(listed.elts) if isinstance(listed, ast.List | ast.Tuple) else []
    if method == "sub":
        return _bare_texts(_replacements(node, modules))
    if method == "replace":
        return _bare_texts(node.args[1:2])
    return []


#: The regular-expression modules whose ``sub`` names its replacement second.
_REGEX_MODULES = frozenset({"re", "regex"})


def _regex_modules(tree: ast.AST) -> frozenset[str]:
    """The bare names read as a regular-expression module.

    An ``import re`` or ``import regex`` binds its name or its alias, wherever
    it stands — a function's local import counts module-wide — and the import
    wins over any other binding of the same name. A name otherwise BOUND to a
    value (an assignment at any depth of its targets, an annotated one holding
    a value, ``:=``, a ``for`` or ``async for``, ``with`` or comprehension
    target) is a compiled pattern,
    whatever it is called (``regex = re.compile(…)``): read by its spelling,
    such a pattern was read as the module, and its replacement taken from the
    subject's place. Any other name keeps its spelling's reading: ``re`` and
    ``regex`` are the module, everything else a pattern.
    """
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name in _REGEX_MODULES
    }
    bound = {
        name.id
        for node in ast.walk(tree)
        for target in _value_targets(node)
        for name in ast.walk(target)
        if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store)
    }
    return frozenset(imported | (_REGEX_MODULES - bound))


def _value_targets(node: ast.AST) -> list[ast.expr]:
    """What a node binds a VALUE to — never an import.

    Args:
        node: Any node of the module.

    Returns:
        An assignment's targets, an annotated assignment's when it holds a
        value (a bare annotation binds nothing), a ``:=``, ``for`` or
        ``async for``, ``with`` or comprehension target; nothing for any other
        node.
    """
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign):
        return [node.target] if node.value is not None else []
    if isinstance(node, ast.NamedExpr | ast.For | ast.AsyncFor | ast.comprehension):
        return [node.target]
    if isinstance(node, ast.withitem) and node.optional_vars is not None:
        return [node.optional_vars]
    return []


def _replacements(node: ast.Call, modules: frozenset[str]) -> list[ast.expr]:
    """What a ``.sub`` substitutes in: the module's ``sub(pattern, repl, …)``
    names it second, a compiled ``PATTERN.sub(repl, …)`` first — or either by
    the ``repl=`` keyword. The module is a bare name ``modules`` binds; an
    attribute (``self.regex``) is always a pattern."""
    receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
    module_call = isinstance(receiver, ast.Name) and receiver.id in modules
    positional = node.args[1:2] if module_call else node.args[:1]
    return [*positional, *(kw.value for kw in node.keywords if kw.arg == "repl")]


def _other_joins(node: ast.AST, modules: frozenset[str]) -> list[str]:
    """A separator joined without an f-string: ``+``, ``%``, ``.format``, ``.join``,
    or substituted in (``re.sub`` or ``regex.sub``, a compiled pattern's ``.sub``,
    ``str.replace``)."""
    if isinstance(node, ast.BinOp):
        return _operator_joins(node)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return _method_joins(node, node.func.attr, _text(node.func.value), modules)
    return []


def _findings(tree: ast.AST) -> list[tuple[int, str]]:
    """Every (line, what is joined) where a colon is written instead of the door."""
    unread = _unread(tree)
    modules = _regex_modules(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if id(node) in unread:
            continue
        if isinstance(node, ast.JoinedStr):
            found.extend((node.lineno, expression) for expression in _separators(node))
        else:
            found.extend((getattr(node, "lineno", 0), what) for what in _other_joins(node, modules))
    return found


def _is_surface(module: str) -> bool:
    return any(
        module.startswith(surface) if surface.endswith("/") else module == surface
        for surface in SURFACES
    )


def _enclosing(tree: ast.AST, line: int) -> str:
    """The innermost function holding a line, or ``<module>``."""
    owners = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.lineno <= line <= (node.end_lineno or node.lineno)
    ]
    if not owners:
        return "<module>"
    return min(owners, key=lambda node: (node.end_lineno or node.lineno) - node.lineno).name


@cache
def _sites() -> tuple[tuple[str, str, int, str], ...]:
    """Every (module, function, line, what is joined) where a surface writes its own colon."""
    found: list[tuple[str, str, int, str]] = []
    for path in sorted(SRC.rglob("*.py")):
        module = str(path.relative_to(SRC)).replace("\\", "/")
        if not _is_surface(module):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found.extend((module, _enclosing(tree, line), line, what) for line, what in _findings(tree))
    return tuple(found)


def _fstring(source: str) -> ast.JoinedStr:
    node = ast.parse(source, mode="eval").body
    assert isinstance(node, ast.JoinedStr)
    return node


@pytest.mark.parametrize(
    "source",
    [
        'f"{label}: {value}"',
        'f"{label} : {value}"',
        'f"- **{label}** : {value}"',
        'f"**{label}:**"',
        f'f"{{label}}{_FULL_WIDTH_COLON}{{value}}"',
        f'f"{{label}}{_NBSP}: {{value}}"',
        'f"{label}:"',
        'f"**{label}** ({stamp}):\\n{value}"',
        'f"<a>{label}</a>: {value}"',
        'f"{label}:<br/>{value}"',
    ],
)
def test_the_rule_sees_a_literal_label_colon(source: str) -> None:
    """A guard that finds nothing guards nothing: each shape it exists for is seen."""
    assert _separators(_fstring(source)) in (["label"], ["stamp"])


@pytest.mark.parametrize(
    "source",
    [
        'label + ": " + value',
        '"%s: %s" % (label, value)',
        '"{}: {}".format(label, value)',
        '": ".join(parts)',
        're.sub("</dt>", " : ", html)',
        '_DT_CLOSE.sub(" : ", html)',
        're.sub("</dt>", repl=" : ", string=html)',
        '_DT_CLOSE.sub(repl=" : ", string=html)',
        'regex.sub("</dt>", " : ", html)',
        'regex = re.compile("</dt>")\nregex.sub(" : ", html)',
        'self.regex.sub(" : ", html)',
        'pattern.regex.sub(" : ", html)',
        'import re as _re\n_re.sub("</dt>", " : ", html)',
        'import regex as rx\nrx.sub("</dt>", " : ", html)',
        'from re import compile\nre = compile("</dt>")\nre.sub(" : ", html)',
        'regex: re.Pattern[str] = re.compile("</dt>")\nregex.sub(" : ", html)',
        '(regex := re.compile("</dt>"))\nregex.sub(" : ", html)',
        'def f(html):\n    import re as x\n    return x.sub("</dt>", " : ", html)',
        # The import wins over any other binding of its name (review 13).
        'import re\nre = compile_all()\nre.sub("</dt>", " : ", html)',
        # A pattern unpacked, looped over or opened is a value like one assigned.
        'regex, flags = re.compile("</dt>"), 0\nregex.sub(" : ", html)',
        'for regex in (re.compile("</dt>"),):\n    regex.sub(" : ", html)',
        'with compiled() as regex:\n    regex.sub(" : ", html)',
        'async def f(patterns, html):\n    async for regex in patterns:\n        regex.sub(" : ", html)',
        # A bare annotation binds nothing: the name keeps its spelling's reading.
        'regex: re.Pattern[str]\nregex.sub("</dt>", " : ", html)',
        '[regex.sub(" : ", html) for regex in patterns]',
        # Neither imported nor bound: read by its spelling, as the module.
        'from compat import regex_module as regex\nregex.sub("</dt>", " : ", html)',
        'def f(regex, html):\n    return regex.sub("</dt>", " : ", html)',
        'html.replace("</dt>", " : ")',
        '"".join([label, " : ", value])',
        'label + "：" + value',
        'label + ":\\n" + value',
        '":\\n".join(parts)',
    ],
)
def test_the_rule_sees_a_separator_joined_another_way(source: str) -> None:
    assert _findings(ast.parse(source))


@pytest.mark.parametrize(
    "source",
    [
        'f"Reason : {value}"',
        'f"**Email:** {value}"',
        'f"<strong>Name :</strong> {value}"',
        f'f"Motif{_FULL_WIDTH_COLON}{{value}}"',
    ],
)
def test_the_rule_sees_a_label_written_out_before_its_value(source: str) -> None:
    """Written before the value rather than after it, the colon is still the
    code's, not the reader's."""
    assert _separators(_fstring(source)) == ["value"]


def test_a_site_is_filed_under_its_innermost_function() -> None:
    """An allowance names the function holding its site: filed under the outer
    one, it would cover every other site the outer function holds."""
    tree = ast.parse("def outer():\n    def inner():\n        return 1\n    return inner\n")

    assert _enclosing(tree, 3) == "inner"
    assert _enclosing(tree, 4) == "outer"


@pytest.mark.parametrize(
    "source",
    [
        '":".join([hours, minutes])',
        'hours + ":" + minutes',
        'prefix + ":" + user_id',
        '"".join([scheme, ":", path])',
    ],
)
def test_an_ascii_colon_with_no_space_joined_another_way_passes(source: str) -> None:
    """A clock or a key: the bare colon was read as a label's separator."""
    assert _findings(ast.parse(source)) == []


@pytest.mark.parametrize(
    "source",
    [
        'f"{hours}:{minutes:02d}"',
        'f"{scheme}://{host}"',
        'f"{label}{separator}{value}"',
        'f"{prefix}:{user_id}"',
    ],
)
def test_a_clock_a_url_a_key_and_the_language_s_separator_pass(source: str) -> None:
    assert _separators(_fstring(source)) == []


def test_a_log_line_and_an_exception_are_not_read_by_a_person() -> None:
    tree = ast.parse(
        'logger.warning("x", error=f"{kind}: {e}")\nraise ValueError(f"{field}: invalid")\n'
    )
    assert _findings(tree) == []


def test_a_call_that_merely_looks_like_a_log_is_read() -> None:
    """``dialog.info(...)`` is a dialog: the receiver's NAME decides, not a substring."""
    assert _findings(ast.parse('dialog.info(f"{label}: {value}")'))


def test_every_surface_joins_a_label_and_its_value_by_the_reader_s_punctuation() -> None:
    offenders = [
        f"  {module}:{line} ({function}) {{{expression}}}"
        for module, function, line, expression in _sites()
        if (module, function, expression) not in ALLOWED
    ]
    assert not offenders, (
        "a label and its value joined by a colon written in the code — use "
        "`label_separator(language)` (core/i18n_drafts.py):\n" + "\n".join(offenders)
    )


def test_every_allowance_matches_exactly_one_site() -> None:
    """Shrink-only, and never a free pass: a second identical join is a new decision."""
    live = Counter((module, function, expression) for module, function, _l, expression in _sites())
    wrong = sorted(f"{key}: {live[key]} sites" for key in ALLOWED if live[key] != 1)
    assert not wrong, f"an allowance covers exactly one site — decide each other: {wrong}"


def test_every_surface_exists() -> None:
    missing = [surface for surface in SURFACES if not (SRC / surface).exists()]
    assert not missing, f"declared surfaces that no longer exist: {missing}"
