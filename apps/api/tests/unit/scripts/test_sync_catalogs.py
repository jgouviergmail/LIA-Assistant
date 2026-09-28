"""The catalog synchronisation follows the application's languages (ADR-323).

Its languages are the application's table, so a language added there must get a
catalog — the first version opened each ``.po`` unconditionally and stopped on
the new language's missing file. And the table itself agrees with the ``Language``
literal every other list of the supported languages derives from, or the import
stops.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polib
import pytest

from scripts.i18n import sync_catalogs
from src.core import i18n_types

pytestmark = pytest.mark.unit


def _save(catalog: polib.POFile, path: Path) -> None:
    """Write a catalog with LF endings on every platform — ``write_text`` and
    ``POFile.save`` write CRLF on Windows, so the fixtures started apart."""
    path.write_bytes(str(catalog).encode("utf-8"))


def _tree(root: Path, languages: tuple[str, ...]) -> None:
    """A locales tree holding a template and a catalog for ``languages`` only."""
    template = polib.POFile()
    template.metadata = {"Project-Id-Version": "LIA API 1.0", "Content-Type": "text/plain"}
    _save(template, root / "messages.pot")
    for language in languages:
        folder = root / language / "LC_MESSAGES"
        folder.mkdir(parents=True)
        _save(polib.POFile(), folder / "messages.po")


def test_a_language_with_no_catalog_gets_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path, ("en",))
    monkeypatch.setattr(sync_catalogs, "LOCALES", tmp_path)
    monkeypatch.setattr(sync_catalogs, "LANGUAGES", ("en", "de"))
    monkeypatch.setattr(sync_catalogs, "census", lambda: ({"Hello {name},": "core/x.py:1"}, []))

    assert sync_catalogs.main() == 0

    created = polib.pofile(str(tmp_path / "de" / "LC_MESSAGES" / "messages.po"))
    assert created.metadata["Language"] == "de"
    assert created.metadata["Project-Id-Version"] == "LIA API 1.0"
    assert [(entry.msgid, entry.msgstr) for entry in created] == [("Hello {name},", "")]
    assert (tmp_path / "de" / "LC_MESSAGES" / "messages.mo").exists()


def test_a_second_run_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Idempotent: the dates move only when the entries do."""
    _tree(tmp_path, ("en", "de"))
    monkeypatch.setattr(sync_catalogs, "LOCALES", tmp_path)
    monkeypatch.setattr(sync_catalogs, "LANGUAGES", ("en", "de"))
    monkeypatch.setattr(sync_catalogs, "census", lambda: ({"Hi": "core/x.py:1"}, []))
    assert sync_catalogs.main() == 0
    first = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.*"))}

    assert sync_catalogs.main() == 0

    assert {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.*"))} == first


def test_a_hand_translated_entry_moves_the_revision_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path, ("en", "de"))
    _sync(tmp_path, monkeypatch, {"Hi": "core/x.py:1"})
    assert sync_catalogs.main() == 0
    path = tmp_path / "de" / "LC_MESSAGES" / "messages.po"
    catalog = polib.pofile(str(path))
    catalog.metadata["PO-Revision-Date"] = "2000-01-01 00:00+0000"
    created = catalog.metadata["POT-Creation-Date"]
    catalog.find("Hi").msgstr = "Hallo"
    _save(catalog, path)
    # A later run: a date that moved can no longer pass for the same minute.
    monkeypatch.setattr(_Clock, "instant", datetime(2026, 9, 27, 4, 30, tzinfo=UTC))

    assert sync_catalogs.main() == 0

    saved = polib.pofile(str(path))
    assert saved.metadata["PO-Revision-Date"] != "2000-01-01 00:00+0000"
    # The entries did not change: only the revision moves.
    assert saved.metadata["POT-Creation-Date"] == created
    assert polib.mofile(str(path.with_suffix(".mo"))).find("Hi").msgstr == "Hallo"


def test_an_obsolete_entry_never_overrides_a_live_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path, ("en", "de"))
    path = tmp_path / "de" / "LC_MESSAGES" / "messages.po"
    catalog = polib.POFile()
    catalog.append(polib.POEntry(msgid="Hi", msgstr="Hallo"))
    catalog.append(polib.POEntry(msgid="Hi", msgstr="Servus", obsolete=True))
    _save(catalog, path)
    monkeypatch.setattr(sync_catalogs, "LOCALES", tmp_path)
    monkeypatch.setattr(sync_catalogs, "LANGUAGES", ("en", "de"))
    monkeypatch.setattr(sync_catalogs, "census", lambda: ({"Hi": "core/x.py:1"}, []))

    assert sync_catalogs.main() == 0

    assert polib.pofile(str(path)).find("Hi").msgstr == "Hallo"


