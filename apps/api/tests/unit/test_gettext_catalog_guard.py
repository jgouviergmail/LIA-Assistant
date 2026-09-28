"""Guard: the six gettext catalogs hold exactly what the code names, translated (ADR-323).

``_()`` (``core.i18n``) answers an unknown msgid with the msgid itself, so an
untranslated sentence fails nothing: it simply goes out in English. Measured on
the last release before the rebuild (4f19469b), with this guard's own census:
the code named 112 msgids; 21 of them were translated in no catalog, 14 more —
the whole e-mail verification and password reset e-mails — in French alone
(de/es/it/zh-CN received those e-mails in English), and every catalog carried
76 entries nothing read.

Rules, over every ``src/**/*.py`` and ``locales/``:

1. every ``_()`` call bound to ``core.i18n`` names its msgid LITERALLY — a
   computed msgid cannot be checked against a catalog;
2. each language's catalog and the template hold exactly the msgids named — a
   missing entry is an untranslated sentence, an extra one a sentence nobody
   reads;
3. every translation is non-empty and keeps its msgid's ``{placeholders}``;
   English translates to the msgid itself;
4. the compiled ``.mo`` — what the runtime reads — says what its ``.po`` — what
   a reviewer reads — says;
5. the Chinese catalog addresses the reader as 你, the application's register
   (the other languages' register is reviewed, never pattern-matched);
6. nothing escapes the census: no call through an imported module
   (``i18n._("…")``, ``src.core.i18n._("…")`` — a method of one's own called
   ``_`` is no module's), no ``getattr(…, "_")`` nor a lookup read through
   ``getattr``, no ``_`` or module ``._`` handed around uncalled, no call or
   uncalled read of a translator lookup (every ``*gettext`` name the ``gettext``
   module and its translations class define, read from the module itself)
   outside ``core/i18n.py``, no lookup imported from the ``gettext`` module there, no
   ``_`` imported from anywhere but ``src.core.i18n`` (a relative import or a
   re-export is invisible to the census), and a module that binds ``_`` to
   gettext never reuses the name — not as a throwaway (``a, _ = pair`` makes
   ``_`` local to the whole function: a later ``_("…")`` there raises), a
   parameter, a lambda's argument, an ``except … as _``, a ``def``/``class``, or
   a second import.
"""

from __future__ import annotations

import ast
import functools
import gettext
import string

import polib
import pytest

from scripts.i18n.sync_catalogs import census, gettext_names
from src.core.i18n_types import LANGUAGE_NAMES
from tests._repo_paths import find_apps_api_root

pytestmark = pytest.mark.unit

API_ROOT = find_apps_api_root()
SRC = API_ROOT / "src"
LOCALES = API_ROOT / "locales"
LANGUAGES: tuple[str, ...] = tuple(LANGUAGE_NAMES)


#: The translator's lookup methods: a call to one outside ``core/i18n.py`` is a
#: sentence the census never sees. Read from ``gettext`` itself — module and
#: translations class — so a lookup a Python release adds (``dpgettext`` and
#: ``dnpgettext`` arrived after the first list was typed) is covered by construction.
_LOOKUPS: frozenset[str] = frozenset(
    name
    for name in (*dir(gettext), *dir(gettext.NullTranslations))
    if name.endswith("gettext") and not name.startswith("_")
)


def _imported_names(tree: ast.Module) -> set[str]:
    """The names a module's imports bind (``import a.b`` binds ``a``)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _root_name(node: ast.expr) -> str | None:
    """``i18n`` for ``i18n._``, ``src`` for ``src.core.i18n._``."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _escapes(tree: ast.Module, rel: str) -> list[str]:
    """Every way a sentence reaches gettext outside the census's view."""
    found: list[str] = []
    bound = gettext_names(tree, rel)
    modules = _imported_names(tree)
    called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    for node in ast.walk(tree):
        found.extend(_name_escapes(node, rel, bound, called))
        found.extend(_rebinding_definitions(node, rel, bound, tree))
        if isinstance(node, ast.ImportFrom | ast.Import):
            found.extend(_foreign_underscore_imports(node, rel))
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            found.extend(_attribute_escapes(node, rel, modules, called))
        elif isinstance(node, ast.Call):
            found.extend(_getattr_escapes(node, rel))
    return found


def _name_escapes(node: ast.AST, rel: str, bound: set[str], called: set[int]) -> list[str]:
    """The door's name rebound, handed around uncalled, or reused as a parameter
    or an except clause's name."""
    if isinstance(node, ast.Name) and node.id in bound:
        if isinstance(node.ctx, ast.Store):
            return [f"{rel}:{node.lineno} rebinds {node.id}"]
        return [] if id(node) in called else [f"{rel}:{node.lineno} passes {node.id} uncalled"]
    if isinstance(node, ast.arg) and node.arg in bound:
        return [f"{rel}:{node.lineno} rebinds {node.arg} as a parameter"]
    if isinstance(node, ast.ExceptHandler) and node.name in bound:
        return [f"{rel}:{node.lineno} rebinds {node.name} in an except clause"]
    return []


