"""AST guard: no sentence is written in a language nobody declared (ADR-323).

A language the caller did not pass is resolved by ``core.i18n.resolve_language``:
the language declared for the current request (its Accept-Language, then the
authenticated account's own), turn or job (the person it serves), else the
instance's configured ``DEFAULT_LANGUAGE``. A known person's stored language is
read through ``normalize_language``.

What this forbids is every way code used to decide the language on its own —
each one writes that language to everybody who was not passed explicitly, and
nothing fails: a German reader simply gets French. Measured by this very scan on
the last release before the rule (4f19469b): 670 sites in 195 files — 456
language parameters defaulting to a fixed language, 55 ``x or <fixed>``, 44
``.get(key, <fixed>)``, 55 fields, constants, pinned entries, local
assignments or entries under a language-named key (among them
``_DEFAULT = "en"`` in six data modules, ``locale = settings.default_language``
in three tools, and — legitimate then as now — the ``DEFAULT_LANGUAGE`` setting
with its own constant, two constants naming the language the prompt files are
written in and the pricing sheet's key set), 16 conditional fallbacks, 6
``getattr`` fallbacks, 3 call arguments, 34 other reads of the instance default
(``TABLE.get(lang, TABLE[DEFAULT_LANGUAGE])`` in the i18n tables, a
``(settings.default_language, "en")`` fallback chain among them) and 1 tuple
returning it. Each review that widened the scan re-ran it there: 621 for the
first four versions, 633 for the fifth, 670 since the sixth.

Shapes, over every ``src/**/*.py`` (a FIXED language is a code or locale
literal in either spelling and any case — ``fr-FR``, ``fr_FR``, ``FR`` —, a name
holding the instance default — ``DEFAULT_LANGUAGE``, ``DEFAULT_LANGUAGE_DEFAULT``,
module-qualified or not —, ``*.default_language``, a lambda returning one, ``str()`` of one, an
f-string made of one alone, or ``text("'fr'")``; a language NAME is ``lang``,
``language`` or ``locale``, alone or ending a compound, singular or plural, with
an optional ``code``/``codes``/``hint``/``tag``/``tags`` suffix, in snake, camel or kebab
case — ``language_hint``, ``languageCode``, ``accept-language`` — the reading
``tests/_language_names.py`` shares with the two other i18n guards):

1. a parameter, dataclass, Pydantic field or column DEFAULTING to a fixed
   language (``Field(...)``/``Query(...)``/``Header``/``Cookie``/``Path``/
   ``Body``/``Form``/``field(...)``/``mapped_column(...)``/``Column(...)``/``PrivateAttr(...)``/
   ``ContextVar(...)``/``Depends(...)`` defaults included — ``default_factory=``,
   ``insert_default=`` and a column's ``server_default=`` too —, declared as the
   value OR inside an ``Annotated[...]``, a module-level ``Annotated`` alias
   included); a field call declares one whatever the name, at module and
   class level; a bare value declares one at class level only, and only on a
   language-named attribute — at module level a bare value is a constant
   (shape 8). Shapes 8 and 9 read class constants too, so an enum member named
   after a code (``FR = "fr"``) passes and one named like a default
   (``FALLBACK = "en"``) does not;
2. ``x or <fixed>``, whatever the operand's position;
3. ``.get(key, <fixed>)``, ``.pop(key, <fixed>)``, ``.setdefault(key, <fixed>)``;
4. ``getattr(obj, name, <fixed>)``;
5. ``a if cond else <fixed>`` and ``<fixed> if cond else a``;
6. a language-named local, attribute, subscript key or dict key assigned a
   fixed language (``lang = "fr"``, ``(lang := "fr")``, ``language_code = "fr"``,
   ``self.language = "fr"``, ``lang = settings.default_language``,
   ``state["user_language"] = "fr"``,
   ``{"user_language": settings.default_language}``);
7. a call passing a fixed language to a language-named keyword (``language=``,
   ``locale=``, ``language_code=``, ``default_language=``…);
8. a module or class constant naming a default language (``_DEFAULT = "en"``,
   ``LANGUAGE_FALLBACK = "fr"``, ``DEFAULT_LOCALE = "fr_FR"``) or named after a
   language (``SOURCE_LANGUAGE = "fr"``), holding a literal or any other fixed
   language (``FALLBACK_LANGUAGE = settings.default_language``);
9. a module or class constant pinned to ONE language's entry of a table, at any
   depth of its value and formatted or not (``MESSAGE = MESSAGES["fr"]``,
   ``MESSAGES.get("fr")``, ``MESSAGES["fr"]["greeting"]``,
   ``MESSAGES[DEFAULT_LANGUAGE].format(…)``, ``str(MESSAGES["fr"])``,
   ``MESSAGES["fr"] + "!"``) — every reader of it reads that language;
10. any other READ of the instance default (``*.default_language``,
    ``DEFAULT_LANGUAGE``…) — ``translate(key, settings.default_language)``,
    ``TABLE.get(lang, TABLE[DEFAULT_LANGUAGE])``: reading it is deciding the
    language for whoever was not passed, so only the resolver reads it and
    every other reader is declared;
11. a fallback CHAIN — a tuple or list mixing a fixed language with a value
    (``for wanted in (language, "en")``), unless it is an operand of a
    comparison or a subscript's (a type's) tuple.

What it does NOT read: a code literal passed POSITIONALLY (nothing at the call
site says which argument is the language); a value computed at run time — a
concatenation or a ``%`` included (``"f" + "r"``); a language pinned INSIDE a
function body (``LABELS["en"]`` there is a read, often of a key set the six
languages share) — a constant of a class defined inside a function included;
a code among LITERALS (a vocabulary, and a table is the completeness guards'
business); a name imported under an alias (``from src.core.constants import
DEFAULT_LANGUAGE_DEFAULT as FALLBACK``); an ``Annotated`` metadata STRING (a
description, never a default); and, in a log call, shapes 6 (a key), 10 and
11 anywhere in its arguments and shape 7 on its OWN keywords (a call nested
in its arguments is read as anywhere) — a log line REPORTS the default, it
decides nothing. A log call is a method called on a receiver NAMED
``logger`` or ``log``, the only two spellings this guard reads
(``self.logger`` and ``_logger`` are read as any call); a fallback (shapes 2
to 5) is read there as anywhere. A provider mapping (``zh-CN`` → a vendor's
``zh``) is written as a dict lookup, which a conditional expression is not
(shape 5 reads one).

A legitimate site is declared in ``ALLOWED`` by file and source text, with the
number of sites it covers and the reason — a further identical site is a new
decision (``test_an_allowance_covers_exactly_its_sites``);
``test_every_allowance_is_still_used`` deletes a stale one (shrink-only).
Comparisons (``if lang == "fr"``) are NOT forbidden: language-specific rules
are legitimate. Language-keyed TABLES are the business of the completeness
guards, not of this one.
"""

