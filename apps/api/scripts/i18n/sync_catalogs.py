"""Keep the gettext catalogs equal to what the code names (ADR-323).

``tests/unit/test_gettext_catalog_guard.py`` refuses a catalog missing a msgid
the code names, or holding one nobody names — ``_()`` answers an unknown msgid
with the msgid itself, so an untranslated sentence fails nothing and simply
goes out in English. This script makes the catalogs equal to the code. It reads
every literal ``_("…")`` call bound to ``core.i18n`` — the very census the guard
runs, imported from here — then:

1. rewrites ``locales/messages.pot`` with exactly those msgids;
2. in each ``locales/<lang>/LC_MESSAGES/messages.po`` — one per language of the
   application's table, created when a language has none yet — keeps the
   translation of every msgid still named (with its comments and flags; an
   obsolete ``#~`` entry is never read back), adds the new ones — English
   translated to the msgid itself, every other language EMPTY — and drops the
   ones nobody names. No source reference is added — the census's
   ``path:line`` is PRINTED for every entry left to translate — and one a
   translator wrote is kept;
3. compiles every ``.mo`` from its ``.po`` (the runtime reads the ``.mo``).

A catalog whose entries do not change keeps its dates: a run that changes
nothing leaves every file as it was. A translation edited by hand since the
last compilation moves ``PO-Revision-Date`` when the run compiles it.

Then translate the empty entries it lists — in the application's register (tu,
du, tú, tu, 你), with French typography (a no-break space before « : ? ! »),
Chinese full-width punctuation, and each language's own marks around a quoted
value: « X » in French (no-break spaces inside), „X“ in German, «X» in Spanish
and Italian, “X” in Chinese — and run it again to compile what was written.
The guard fails while any entry is empty or still marked fuzzy.

Run from ``apps/api``::

    .venv/Scripts/python scripts/i18n/sync_catalogs.py   # Windows
    .venv/bin/python scripts/i18n/sync_catalogs.py       # Linux / macOS
"""

from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime
from pathlib import Path

import polib

API_ROOT = Path(__file__).resolve().parents[2]
SRC = API_ROOT / "src"
LOCALES = API_ROOT / "locales"
# Run as a script, ``src`` is not importable yet; imported (by the catalog
# guard), it already is — and an import must not reorder anyone's path.
if __name__ == "__main__" and str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.core.i18n_types import LANGUAGE_NAMES  # noqa: E402 - settings-free module

#: The catalogs' directories: the backend-canonical codes (``zh-CN``), read from
#: the application's own table — a second list would miss a language added there.
LANGUAGES: tuple[str, ...] = tuple(LANGUAGE_NAMES)
SOURCE_LANGUAGE = "en"
WRAP_WIDTH = 78
#: The plural rule a NEW catalog is created with — the existing six carry theirs.
#: One per language of the application: a language added there without its
#: rule stops the run before anything is written, never guessed.
PLURAL_FORMS: dict[str, str] = {
    "fr": "nplurals=2; plural=(n > 1)",
    "en": "nplurals=2; plural=(n != 1)",
    "es": "nplurals=2; plural=(n != 1)",
    "de": "nplurals=2; plural=(n != 1)",
    "it": "nplurals=2; plural=(n != 1)",
    "zh-CN": "nplurals=1; plural=0",
}


def gettext_names(tree: ast.Module, rel: str) -> set[str]:
    """Local names bound to ``core.i18n._`` in a module (aliases included).

    Args:
        tree: The module's AST.
        rel: The module's path under ``src/``.

    Returns:
        The names a call to gettext goes through in that module.
    """
    names = {"_"} if rel == "core/i18n.py" else set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.core.i18n":
            names.update(alias.asname or alias.name for alias in node.names if alias.name == "_")
    return names


def census(src: Path = SRC) -> tuple[dict[str, str], list[str]]:
    """Every msgid a ``_()`` call names, and every call that names none literally.

    Args:
        src: The source tree to read.

    Returns:
        ``(msgids, computed)`` — each msgid with the ``path:line`` of its first
        call (files in sorted order), and the calls whose msgid is computed.
    """
    msgids: dict[str, str] = {}
    computed: list[str] = []
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(src).as_posix()
        bound = gettext_names(tree, rel)
        if not bound:
            continue
        calls = sorted(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in bound
            ),
            key=lambda node: (node.lineno, node.col_offset),
        )
        for node in calls:
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                msgids.setdefault(first.value, f"{rel}:{node.lineno}")
            else:
                computed.append(f"{rel}:{node.lineno}")
    return msgids, computed


def _write(path: Path, catalog: polib.POFile, like: Path | None = None) -> None:
    """Save a catalog with the line ending the file — or, new, its sibling ``like`` — has."""
    model = path if path.exists() else like
    crlf = model is not None and model.exists() and b"\r\n" in model.read_bytes()
    body = str(catalog).replace("\r\n", "\n")
    path.write_bytes((body.replace("\n", "\r\n") if crlf else body).encode("utf-8"))


def _signature(catalog: polib.POFile) -> list[tuple[object, ...]]:
    """What a catalog says, entry by entry — its dates excluded."""
    return [
        (e.msgid, e.msgstr, e.comment, e.tcomment, tuple(e.flags), tuple(e.occurrences))
        for e in catalog
    ]