def _rebinding_definitions(node: ast.AST, rel: str, bound: set[str], tree: ast.Module) -> list[str]:
    """A ``def`` or ``class`` named like the door — the door itself, core/i18n.py's
    module-level ``def _``, excepted."""
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return []
    door = rel == "core/i18n.py" and node.name == "_" and node in tree.body
    if node.name in bound and not door:
        return [f"{rel}:{node.lineno} rebinds {node.name} as a def or class"]
    return []


def _getattr_escapes(node: ast.Call, rel: str) -> list[str]:
    """``getattr(module, "_")`` or a translator lookup read through ``getattr``."""
    func = node.func
    if not isinstance(func, ast.Name):
        return []
    second = node.args[1] if func.id == "getattr" and len(node.args) > 1 else None
    name = second.value if isinstance(second, ast.Constant) else None
    if name == "_" or (name in _LOOKUPS and rel != "core/i18n.py"):
        return [f"{rel}:{node.lineno} reads {name} through getattr"]
    return []


def _attribute_escapes(
    node: ast.Attribute, rel: str, modules: set[str], called: set[int]
) -> list[str]:
    """A ``module._`` or a translator lookup, called or handed around."""
    how = "calls" if id(node) in called else "reads uncalled"
    if node.attr == "_" and _root_name(node.value) in modules:
        return [f"{rel}:{node.lineno} {how} ._ through a module"]
    if node.attr in _LOOKUPS and rel != "core/i18n.py":
        return [f"{rel}:{node.lineno} {how} .{node.attr}"]
    return []


def _foreign_underscore_imports(node: ast.Import | ast.ImportFrom, rel: str) -> list[str]:
    """An ``_`` bound by any import but ``from src.core.i18n import _`` — and, outside
    ``core/i18n.py``, a lookup imported from the ``gettext`` module itself."""
    if isinstance(node, ast.ImportFrom):
        module, level = node.module or "", node.level
    else:
        module, level = "", 0
    census_door = module == "src.core.i18n" and level == 0
    hits = []
    for alias in node.names:
        bound_as = alias.asname or alias.name
        if bound_as == "_" and not (census_door and alias.name == "_"):
            origin = module or alias.name
            hits.append(f"{rel}:{node.lineno} binds _ from {'.' * level}{origin}")
        elif module == "gettext" and alias.name in _LOOKUPS and rel != "core/i18n.py":
            hits.append(f"{rel}:{node.lineno} imports {alias.name} from gettext")
    return hits


@functools.cache
def _census() -> tuple[frozenset[str], tuple[str, ...]]:
    """ONE census: the synchronisation script's, so what it writes is what this checks.

    Run on first use, once: collecting this module must not scan ``src/`` for
    every worker that never runs these tests.

    Returns:
        ``(msgids, computed)`` — every msgid named, and every call naming none literally.
    """
    named, computed = census(SRC)
    return frozenset(named), tuple(computed)


#: The procedure a failure below points at.
SYNC = "run scripts/i18n/sync_catalogs.py from apps/api, translate what it lists, run it again"


def _fields(text: str) -> list[str]:
    """The ``{field}`` names of a format string, sorted."""
    return sorted(f for _lit, f, _spec, _conv in string.Formatter().parse(text) if f is not None)


def _catalog(language: str) -> polib.POFile:
    return polib.pofile(str(LOCALES / language / "LC_MESSAGES" / "messages.po"))


def test_census_finds_the_translated_sentences() -> None:
    """The scan is alive: it finds the e-mails' and the tools' sentences."""
    msgids, _computed = _census()
    assert "Your LIA account has been deactivated" in msgids
    assert "Hello {name}," in msgids
    assert len(msgids) > 100


def test_nothing_reaches_gettext_outside_the_census() -> None:
    escapes = [
        hit
        for path in sorted(SRC.rglob("*.py"))
        for hit in _escapes(
            ast.parse(path.read_text(encoding="utf-8")), path.relative_to(SRC).as_posix()
        )
    ]
    assert escapes == [], f"These sentences escape the catalog census: {escapes}"