from __future__ import annotations

import ast
import functools
import re
from collections.abc import Mapping
from types import MappingProxyType

import pytest

from tests._language_names import is_language_name
from tests._repo_paths import find_apps_api_root

pytestmark = pytest.mark.unit

SRC = find_apps_api_root() / "src"

#: Language and locale spellings a literal default could pin.
CODES: frozenset[str] = frozenset(
    {
        "fr",
        "en",
        "es",
        "de",
        "it",
        "zh",
        "zh-CN",
        "zh_CN",
        "fr-FR",
        "fr_FR",
        "en-US",
        "en_US",
        "en-GB",
        "en_GB",
        "es-ES",
        "es_ES",
        "de-DE",
        "de_DE",
        "it-IT",
        "it_IT",
    }
)

#: The same spellings, compared case-insensitively (``FR``, ``zh-cn``).
_CODES_FOLDED: frozenset[str] = frozenset(code.lower() for code in CODES)

#: Names that hold the instance default — reading it IS deciding the language.
DEFAULT_NAMES: frozenset[str] = frozenset(
    {"DEFAULT_LANGUAGE", "_DEFAULT_LANGUAGE", "DEFAULT_LANGUAGE_DEFAULT"}
)

#: Pydantic / FastAPI / dataclass / SQLAlchemy / contextvars constructors declaring
#: a default (``default=``; for all but ``COLUMN_CALLS``, also the first positional one).
FIELD_CALLS: frozenset[str] = frozenset(
    {
        "Field",
        "Query",
        "Header",
        "Cookie",
        "Path",
        "Body",
        "Form",
        "field",
        "mapped_column",
        "Column",
        "PrivateAttr",
        "ContextVar",
        "Depends",
    }
)

#: Keywords that declare a default (a value, a factory, or the column's DDL one).
DEFAULT_KEYWORDS: frozenset[str] = frozenset(
    {"default", "default_factory", "insert_default", "server_default"}
)

#: Constructors whose first positional argument is NOT a default (a column's
#: type or name, a context variable's name).
COLUMN_CALLS: frozenset[str] = frozenset({"mapped_column", "Column", "ContextVar"})

_DEFAULT_CONSTANT = re.compile(r"(?i)^_?(default|fallback)(_lang|_language|_locale)?$")

