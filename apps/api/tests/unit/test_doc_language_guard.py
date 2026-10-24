"""Guard: no NEW document is written in French; the French list only shrinks (AC-039a).

Why
---
``CLAUDE.md`` required every document in English while a third of the corpus was
French: the V14 revision (run R22, 2026-10-22) counted 284 of 833 tracked Markdown
documents mostly in French, entry points included. The rule had been adopted after
the corpus existed, with no transition rule and no instrument, so nothing told a
contributor which rule held. The owner amended it on 2026-10-22: a new document is
written in English, an existing French document may still be edited in French, and
the list of French documents is frozen by a shrink-only ratchet. Living maps, dated
plans and audit reports are exempt by decision.

``scripts/audit/doc_language.py`` is that ratchet. These tests prove the detector on
labelled samples, the corpus and its exemptions, every transition of the baseline on
a synthetic repository, and the real repository's verdict.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests._git_sandbox import isolate_from_the_running_repository
from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
AUDIT_DIR = REPO_ROOT / "scripts" / "audit"
SCRIPT_PATH = AUDIT_DIR / "doc_language.py"

pytestmark = pytest.mark.unit

_MODULE_NAME = "_lia_audit_doc_language"


def _load_module() -> ModuleType:
    # The script imports its sibling ``doc_audit`` by name, exactly as it does when
    # it runs from scripts/audit/ (where Python puts the script's directory first
    # on the path). Out of tree, the directory joins the path before it executes.
    if str(AUDIT_DIR) not in sys.path:
        sys.path.insert(0, str(AUDIT_DIR))
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


language = _load_module()


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """``tracked_paths`` runs git: a hook's repository must never answer for a test's."""
    isolate_from_the_running_repository(monkeypatch)


FRENCH = (
    "Le registre des constats est la seule source pour les audits, et chaque rapport "
    "doit le suivre dans le dépôt. Il ne faut pas que les identifiants changent.\n"
) * 4
ENGLISH = (
    "The register of findings is the only source for the audits, and each report "
    "must follow it in the repository. It is not something that changes.\n"
) * 4


def _baseline(root: Path, documents: list[str]) -> None:
    path = root / language.BASELINE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_doc": "Synthetic baseline.", "documents": documents}), encoding="utf-8"
    )


def _doc(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestDetection:
    def test_french_prose_is_french_and_english_prose_is_not(self) -> None:
        assert language.Verdict("f.md", *language.measure(FRENCH)).is_french
        assert not language.Verdict("e.md", *language.measure(ENGLISH)).is_french

    def test_code_and_link_targets_never_count(self) -> None:
        one_line = FRENCH.splitlines()[0]
        fenced = ENGLISH + "\n```text\n" + FRENCH + "```\n" + "`" + one_line + "`\n"
        linked = ENGLISH + "[the guide](docs/le-guide-des-tests-pour-les-et-des.md)\n"
        assert language.measure(fenced) == language.measure(ENGLISH)
        assert language.measure(linked)[0] == language.measure(ENGLISH)[0]

    def test_elided_function_words_are_counted(self) -> None:
        french, _english = language.measure("qu'il d'un l'application jusqu’à")
        assert french == 2  # il, un — « à » and the nouns are not function words

    def test_a_short_document_is_never_classified(self) -> None:
        verdict = language.Verdict("s.md", *language.measure("Le guide des tests."))
        assert not verdict.classified and not verdict.is_french

    def test_the_threshold_is_the_published_share(self) -> None:
        half = language.Verdict("m.md", 20, 20)
        below = language.Verdict("m.md", 19, 21)
        assert half.share == language.FRENCH_SHARE and half.is_french
        assert not below.is_french


class TestCorpus:
    @pytest.mark.parametrize(
        "rel",
        [
            "docs/maps/functional.md",
            "docs/superpowers/plans/2026-10-23-a-plan.md",
            "docs/audit/README.md",
            "apps/web/src/data/guides/how.fr.md",
            "apps/web/src/data/guides/why.zh.md",
        ],
    )
    def test_an_exempt_document_is_outside_the_corpus(self, tmp_path: Path, rel: str) -> None:
        _doc(tmp_path, rel, FRENCH)
        assert language.exemption_for(rel)
        assert rel not in language.corpus(tmp_path)

    def test_every_other_markdown_document_is_in_the_corpus(self, tmp_path: Path) -> None:
        for rel in ("README.md", "docs/guides/GUIDE.md", "docs/superpowers/specs/s.md"):
            _doc(tmp_path, rel, ENGLISH)
        _doc(tmp_path, "node_modules/pkg/README.md", FRENCH)
        assert language.corpus(tmp_path) == [
            "README.md",
            "docs/guides/GUIDE.md",
            "docs/superpowers/specs/s.md",
        ]


class TestRatchet:
    def test_a_new_french_document_is_refused(self, tmp_path: Path) -> None:
        _doc(tmp_path, "docs/kept.md", FRENCH)
        _doc(tmp_path, "docs/new.md", FRENCH)
        _baseline(tmp_path, ["docs/kept.md"])
        outcome = language.check(tmp_path)
        assert [v.path for v in outcome.new_french] == ["docs/new.md"]
        assert outcome.stale == ()

    def test_a_frozen_french_document_may_still_be_edited_in_french(self, tmp_path: Path) -> None:
        _doc(tmp_path, "docs/kept.md", FRENCH + FRENCH)
        _baseline(tmp_path, ["docs/kept.md"])
        outcome = language.check(tmp_path)
        assert outcome.new_french == () and outcome.stale == ()

    def test_a_translated_or_deleted_document_must_leave_the_list(self, tmp_path: Path) -> None:
        _doc(tmp_path, "docs/translated.md", ENGLISH)
        _doc(tmp_path, "docs/kept.md", FRENCH)
        _baseline(tmp_path, ["docs/gone.md", "docs/kept.md", "docs/translated.md"])
        outcome = language.check(tmp_path)
        assert [path for path, _reason in outcome.stale] == ["docs/gone.md", "docs/translated.md"]

        removed = language.update(tmp_path)

        assert removed == ["docs/gone.md", "docs/translated.md"]
        assert language.load_baseline(tmp_path) == frozenset({"docs/kept.md"})
        assert language.check(tmp_path).stale == ()

    def test_the_rewritten_baseline_keeps_unix_line_endings(self, tmp_path: Path) -> None:
        """The file is declared ``eol=lf``: a Windows rewrite must not turn it into CRLF."""
        _doc(tmp_path, "docs/kept.md", FRENCH)
        _baseline(tmp_path, ["docs/gone.md", "docs/kept.md"])

        language.update(tmp_path)

        assert b"\r\n" not in (tmp_path / language.BASELINE_REL).read_bytes()

    def test_the_update_never_adds_a_document(self, tmp_path: Path) -> None:
        _doc(tmp_path, "docs/new.md", FRENCH)
        _baseline(tmp_path, [])
        assert language.update(tmp_path) == []
        assert language.load_baseline(tmp_path) == frozenset()
        assert [v.path for v in language.check(tmp_path).new_french] == ["docs/new.md"]

    def test_a_moved_french_document_keeps_its_entry_on_request(self, tmp_path: Path) -> None:
        _doc(tmp_path, "docs/moved/kept.md", FRENCH)
        _baseline(tmp_path, ["docs/kept.md"])
        language.update(tmp_path, rename=("docs/kept.md", "docs/moved/kept.md"))
        assert language.load_baseline(tmp_path) == frozenset({"docs/moved/kept.md"})
        outcome = language.check(tmp_path)
        assert outcome.new_french == () and outcome.stale == ()

    @pytest.mark.parametrize(
        ("old", "new"),
        [
            ("docs/unknown.md", "docs/moved/kept.md"),
            ("docs/kept.md", "docs/english.md"),
            ("docs/kept.md", "docs/missing.md"),
            ("docs/still-here.md", "docs/moved/kept.md"),
        ],
        ids=["old-not-frozen", "new-not-french", "new-missing", "old-still-exists"],
    )
    def test_a_rename_that_is_not_a_move_is_refused(
        self, tmp_path: Path, old: str, new: str
    ) -> None:
        _doc(tmp_path, "docs/moved/kept.md", FRENCH)
        _doc(tmp_path, "docs/english.md", ENGLISH)
        _doc(tmp_path, "docs/still-here.md", FRENCH)
        _baseline(tmp_path, ["docs/kept.md", "docs/still-here.md"])
        before = language.load_baseline(tmp_path)
        with pytest.raises(ValueError):
            language.update(tmp_path, rename=(old, new))
        assert language.load_baseline(tmp_path) == before


class TestTheRealRepository:
    def test_no_new_french_document_and_no_stale_entry(self) -> None:
        outcome = language.check(REPO_ROOT)
        assert (
            outcome.new_french == ()
        ), "Write these documents in English (CLAUDE.md, documentation language): " + ", ".join(
            f"{v.path} ({v.share:.2f})" for v in outcome.new_french
        )
        assert outcome.stale == (), "Run `task docs:language:update`: " + ", ".join(
            f"{path} ({reason})" for path, reason in outcome.stale
        )

    def test_the_baseline_is_sorted_and_unique(self) -> None:
        data = json.loads((REPO_ROOT / language.BASELINE_REL).read_text(encoding="utf-8"))
        documents = data["documents"]
        assert documents == sorted(set(documents))

    def test_the_entry_points_awaiting_translation_are_frozen(self) -> None:
        """AC-039b translates them in a lot of its own; until then they are listed."""
        frozen = language.load_baseline(REPO_ROOT)
        for entry_point in ("docs/INDEX.md", "docs/ARCHITECTURE.md"):
            assert entry_point in frozen


class TestCommandLine:
    def test_the_check_fails_on_a_new_french_document(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _doc(tmp_path, "docs/new.md", FRENCH)
        _baseline(tmp_path, [])
        assert language.main([str(tmp_path)]) == 1
        assert "docs/new.md" in capsys.readouterr().out

    def test_a_clean_repository_passes(self, tmp_path: Path) -> None:
        _doc(tmp_path, "docs/english.md", ENGLISH)
        _baseline(tmp_path, [])
        assert language.main([str(tmp_path)]) == 0

    def test_a_stale_entry_fails_until_the_update_removes_it(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _doc(tmp_path, "docs/translated.md", ENGLISH)
        _baseline(tmp_path, ["docs/translated.md"])
        assert language.main([str(tmp_path)]) == 1
        assert "docs/translated.md" in capsys.readouterr().out
        assert language.main([str(tmp_path), "--update"]) == 0

    def test_a_rename_needs_the_update_mode(self, tmp_path: Path) -> None:
        _baseline(tmp_path, [])
        with pytest.raises(SystemExit):
            language.main([str(tmp_path), "--rename", "a.md", "b.md"])