def test_a_new_catalog_carries_its_language_s_plural_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path, ("en",))
    monkeypatch.setattr(sync_catalogs, "LOCALES", tmp_path)
    monkeypatch.setattr(sync_catalogs, "LANGUAGES", ("en", "zh-CN"))
    monkeypatch.setattr(sync_catalogs, "census", lambda: ({"Hi": "core/x.py:1"}, []))

    assert sync_catalogs.main() == 0

    created = polib.pofile(str(tmp_path / "zh-CN" / "LC_MESSAGES" / "messages.po"))
    assert created.metadata["Plural-Forms"] == "nplurals=1; plural=0"


def test_every_language_has_its_plural_rule() -> None:
    """A new catalog is headed with its language's rule: none is guessed."""
    assert set(sync_catalogs.PLURAL_FORMS) == set(sync_catalogs.LANGUAGES)


def test_every_supported_language_is_its_own_canonical_code() -> None:
    """The chokepoint maps each declared code to itself: a regional code other
    than Chinese's, added to the literal, would name no language at all."""
    from src.core.constants import SUPPORTED_LANGUAGES

    assert SUPPORTED_LANGUAGES
    assert {code: i18n_types.canonical_language(code) for code in SUPPORTED_LANGUAGES} == {
        code: code for code in SUPPORTED_LANGUAGES
    }


def test_a_declaration_that_disagrees_stops_the_import(monkeypatch: pytest.MonkeyPatch) -> None:
    names = {code: name for code, name in i18n_types.LANGUAGE_NAMES.items() if code != "it"}
    monkeypatch.setattr(i18n_types, "LANGUAGE_NAMES", names)

    with pytest.raises(RuntimeError, match="LANGUAGE_NAMES"):
        i18n_types._assert_one_vocabulary()


class _Clock:
    """A ``datetime`` stand-in whose ``now`` answers a fixed instant."""

    instant = datetime(2026, 9, 26, 3, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz: object = None) -> datetime:
        return cls.instant


def _sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, msgids: dict[str, str]) -> None:
    monkeypatch.setattr(sync_catalogs, "LOCALES", tmp_path)
    monkeypatch.setattr(sync_catalogs, "LANGUAGES", ("en", "de"))
    monkeypatch.setattr(sync_catalogs, "census", lambda: (msgids, []))
    monkeypatch.setattr(sync_catalogs, "datetime", _Clock)