@pytest.mark.parametrize(
    ("source", "caught"),
    [
        ('from src.core.i18n import _\nx = _("Hi")', False),
        ("from src.core.i18n import _\nfor _ in range(3):\n    pass", True),
        ('from src.core.i18n import _\ntexts = map(_, ["a"])', True),
        ('import src.core.i18n as i18n\nx = i18n._("Hi")', True),
        ('from src.core import i18n\nx = i18n._("Hi")', True),
        ('translator = get_translator("fr")\nx = translator.gettext("Hi")', True),
        # Shapes the guard claimed and missed (review of 2026-09-26).
        ('from src.core.i18n import _\ndef f(_):\n    return _("Hi")', True),
        ("from src.core.i18n import _\ntry:\n    pass\nexcept ValueError as _:\n    pass", True),
        ('from src.core.i18n import _\nf = lambda _: _("Hi")', True),
        ("from src.core.i18n import _\nfrom helpers import gettext_lazy as _", True),
        ('from ..core.i18n import _\nx = _("Hi")', True),
        ('from src.core.i18n_helpers import _\nx = _("Hi")', True),
        ('import src.core.i18n\nx = src.core.i18n._("Hi")', True),
        ('from src.core import i18n\nx = getattr(i18n, "_")("Hi")', True),
        ('translator = get_translator("fr")\nx = translator.pgettext("ctx", "Hi")', True),
        # A parameter named ``_`` in a module that never binds gettext is its own business.
        ("def route(_: User = Depends(current_user)):\n    return 1", False),
        # Shapes the guard claimed and missed (review of 2026-09-26, round 4).
        ("from src.core.i18n import _\ndef _(text):\n    return text", True),
        ("from src.core.i18n import _\nclass _:\n    pass", True),
        ('from src.core import i18n\ntranslate = i18n._\nx = translate("Hi")', True),
        ('translator = get_translator("fr")\nlookup = translator.gettext', True),
        ('from gettext import gettext\nx = gettext("Hi")', True),
        ('from gettext import ngettext as plural\nx = plural("a", "b", 2)', True),
        # Shapes the guard claimed and missed (review of 2026-09-26, round 5).
        ('from gettext import dpgettext\nx = dpgettext("messages", "ctx", "Hi")', True),
        ('import gettext\nx = gettext.dnpgettext("messages", "ctx", "a", "b", 2)', True),
        ('t = get_translator("fr")\nx = getattr(t, "gettext")("Hi")', True),
        # A method of one's own called ``_`` is no module's (round 4).
        ('class C:\n    def f(self):\n        return self._("x")', False),
        ("from gettext import NullTranslations\nt = NullTranslations()", False),
    ],
)
def test_the_escape_scan_reads_the_shapes(source: str, caught: bool) -> None:
    assert bool(_escapes(ast.parse(source), "probe.py")) is caught


def test_every_gettext_call_names_its_msgid_literally() -> None:
    _msgids, computed = _census()
    assert computed == (), (
        "A computed msgid cannot be checked against the catalogs — name it "
        f"literally: {list(computed)}"
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_catalog_holds_exactly_the_named_msgids(language: str) -> None:
    msgids, _computed = _census()
    held = {entry.msgid for entry in _catalog(language)}
    assert sorted(msgids - held) == [], f"{language}: named but not in the catalog — {SYNC}"
    assert sorted(held - msgids) == [], f"{language}: in the catalog, named nowhere — {SYNC}"


def test_template_holds_exactly_the_named_msgids() -> None:
    template = polib.pofile(str(LOCALES / "messages.pot"))
    assert {entry.msgid for entry in template} == _census()[0]
    assert all(entry.msgstr == "" for entry in template)


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_translation_is_whole(language: str) -> None:
    problems = []
    for entry in _catalog(language):
        if not entry.msgstr or entry.fuzzy or entry.obsolete:
            problems.append(f"untranslated: {entry.msgid!r}")
        elif _fields(entry.msgstr) != _fields(entry.msgid):
            problems.append(f"placeholders differ: {entry.msgid!r} -> {entry.msgstr!r}")
        elif language == "en" and entry.msgstr != entry.msgid:
            problems.append(f"English is the msgid itself: {entry.msgid!r}")
    assert problems == [], f"{problems} — {SYNC}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_compiled_catalog_says_what_its_source_says(language: str) -> None:
    source = {entry.msgid: entry.msgstr for entry in _catalog(language)}
    compiled = polib.mofile(str(LOCALES / language / "LC_MESSAGES" / "messages.mo"))
    assert {entry.msgid: entry.msgstr for entry in compiled} == source, SYNC
    # ...and the runtime reads it: gettext resolves every msgid through it.
    runtime = gettext.translation(
        "messages", localedir=str(LOCALES), languages=[language], fallback=False
    )
    assert {msgid: runtime.gettext(msgid) for msgid in source} == source


def test_chinese_addresses_the_reader_as_ni() -> None:
    formal = [entry.msgid for entry in _catalog("zh-CN") if "您" in entry.msgstr]
    assert formal == [], f"您 where the application says 你: {formal}"