#: Legitimate sites: (path under src/, exact source text of the flagged node)
#: -> (number of sites it covers, reason).
ALLOWED: dict[tuple[str, str], tuple[int, str]] = {
    ("core/i18n.py", "_declared_language.get() or settings.default_language"): (
        1,
        "the resolver itself: nothing declared, the instance default",
    ),
    ("core/i18n.py", "canonical_language(language) or settings.default_language"): (
        1,
        "the chokepoint itself: a given language nobody supports reads as the default",
    ),
    ("core/constants.py", 'DEFAULT_LANGUAGE_DEFAULT: Final = "fr"'): (
        1,
        "the DEFAULT_LANGUAGE setting's own default, where every setting default lives",
    ),
    (
        "core/config/advanced.py",
        "default_language: Language = Field( default=DEFAULT_LANGUAGE_DEFAULT, description=( "
        '"Language of every sentence written for nobody known: no explicit " '
        '"language and none declared by the request, turn or job (ADR-323)" ), )',
    ): (1, "the setting itself, defaulting to its own constant"),
    (
        "domains/users/models.py",
        "language: Mapped[str] = mapped_column( String(10), default=lambda: "
        "settings.default_language, nullable=False, server_default=DEFAULT_LANGUAGE_DEFAULT, "
        'comment="User preferred language (ISO 639-1 code: fr, en, es, de, it, zh-CN) for '
        'emails and notifications", )',
    ): (
        1,
        "a schema default cannot read a setting: the DDL default is the setting's own "
        "constant, and every ORM insert takes the CONFIGURED default (``default=``)",
    ),
    (
        "core/i18n_pricing_sheet.py",
        "SHEET_LABEL_KEYS: tuple[str, ...] = tuple( [_COLUMN_PREFIX + key for key in "
        '_COLUMNS["en"]] + list(_STRINGS["en"]) )',
    ): (
        1,
        "the KEY set of the English table, which every language shares "
        "(tests/unit/core/test_i18n_pricing_sheet.py holds the inner key parity) — "
        "no reader reads English text through it",
    ),
    ("core/i18n.py", "settings.default_language"): (
        1,
        "the chokepoint's translator: a language with no catalog reads the " "instance default's",
    ),
    ("core/config/advanced.py", "self.default_language"): (
        2,
        "the setting's own validator, checking it against SUPPORTED_LANGUAGES",
    ),
    ("api/v1/routes.py", "settings.default_language"): (
        1,
        "the public configuration PUBLISHES the instance default — the frontend "
        "reads it, nothing is written in it",
    ),
    ("domains/personalities/models.py", "(language_code, settings.default_language)"): (
        1,
        "a personality translation's documented fallback: the requested "
        "language, then the instance default — never a language of the code's own",
    ),
    ("domains/live/direct_mandate.py", '_PROMPT_LANGUAGE: Final = "en"'): (
        1,
        "the language the prompt FILE is written in — the model reads English, so "
        "the domains it names are rendered in English whoever speaks",
    ),
    ("domains/telephony/mandates.py", 'PROMPT_LANGUAGE: Final = "en"'): (
        1,
        "the language the prompt FILES are written in — the model reads English, so "
        "the domains they name are rendered in English whoever calls",
    ),
}


def _is_language_name(name: str) -> bool:
    """A language name — the one reading the three i18n guards share."""
    return is_language_name(name)


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""


def _is_fixed(node: ast.AST | None) -> bool:
    """A value that decides a language on the caller's behalf."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value.lower() in _CODES_FOLDED
    if isinstance(node, ast.Name):
        return node.id in DEFAULT_NAMES
    if isinstance(node, ast.Attribute):  # settings.default_language, constants.DEFAULT_…
        return node.attr == "default_language" or node.attr in DEFAULT_NAMES
    return _wraps_fixed(node)


def _wraps_fixed(node: ast.AST | None) -> bool:
    """A fixed language behind a wrapper: ``str()``, a lone f-string, a lambda,
    or a column's ``text()`` DDL."""
    if isinstance(node, ast.Call) and _call_name(node) == "str" and len(node.args) == 1:
        return _is_fixed(node.args[0])  # str("fr")
    if isinstance(node, ast.JoinedStr) and len(node.values) == 1:
        part = node.values[0]  # f"{DEFAULT_LANGUAGE}"
        return isinstance(part, ast.FormattedValue) and _is_fixed(part.value)
    if isinstance(node, ast.Lambda):  # default_factory=lambda: "fr"
        return _is_fixed(node.body)
    if isinstance(node, ast.Call) and _call_name(node) == "text" and len(node.args) == 1:
        literal = node.args[0]  # server_default=text("'fr'")
        return (
            isinstance(literal, ast.Constant)
            and isinstance(literal.value, str)
            and literal.value.strip("'\"").lower() in _CODES_FOLDED
        )
    return False


def _field_defaults(node: ast.AST) -> list[ast.expr]:
    """The defaults a ``Field(...)``-like call declares (a column's DDL one included)."""
    if not isinstance(node, ast.Call):
        return []
    name = _call_name(node)
    if name not in FIELD_CALLS:
        return []
    found = [kw.value for kw in node.keywords if kw.arg in DEFAULT_KEYWORDS]
    if any(kw.arg in {"default", "default_factory"} for kw in node.keywords):
        return found
    if name in COLUMN_CALLS:  # the first positional argument is the column TYPE or name
        return found
    return [*found, node.args[0]] if node.args else found