def _rebuilt(old: polib.POFile, msgids: list[str], translate: bool, stamp: str) -> polib.POFile:
    """``old`` holding exactly ``msgids``, each kept entry whole.

    A kept entry keeps its translation, its comments (extracted and
    translator's), its flags — a ``fuzzy`` translation stays marked, so the
    guard still refuses it — and its references. The dates move only when the
    entries do.

    Args:
        old: The catalog as it is on disk.
        msgids: The msgids the code names, in census order.
        translate: False for the template, whose translations stay empty.
        stamp: The creation / revision date to write when the entries change.

    Returns:
        The rebuilt catalog.
    """
    # An obsolete ``#~`` entry sharing a live msgid must never override it.
    kept = {entry.msgid: entry for entry in old if not entry.obsolete}
    new = polib.POFile(wrapwidth=WRAP_WIDTH)
    new.header = old.header
    new.metadata = dict(old.metadata)
    if not translate:
        new.metadata_is_fuzzy = True
    for msgid in msgids:
        previous = kept.get(msgid)
        new.append(
            polib.POEntry(
                msgid=msgid,
                msgstr=previous.msgstr if previous and translate else "",
                comment=previous.comment if previous else "",
                tcomment=previous.tcomment if previous else "",
                flags=list(previous.flags) if previous else [],
                occurrences=list(previous.occurrences) if previous else [],
            )
        )
    if _signature(new) != _signature(old):
        new.metadata["POT-Creation-Date"] = stamp
        if translate:
            new.metadata["PO-Revision-Date"] = stamp
    return new


def _new_catalog(language: str, template: polib.POFile) -> polib.POFile:
    """An empty catalog for a language that has none yet, headed like the template.

    Args:
        language: The backend-canonical code (``zh-CN``).
        template: The template, whose project metadata the catalog copies.

    Returns:
        A catalog holding no entry, for ``_rebuilt`` to fill.
    """
    catalog = polib.POFile(wrapwidth=WRAP_WIDTH)
    catalog.header = f"{LANGUAGE_NAMES[language]} translations for LIA API"
    catalog.metadata = {
        "Project-Id-Version": template.metadata.get("Project-Id-Version", "LIA API"),
        "Language-Team": LANGUAGE_NAMES[language],
        "Language": language,
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
        "Plural-Forms": PLURAL_FORMS[language],
    }
    return catalog


def _compiled_differs(catalog: polib.POFile, mo_path: Path) -> bool:
    """Whether the translations differ from what was last compiled — a hand edit."""
    if not mo_path.exists():
        return True
    compiled = {e.msgid: e.msgstr for e in polib.mofile(str(mo_path)) if e.msgid}
    written = {e.msgid: e.msgstr for e in catalog if e.msgstr and not e.fuzzy}
    return compiled != written


def _catalog_of(language: str, template: polib.POFile) -> tuple[Path, polib.POFile]:
    """A language's catalog path and content — an empty catalog when it has none yet."""
    path = LOCALES / language / "LC_MESSAGES" / "messages.po"
    if path.exists():
        return path, polib.pofile(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path, _new_catalog(language, template)


def _untranslated(catalog: polib.POFile, language: str) -> list[str]:
    """The msgids left to translate; English's empty entries become their msgid.

    Args:
        catalog: The rebuilt catalog — the source language's is filled in place.
        language: The catalog's language.

    Returns:
        The msgids whose translation is empty, in catalog order.
    """
    missing: list[str] = []
    for entry in catalog:
        if entry.msgstr:
            continue
        if language == SOURCE_LANGUAGE:
            entry.msgstr = entry.msgid
        else:
            missing.append(entry.msgid)
    return missing


def _date(catalog: polib.POFile, old: polib.POFile, path: Path, stamp: str) -> None:
    """Move a catalog's dates when its entries — or its compiled words — changed."""
    if _signature(catalog) != _signature(old):
        # English fills its new entries AFTER the rebuild compared them.
        catalog.metadata["POT-Creation-Date"] = stamp
        catalog.metadata["PO-Revision-Date"] = stamp
    elif _compiled_differs(catalog, path.with_suffix(".mo")):
        # A translator's hand edit: the catalog is the same shape, its words
        # are not what the runtime reads yet.
        catalog.metadata["PO-Revision-Date"] = stamp


def _report(
    language: str, catalog: polib.POFile, missing: list[str], msgids: dict[str, str]
) -> None:
    """Print a catalog's state and the ``path:line`` of every entry left to do."""
    fuzzy = [entry.msgid for entry in catalog if entry.fuzzy]
    status = f"{len(missing)} to translate" if missing else "complete"
    if fuzzy:
        status += f", {len(fuzzy)} fuzzy to review"
    print(f"{language}: {len(catalog)} msgids, {status}")
    for msgid in [*missing, *fuzzy]:
        print(f"    {msgids[msgid]}  {msgid!r}")


def main() -> int:
    """Synchronise the template, every language's catalog and their compiled forms.

    Returns:
        The process exit code: 1 when a msgid is computed (it cannot be
        catalogued) or a language has no plural rule (none is guessed) — both
        before anything is written —, 0 otherwise.
    """
    unruled = [language for language in LANGUAGES if language not in PLURAL_FORMS]
    if unruled:
        print("A language has no plural rule — declare it in PLURAL_FORMS:", *unruled, sep="\n  ")
        return 1
    msgids, computed = census()
    if computed:
        print("A computed msgid cannot be catalogued — name it literally:", *computed, sep="\n  ")
        return 1
    order = list(msgids)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M+0000")

    template_path = LOCALES / "messages.pot"
    template = polib.pofile(str(template_path))
    _write(template_path, _rebuilt(template, order, False, stamp))

    for language in LANGUAGES:
        path, old = _catalog_of(language, template)
        catalog = _rebuilt(old, order, True, stamp)
        missing = _untranslated(catalog, language)
        _date(catalog, old, path, stamp)
        _write(path, catalog, like=template_path)
        catalog.save_as_mofile(str(path.with_suffix(".mo")))
        _report(language, catalog, missing, msgids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