def test_a_later_run_with_nothing_new_moves_no_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both runs of the first idempotence test fall in one minute; this one does not."""
    _tree(tmp_path, ("en", "de"))
    _sync(tmp_path, monkeypatch, {"Hi": "core/x.py:1"})
    assert sync_catalogs.main() == 0
    first = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.*"))}

    monkeypatch.setattr(_Clock, "instant", datetime(2026, 9, 27, 4, 30, tzinfo=UTC))
    assert sync_catalogs.main() == 0

    assert {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.*"))} == first


def test_a_crlf_catalog_stays_crlf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _tree(tmp_path, ("en", "de"))
    path = tmp_path / "de" / "LC_MESSAGES" / "messages.po"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    _sync(tmp_path, monkeypatch, {"Hi": "core/x.py:1"})

    assert sync_catalogs.main() == 0

    written = path.read_bytes()
    assert b"\r\n" in written and b"\n" not in written.replace(b"\r\n", b"")


def test_english_is_its_own_msgid_and_a_dropped_msgid_leaves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path, ("en", "de"))
    path = tmp_path / "de" / "LC_MESSAGES" / "messages.po"
    catalog = polib.POFile()
    catalog.append(polib.POEntry(msgid="Gone", msgstr="Weg"))
    _save(catalog, path)
    _sync(tmp_path, monkeypatch, {"Hi": "core/x.py:1"})

    assert sync_catalogs.main() == 0

    english = polib.pofile(str(tmp_path / "en" / "LC_MESSAGES" / "messages.po"))
    assert [(entry.msgid, entry.msgstr) for entry in english] == [("Hi", "Hi")]
    assert [entry.msgid for entry in polib.pofile(str(path))] == ["Hi"]


def test_a_new_catalog_takes_its_template_s_line_ending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path, ("en",))
    template = tmp_path / "messages.pot"
    template.write_bytes(template.read_bytes().replace(b"\n", b"\r\n"))
    _sync(tmp_path, monkeypatch, {"Hi": "core/x.py:1"})

    assert sync_catalogs.main() == 0

    created = (tmp_path / "de" / "LC_MESSAGES" / "messages.po").read_bytes()
    assert b"\r\n" in created and b"\n" not in created.replace(b"\r\n", b"")


def test_a_fuzzy_translation_moves_no_date_on_a_later_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Never compiled, a fuzzy translation must not read as a hand edit on every
    run — and it is listed for review."""
    _tree(tmp_path, ("en", "de"))
    catalog = polib.POFile()
    catalog.append(polib.POEntry(msgid="Hi", msgstr="Hallo", flags=["fuzzy"]))
    _save(catalog, tmp_path / "de" / "LC_MESSAGES" / "messages.po")
    _sync(tmp_path, monkeypatch, {"Hi": "core/x.py:1"})
    assert sync_catalogs.main() == 0
    first = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.*"))}
    capsys.readouterr()

    monkeypatch.setattr(_Clock, "instant", datetime(2026, 9, 27, 4, 30, tzinfo=UTC))
    assert sync_catalogs.main() == 0

    assert {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.*"))} == first
    printed = capsys.readouterr().out
    assert "de: 1 msgids, complete, 1 fuzzy to review" in printed
    assert "core/x.py:1  'Hi'" in printed


def test_a_catalog_never_compiled_is_compiled_and_dated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path, ("en", "de"))
    _sync(tmp_path, monkeypatch, {"Hi": "core/x.py:1"})
    assert sync_catalogs.main() == 0
    path = tmp_path / "de" / "LC_MESSAGES" / "messages.po"
    catalog = polib.pofile(str(path))
    catalog.find("Hi").msgstr = "Hallo"
    catalog.metadata["PO-Revision-Date"] = "2000-01-01 00:00+0000"
    _save(catalog, path)
    path.with_suffix(".mo").unlink()

    assert sync_catalogs.main() == 0

    assert polib.pofile(str(path)).metadata["PO-Revision-Date"] != "2000-01-01 00:00+0000"
    assert polib.mofile(str(path.with_suffix(".mo"))).find("Hi").msgstr == "Hallo"


def test_a_computed_msgid_stops_the_run_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path, ("en", "de"))
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.*"))}
    _sync(tmp_path, monkeypatch, {"Hi": "core/x.py:1"})
    monkeypatch.setattr(sync_catalogs, "census", lambda: ({"Hi": "core/x.py:1"}, ["core/y.py:3"]))

    assert sync_catalogs.main() == 1

    assert {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.*"))} == before


def test_a_language_without_a_plural_rule_stops_the_run_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It stopped on a ``KeyError`` once the template and the earlier catalogs
    were already written."""
    _tree(tmp_path, ("en",))
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.*"))}
    _sync(tmp_path, monkeypatch, {"Hi": "core/x.py:1"})
    monkeypatch.setattr(sync_catalogs, "LANGUAGES", ("en", "pt"))

    assert sync_catalogs.main() == 1

    assert {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.*"))} == before


def test_a_kept_entry_keeps_its_references_and_comments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a translator or the extraction wrote beside a msgid still named stays."""
    _tree(tmp_path, ("en", "de"))
    path = tmp_path / "de" / "LC_MESSAGES" / "messages.po"
    catalog = polib.POFile()
    catalog.append(
        polib.POEntry(
            msgid="Hi",
            msgstr="Hallo",
            occurrences=[("src/core/x.py", "12")],
            comment="Shown on the welcome card.",
            tcomment="Informal greeting, du form.",
        )
    )
    _save(catalog, path)
    _sync(tmp_path, monkeypatch, {"Hi": "core/x.py:1"})

    assert sync_catalogs.main() == 0

    kept = polib.pofile(str(path)).find("Hi")
    assert (kept.msgstr, kept.occurrences, kept.comment, kept.tcomment) == (
        "Hallo",
        [("src/core/x.py", "12")],
        "Shown on the welcome card.",
        "Informal greeting, du form.",
    )


def test_every_entry_left_to_translate_is_printed_with_its_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _tree(tmp_path, ("en", "de"))
    _sync(tmp_path, monkeypatch, {"Hi": "core/x.py:1", "Bye": "core/y.py:7"})

    assert sync_catalogs.main() == 0

    printed = capsys.readouterr().out
    assert "de: 2 msgids, 2 to translate" in printed
    assert "core/x.py:1  'Hi'" in printed
    assert "core/y.py:7  'Bye'" in printed