def _is_fixed_default(node: ast.AST | None) -> bool:
    return node is not None and (
        _is_fixed(node) or any(_is_fixed(default) for default in _field_defaults(node))
    )


def _annotated_defaults(annotation: ast.expr | None) -> list[ast.expr]:
    """The field calls an ``Annotated[T, Field(...)]`` annotation carries, at any depth."""
    found: list[ast.expr] = []
    for node in ast.walk(annotation) if annotation is not None else ():
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, (ast.Name, ast.Attribute))
            and (node.value.id if isinstance(node.value, ast.Name) else node.value.attr)
            == "Annotated"
            and isinstance(node.slice, ast.Tuple)
        ):
            found.extend(node.slice.elts[1:])
    return found


def _annotation_pins(annotation: ast.expr | None) -> bool:
    """Whether an annotation's field call declares a fixed default.

    Only a CALL declares one: ``Annotated[str, "fr"]`` carries a description.
    """
    return any(
        isinstance(meta, ast.Call) and _is_fixed_default(meta)
        for meta in _annotated_defaults(annotation)
    )


def _is_default_constant(name: str) -> bool:
    """A constant named like a default language, or after a language."""
    upper = name.upper()
    return bool(
        _DEFAULT_CONSTANT.match(name)
        or (("DEFAULT" in upper or "FALLBACK" in upper) and ("LANG" in upper or "LOCALE" in upper))
        or _is_language_name(name)
    )


def _is_log_call(node: ast.Call) -> bool:
    """``logger.warning(…)`` and its siblings: a field there reports, it never decides."""
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in {"logger", "log"}
    )


def _pins_one_language(value: ast.AST) -> bool:
    """A value read through ONE language's entry of a table, at any depth.

    ``MESSAGES["fr"]``, ``MESSAGES["fr"]["greeting"]`` and
    ``MESSAGES[DEFAULT_LANGUAGE].format(…)`` all pin a language.
    """
    node = value
    while True:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "get" and node.args and _is_fixed(node.args[0]):
                return True  # MESSAGES.get("fr")
            node = node.func.value
        elif isinstance(node, ast.Subscript):
            if _is_fixed(node.slice):
                return True
            node = node.value
        else:
            return False


def _violations(tree: ast.AST) -> list[ast.expr | ast.stmt]:
    """Every node deciding a language on its own, once each."""
    unique = {id(node): node for _shape, node in _labelled(tree)}
    return list(unique.values())


def _class_default(stmt: ast.stmt) -> bool:
    """A class-level attribute that DECLARES a fixed language default.

    A field call (``Field("fr")``) declares one whatever the attribute is called;
    a bare value does only on a language-named attribute — ``FR = "fr"`` in an
    enum is a member's value, not a default.
    """
    if isinstance(stmt, ast.AnnAssign):
        targets: list[ast.expr] = [stmt.target]
        annotation: ast.expr | None = stmt.annotation
    elif isinstance(stmt, ast.Assign):
        targets, annotation = list(stmt.targets), None
    else:
        return False
    if _annotation_pins(annotation):
        return True
    value = stmt.value
    if value is None:
        return False
    if any(_is_fixed(default) for default in _field_defaults(value)):
        return True
    named = any(isinstance(t, ast.Name) and _is_language_name(t.id) for t in targets)
    return named and _is_fixed(value)


_Found = list[tuple[str, ast.expr | ast.stmt]]


def _parameter_defaults(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> _Found:
    """Shape 1: a parameter defaulting to a fixed language, as a value or inside
    an ``Annotated[...]``."""
    args = node.args
    found: _Found = [
        ("1", default)
        for default in [*args.defaults, *args.kw_defaults]
        if default is not None and _is_fixed_default(default)
    ]
    if not isinstance(node, ast.Lambda):
        parameters = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        found.extend(
            ("1", arg.annotation)
            for arg in parameters
            if arg.annotation is not None and _annotation_pins(arg.annotation)
        )
    return found


def _call_shapes(node: ast.Call) -> _Found:
    """Shapes 3, 4 and 7 of a call: a lookup's fixed fallback, a ``getattr``'s,
    or a fixed language handed to a language-named keyword (a log line
    REPORTING the default decides nothing)."""
    func = node.func
    found: _Found = []
    lookup = isinstance(func, ast.Attribute) and func.attr in {"get", "pop", "setdefault"}
    if lookup and len(node.args) == 2 and _is_fixed(node.args[1]):
        found.append(("3", node))
    is_getattr = isinstance(func, ast.Name) and func.id == "getattr"
    if is_getattr and len(node.args) == 3 and _is_fixed(node.args[2]):
        found.append(("4", node))
    keywords = [] if _is_log_call(node) else node.keywords
    found.extend(
        ("7", node)
        for kw in keywords
        if kw.arg is not None and _is_language_name(kw.arg) and _is_fixed(kw.value)
    )
    return found


def _expression_shapes(node: ast.AST) -> _Found:
    """Shapes 2, 5 and 6 of an expression: ``x or <fixed>`` whatever the
    operand's position, a conditional with a fixed branch, and
    ``(lang := "fr")`` — a walrus binds a local like an assignment does."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        fixed = any(_is_fixed(operand) for operand in node.values)
        return [("2", node)] if fixed else []
    if isinstance(node, ast.IfExp):
        fixed = _is_fixed(node.orelse) or _is_fixed(node.body)
        return [("5", node)] if fixed else []
    if isinstance(node, ast.NamedExpr):
        fixed = _is_language_name(node.target.id) and _is_fixed(node.value)
        return [("6", node)] if fixed else []
    return []


def _constant_shape(names: list[str], value: ast.expr, is_fixed: bool) -> str | None:
    """Shapes 1, 8 and 9 of a module or class constant: an ``Annotated`` alias
    or a field call declaring a fixed default (1), a constant naming a default
    language (8), or one pinned to one language's entry of a table at any
    depth (9)."""
    if _annotation_pins(value):
        return "1"
    # A field call declares a default whatever the constant is called — the
    # codebase names a context variable ``*_ctx`` — as at class level.
    if any(_is_fixed(default) for default in _field_defaults(value)):
        return "1"
    if any(_is_default_constant(name) for name in names) and is_fixed:
        return "8"
    pinned = (sub for sub in ast.walk(value) if isinstance(sub, ast.expr))
    return "9" if any(_pins_one_language(sub) for sub in pinned) else None


def _assigned(node: ast.Assign | ast.AnnAssign) -> tuple[list[str], list[str]]:
    """The names and the attributes an assignment binds."""
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names = [t.id for t in targets if isinstance(t, ast.Name)]
    return names, [t.attr for t in targets if isinstance(t, ast.Attribute)]


def _assignment_shapes(node: ast.Assign | ast.AnnAssign, local: bool) -> _Found:
    """Shape 6 (a language-named local or attribute assigned a fixed language)
    and, outside a function, shapes 1, 8 and 9 of a constant."""
    names, attributes = _assigned(node)
    value = node.value
    is_fixed = value is not None and _is_fixed(value)
    if is_fixed and any(_is_language_name(a) for a in attributes):
        return [("6", node)]
    if local:
        named = any(_is_language_name(n) for n in names)
        return [("6", node)] if is_fixed and named else []
    if value is None or not names:
        return []
    shape = _constant_shape(names, value, is_fixed)
    return [(shape, node)] if shape else []


def _node_shapes(node: ast.AST, local_nodes: set[int]) -> _Found:
    """The shapes (1-9) one node shows."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return _parameter_defaults(node)
    if isinstance(node, ast.ClassDef):
        # Class-level field defaults (dataclass / Pydantic / settings).
        return [("1", stmt) for stmt in node.body if _class_default(stmt)]
    if isinstance(node, ast.Call):
        return _call_shapes(node)
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        return _assignment_shapes(node, id(node) in local_nodes)
    return _expression_shapes(node)


def _labelled(tree: ast.AST) -> _Found:
    """Every violation with the shape (1-11) that caught it."""
    functions = [
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    local_nodes = {id(sub) for fn in functions for sub in ast.walk(fn) if sub is not fn}
    found = [hit for node in ast.walk(tree) for hit in _node_shapes(node, local_nodes)]
    found.extend(_chains_and_entries(tree))
    found.extend(_default_reads(tree, found))
    return found


def _language_key(node: ast.AST | None) -> bool:
    """A string key naming a language (``"user_language"``, ``"locale"``)."""
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _is_language_name(node.value)
    )


def _logged_ids(tree: ast.AST) -> set[int]:
    """Every node inside a log call: a log line REPORTS the default, it decides nothing."""
    return {
        id(sub)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_log_call(node)
        for sub in ast.walk(node)
    }


def _never_chains(tree: ast.AST) -> set[int]:
    """The sequences that fall back to nothing: a comparison's operand tests a
    language; a subscript's tuple is a type (``Annotated[str, "fr"]``) or a key."""
    compared = {
        id(operand)
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        for operand in [node.left, *node.comparators]
    }
    return compared | {id(node.slice) for node in ast.walk(tree) if isinstance(node, ast.Subscript)}


def _chains_and_entries(tree: ast.AST) -> _Found:
    """Shape 11 (a fallback chain) and shape 6 under a language-named key."""
    found: _Found = []
    never_chains = _never_chains(tree)
    logged = _logged_ids(tree)
    for node in ast.walk(tree):
        if id(node) in logged:
            continue
        if isinstance(node, ast.Tuple | ast.List) and id(node) not in never_chains:
            if _is_fallback_chain(node):
                found.append(("11", node))
        elif isinstance(node, ast.Assign) and _is_fixed(node.value):
            if _keyed_by_language(node):
                found.append(("6", node))
        elif isinstance(node, ast.Dict):
            found.extend(("6", value) for value in _language_entries(node))
    return found


def _is_fallback_chain(node: ast.Tuple | ast.List) -> bool:
    """11. ``(language, "en")``: a chain that falls back to a language of its
    own — a fixed language beside a VALUE; a list of literals is a vocabulary
    (weekday abbreviations, country codes), never a chain."""
    return any(_is_fixed(element) for element in node.elts) and any(
        not _is_fixed(element) and not isinstance(element, ast.Constant) for element in node.elts
    )


def _keyed_by_language(node: ast.Assign) -> bool:
    """6. ``state["user_language"] = "fr"``."""
    return any(
        isinstance(target, ast.Subscript) and _language_key(target.slice) for target in node.targets
    )


def _language_entries(node: ast.Dict) -> list[ast.expr]:
    """6. ``{"user_language": settings.default_language}``: the fixed values."""
    return [
        value
        for key, value in zip(node.keys, node.values, strict=True)
        if _language_key(key) and _is_fixed(value)
    ]


def _default_reads(
    tree: ast.AST, found: list[tuple[str, ast.expr | ast.stmt]]
) -> list[tuple[str, ast.expr | ast.stmt]]:
    """Shape 10: a read of the instance default no other shape already caught.

    Reading the instance default IS deciding the language for whoever was not
    passed — ``translate(key, settings.default_language)`` and
    ``(settings.default_language, "en")`` wrote one to everybody, and no other
    shape saw them. Only the resolver may read it; any other reader is declared.
    """
    covered = {id(sub) for _shape, node in found for sub in ast.walk(node)}
    logged = _logged_ids(tree)
    return [
        ("10", node)
        for node in ast.walk(tree)
        if (
            (isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load))
            or (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load))
        )
        and _is_fixed(node)
        and id(node) not in covered
        and id(node) not in logged
    ]


@functools.cache
def _scan() -> Mapping[tuple[str, str], tuple[int, ...]]:
    """(path, source text) -> lines, for every violation in src/ (scanned once).

    Identical text in one file keeps EVERY line, so an allowance cannot silently
    absorb a second site.
    """
    offenders: dict[tuple[str, str], list[int]] = {}
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in _violations(tree):
            text = ast.get_source_segment(source, node) or ""
            offenders.setdefault((relative, " ".join(text.split())), []).append(node.lineno)
    return MappingProxyType({key: tuple(lines) for key, lines in offenders.items()})


class TestNoLanguageDecidedLocally:
    """A language absent from the caller is the DECLARED one, never a literal."""

    def test_no_fixed_language_default_in_src(self) -> None:
        offenders = {key: lines for key, lines in _scan().items() if key not in ALLOWED}

        assert not offenders, (
            "A language decided locally writes it to everybody not passed "
            "explicitly — resolve an absent language with resolve_language(), "
            "read a known person's with normalize_language(person.language) "
            "(ADR-323):\n"
            + "\n".join(
                f"  {path}:{line} — {text}"
                for (path, text), lines in sorted(offenders.items())
                for line in lines
            )
        )

    def test_an_allowance_covers_exactly_its_sites(self) -> None:
        """A further site identical to an allowed one is a new decision, not a free pass."""
        miscounted = {
            key: f"declared {ALLOWED[key][0]}, found {len(lines)} at lines {list(lines)}"
            for key, lines in _scan().items()
            if key in ALLOWED and len(lines) != ALLOWED[key][0]
        }

        assert not miscounted, (
            "An allowance states how many sites it covers — raise its count only "
            f"after deciding each new site: {miscounted}"
        )

    def test_every_allowance_is_still_used(self) -> None:
        """Shrink-only: an allowance whose code no longer needs it must go."""
        stale = sorted(set(ALLOWED) - set(_scan()))

        assert not stale, f"These allowances match nothing any more — remove them: {stale}"


class TestGuardOracle:
    """The guard must flag every shape that shipped, and nothing legitimate."""

    @pytest.mark.parametrize(
        "source",
        [
            'def f(language: str = "fr") -> None: ...',
            "def f(language: str = settings.default_language) -> None: ...",
            "def f(*, lang: str = DEFAULT_LANGUAGE) -> None: ...",
            'class M:\n    language: str = Field("fr")',
            'class M:\n    language: str = Field(default="en")',
            'class T:\n    locale: Mapped[str] = mapped_column(String(10), default="fr")',
            'class T:\n    language: Mapped[str] = mapped_column(String(10), server_default="fr")',
            "class D:\n    language: str = settings.default_language",
            'x = user.language or "fr"',
            "x = user.language or settings.default_language",
            'x = state.get("user_language", "fr")',
            'x = getattr(user, "language", "en")',
            'x = lang if lang else "fr"',
            'def f():\n    lang = "fr"',
            'send(text, language="fr")',
            '_DEFAULT = "en"',
            '_DEFAULT_LANGUAGE = "en"',
            # Shapes the first version missed (review of 2026-09-25).
            "def f(language: str = DEFAULT_LANGUAGE_DEFAULT) -> None: ...",
            'x = "fr" if not lang else lang',
            'x = kwargs.pop("language", "fr")',
            'x = options.setdefault("language", "fr")',
            'def f():\n    language_code = "fr"',
            'class C:\n    def __init__(self):\n        self.language = "fr"',
            'MESSAGE = MESSAGES["fr"]',
            # Shapes the guard claimed and missed (review of 2026-09-26).
            'class M:\n    language: str = Field(default_factory=lambda: "fr")',
            'class D:\n    language: str = field(default_factory=lambda: "fr")',
            "class T:\n    language: Mapped[str] = mapped_column(String(10), server_default=text(\"'fr'\"))",
            'class T:\n    language: Mapped[str] = mapped_column(String(10), insert_default="fr")',
            'class T:\n    language = Column(String(10), default="fr")',
            "def f(language: str = constants.DEFAULT_LANGUAGE_DEFAULT) -> None: ...",
            "x = user.language or constants.DEFAULT_LANGUAGE_DEFAULT",
            "send(text, language=settings.default_language)",
            "send(text, language=DEFAULT_LANGUAGE_DEFAULT)",
            'format_date(d, locale="fr_FR")',
            'x = locale or "fr_FR"',
            'send(text, language_code="fr")',
            'send(text, lang_code="fr")',
            'send(text, default_language="fr")',
            'SOURCE_LANGUAGE = "fr"',
            'FALLBACK_LANGUAGE_CODE = "fr"',
            'GREETING = MESSAGES["fr"]["greeting"]',
            "GREETING = MESSAGES[DEFAULT_LANGUAGE]",
            'GREETING = MESSAGES["fr"].format(name="x")',
            # Shapes the guard claimed and missed (review of 2026-09-26, round 4).
            'class M:\n    language: Annotated[str, Field(default="fr")]',
            'class M:\n    lang: Annotated[str | None, Field(default_factory=lambda: "fr")] = None',
            'def f(language: Annotated[str, Query(default="fr")]) -> None: ...',
            'def f(lang: str = Cookie("fr")) -> None: ...',
            'def f(lang: str = Path(default="fr")) -> None: ...',
            'GREETING = MESSAGES.get("fr")',
            'send(text, language_hint="fr")',
            'send(text, languageCode="fr")',
            'x = user.language or str("fr")',
            'x = lang or f"{DEFAULT_LANGUAGE}"',
            'def f():\n    userLanguage = "fr"',
            # Shapes the guard claimed and missed (review of 2026-09-26, round 5).
            'LangQ = Annotated[str, Query(default="fr")]',
            'x = user.language or "fr" or ""',
            'LANGUAGE_FALLBACK = "fr"',
            'DEFAULT_LOCALE = "fr_FR"',
            "DEFAULT_LANG = DEFAULT_LANGUAGE_DEFAULT",
            "FALLBACK_LANGUAGE = settings.default_language",
            'GREETING = str(MESSAGES["fr"])',
            'GREETING = frozenset(LABELS["en"])',
            'GREETING = MESSAGES["fr"] + "!"',
            "GREETING = f\"{MESSAGES['fr']}\"",
            'GREETING = MESSAGES["fr"] if x else MESSAGES["en"]',
            'def f(language: str = "FR") -> None: ...',
            'x = locale or "zh-cn"',
            "def f():\n    lang = settings.default_language",
            "class C:\n    def __init__(self):\n        self.language = settings.default_language",
            '_lang: ContextVar[str] = ContextVar("lang", default="fr")',
            'class M(BaseModel):\n    _lang: str = PrivateAttr(default="fr")',
            'def f(lang: str = Depends(lambda: "fr")) -> None: ...',
            'class C:\n    FALLBACK = "en"',
            # Shapes the guard missed (review of 2026-09-26, round 6): the
            # personality fallback this change removed read the default in a
            # tuple, and every other read of it decides as much.
            'fallback_languages = (settings.default_language, "en")',
            'def f(lang):\n    for wanted in (lang, "en"):\n        pass',
            'def f():\n    return {"user_language": settings.default_language}',
            'def f(state):\n    state["user_language"] = "fr"',
            "def f(prefs):\n    default = settings.default_language\n"
            '    return prefs.get("language", default)',
            "def f(key):\n    return translate(key, settings.default_language)",
            "def f():\n    return [lang, DEFAULT_LANGUAGE]",
            # The binding shape the locale and log content guards follow (review 9).
            'def f():\n    if (language := "fr"):\n        return language',
        ],
    )
    def test_flags_a_shipped_shape(self, source: str) -> None:
        assert _violations(ast.parse(source)), source

    @pytest.mark.parametrize(
        ("source", "shape"),
        [
            ('def f(language: str = "fr") -> None: ...', "1"),
            ('x = user.language or "fr"', "2"),
            ('x = lang or f"{DEFAULT_LANGUAGE}"', "2"),
            ("x = lang or f\"{'fr'}\"", "2"),
            ('x = state.get("user_language", "fr")', "3"),
            ('x = getattr(user, "language", "en")', "4"),
            ('x = lang if lang else "fr"', "5"),
            ('def f():\n    lang = "fr"', "6"),
            ('def f():\n    return {"user_language": "fr"}', "6"),
            ('send(text, language="fr")', "7"),
            ('_DEFAULT = "en"', "8"),
            ('MESSAGE = MESSAGES["fr"]', "9"),
            ('fallback_languages = (settings.default_language, "en")', "10"),
            ('def f(lang):\n    for wanted in (lang, "en"):\n        pass', "11"),
            # Each witness of a predicate no probe held (review 12).
            ('language_ctx: ContextVar[str] = ContextVar("language", default="fr")', "1"),
            ('_lang_ctx: ContextVar[str] = ContextVar("lang", default="fr")', "1"),
            ('class M:\n    x: str = Field(default="fr")', "1"),
            # Only the class reading sees a class defined inside a function.
            ('def f():\n    class M:\n        x: str = Field(default="fr")', "1"),
            ('def f():\n    class M:\n        language: str = "fr"', "1"),
            ('def f(lang: str = Body("fr")) -> None: ...', "1"),
            ('def f(lang: str = Form("fr")) -> None: ...', "1"),
            ('def f(lang: str = Header("fr")) -> None: ...', "1"),
            ("def f(lang: str = _DEFAULT_LANGUAGE) -> None: ...", "1"),
            ('self.logger.info("x", language="fr")', "7"),
            ('logger.info("x", extra=dict(language="fr"))', "7"),
            # A fallback decides a language even inside a log call (review 13).
            ('logger.info("x", lang=user.language or "fr")', "2"),
            ('log.info("x", lang=prefs.get("language", "fr"))', "3"),
            ('logger.info("x", lang=getattr(user, "language", "fr"))', "4"),
            ('log.info("x", lang=user.language if user else "fr")', "5"),
            # Only ``logger`` and ``log`` name a log call: ``_logger`` is any call.
            ('_logger.info("x", language="fr")', "7"),
        ],
    )
    def test_each_shape_is_caught_by_its_own_predicate(self, source: str, shape: str) -> None:
        """Shape 10 reads every use of the default: asserting only that
        SOMETHING was flagged let it mask a predicate that stopped working — a
        literal in a language-keyed dict was then flagged by nothing (review 11)."""
        assert shape in {found for found, _node in _labelled(ast.parse(source))}, source

    @pytest.mark.parametrize(
        "source",
        [
            "def f(language: str | None = None) -> None: ...",
            'def f(language: str = "") -> None: ...',
            "x = resolve_language(user_language)",
            "x = language or resolve_language()",
            # A fallback entry read INSIDE a function is a read, not a pin.
            'def f():\n    x = table.get(lang, table["en"])',
            'if lang == "fr":\n    pass',
            'x = describe(rule, "fr") if lang == "fr" else None',
            'LANGS = ["fr", "en"]',
            'x = {"fr": "Bonjour", "en": "Hello"}',
            "class T:\n    locale: Mapped[str] = mapped_column(String(10))",
            # A table's one-language view inside a function is a read, not a pin.
            'def f():\n    known = set(LABELS["en"])',
            "class T:\n    language: Mapped[str] = mapped_column(String(10), default=lambda: x)",
            # A column's TYPE is not its default.
            'class T:\n    language = Column("language", String(10))',
            # Reading a language-keyed table's entry for a variable is a read.
            "GREETING = MESSAGES[lang]",
            'send(text, language=user.language or "")',
            'logger.warning("fallback", fallback_language=settings.default_language)',
            # An enum member is a value, not a default (round 4).
            'class Lang(StrEnum):\n    FR = "fr"\n    EN = "en"',
            # A description in an Annotated is no default (round 5).
            'def f(language: Annotated[str, "fr"]) -> None: ...',
            # A context variable named after a code declares nothing.
            '_x: ContextVar[str | None] = ContextVar("fr", default=None)',
            # A concatenation is computed; a slang is not a language.
            'x = lang or "f" + "r"',
            'send(text, slang="fr")',
            # A comparison tests a language; a vocabulary is a list of literals;
            # a type's tuple falls back to nothing (round 6).
            'if lang in (other, "fr"):\n    pass',
            'DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]',
            'x: dict[str, Annotated[str, "fr"]] = {}',
            'x = {"language": lang}',
            # A log line reports; a column's first argument is its NAME (review 12).
            'log.warning("x", language="fr")',
            'logger.info("x", extra={"user_language": "fr"})',
            'logger.info("x", chain=(lang, "en"))',
            'class T:\n    fr: Mapped[str] = mapped_column("fr", Text)',
        ],
    )
    def test_leaves_a_legitimate_shape_alone(self, source: str) -> None:
        assert _violations(ast.parse(source)) == [], source
