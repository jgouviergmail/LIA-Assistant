"""Guard: the audit findings register agrees with the reports it registers (AC-031).

Why
---
Until 2026-10-23 the register of audit findings lived only inside successive HTML
reports, and nothing checked that one report carried the previous one forward.
The revision of V14 measured the cost: three P0 findings of V13 still open after
86 releases, a V13 finding (AC-006) silently dropped by V14, and V14 reusing the
identifier AC-014 for another subject. Building the register on 2026-10-23 found
a wider drift the revision had not named: V11, V12 and V13 each numbered their
findings from AC-001 again, so the "stable identifiers since V11" the protocol
claimed never existed.

``docs/audit/findings_register.json`` is now the register, and
``scripts/audit/findings_register.py`` verifies it: its SHAPE first — the file is
edited by hand, and a typo must come back as a sentence, never as a traceback —
then every rule tying an entry to the cards of the reports and to its proofs.
These tests run that verification on the real register, independently of
today's date so a test never turns red because time passed, and prove each rule
on a synthetic repository, including the date-dependent deadline check the
release gate applies.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
SCRIPT_PATH = REPO_ROOT / "scripts" / "audit" / "findings_register.py"

pytestmark = pytest.mark.unit

#: Namespaced import name, registered in ``sys.modules`` BEFORE execution because
#: ``@dataclass`` resolves annotations through the module (same plumbing as the
#: doc_facts guard).
_MODULE_NAME = "_lia_audit_findings_register"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


register_tool = _load_module()

V13_REL = "docs/audit/AUDIT_CODEBASE_2026-08-02_CONSOLIDE_V13.html"
V14_REL = "docs/audit/AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14.html"
ADR_REL = "docs/architecture/ADR-001-Synthetic-Decision.md"


def _report_html(*articles: tuple[str, str]) -> str:
    body = "".join(
        f'<article class="finding" id="{aid}"><h3>{title}</h3><p>text</p></article>'
        for aid, title in articles
    )
    return (
        '<html><body><section id="r01"><h3>Run</h3></section>'
        f"{body}<article id='area-1'><h3>Area</h3></article></body></html>"
    )


def _entry(sid: str, **overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": sid,
        "level": "moderate",
        "priority": "P2",
        "effort": "E2",
        "horizon": "H1",
        "status": "open",
        "opened_on": "2026-08-02",
        "appearances": [
            {"report": "V13", "article": sid.lower(), "kind": "finding", "title": f"{sid} — Title"}
        ],
        "aliases": [],
        "closure": None,
        "remediation": None,
        "deferral": None,
        "note": None,
    }
    entry.update(overrides)
    return entry


def _register(findings: list[dict[str, object]], **reports: dict[str, str]) -> dict[str, object]:
    return {
        "$comment": "Synthetic register.",
        "schema_version": 1,
        "horizon_days": {"H0": 7, "H1": 28, "H2": 90},
        "reports": {"V13": {"file": V13_REL, "date": "2026-08-02"}, **reports},
        "legacy_reports": {},
        "findings": findings,
    }


def _published(findings: list[dict[str, object]]) -> list[tuple[str, str]]:
    cards: list[tuple[str, str]] = []
    for finding in findings:
        appearances = finding["appearances"]
        assert isinstance(appearances, list)
        cards += [(a["article"], a["title"]) for a in appearances if a["report"] == "V13"]
    return cards


def _repo(tmp_path: Path, findings: list[dict[str, object]], *, v13: str | None = None) -> Path:
    audit = tmp_path / "docs" / "audit"
    audit.mkdir(parents=True)
    (tmp_path / V13_REL).write_text(
        v13 if v13 is not None else _report_html(*_published(findings)), encoding="utf-8"
    )
    (tmp_path / "docs" / "architecture").mkdir(parents=True)
    (tmp_path / ADR_REL).write_text("# ADR-001\n", encoding="utf-8")
    (audit / "findings_register.json").write_text(json.dumps(_register(findings)), encoding="utf-8")
    return tmp_path


def _errors(root: Path) -> list[str]:
    _register_found, errors = register_tool.check(root)
    return list(errors)


def _closed(*proof: str) -> dict[str, object]:
    return _entry(
        "AC-001",
        status="closed",
        closure={"on": "2026-10-22", "report": "V13", "proof": list(proof)},
    )


class TestTheRealRegister:
    """The committed register, verified without reading the date."""

    def test_it_agrees_with_every_report_it_registers(self) -> None:
        register, errors = register_tool.check(REPO_ROOT)
        assert errors == []
        assert register is not None and register.findings

    def test_the_identifier_v14_reused_is_an_explicit_alias(self) -> None:
        register, _errors_found = register_tool.check(REPO_ROOT)
        by_id = {finding.id: finding for finding in register.findings}
        assert "V14:AC-014" in by_id["AC-040"].aliases
        assert by_id["AC-014"].status == "closed"


class TestShape:
    """A hand edit that breaks the shape is reported as a sentence."""

    def test_a_valid_register_parses_to_typed_entries(self) -> None:
        register, errors = register_tool.parse_register(_register([_entry("AC-001")]))
        assert errors == []
        finding = register.findings[0]
        assert finding.opened_on == date(2026, 8, 2)
        assert finding.appearances[0].report == "V13"

    @pytest.mark.parametrize(
        ("mutate", "fragment"),
        [
            (lambda r: r.update(schema_version=2), "schema_version"),
            (lambda r: r.update(finding=[]), "unknown key 'finding'"),
            (lambda r: r.update(findings="AC-001"), "expected a list"),
            (lambda r: r["findings"].append("AC-002"), "findings[1]: expected an object"),
            (lambda r: r["findings"][0].update(deferal=None), "unknown key 'deferal'"),
            (lambda r: r["findings"][0].pop("note"), "missing key 'note'"),
            (lambda r: r["findings"][0].update(appearances={}), "expected a list"),
            (lambda r: r["findings"][0].update(opened_on="22/10/2026"), "ISO date"),
            # ``date.fromisoformat`` reads the basic format too: refused on purpose.
            (lambda r: r["findings"][0].update(opened_on="20260802"), "ISO date"),
            (lambda r: r["findings"][0].update(aliases=[3]), "expected a string"),
            (lambda r: r["horizon_days"].update(H0=True), "positive integer"),
            (lambda r: r["horizon_days"].update(H0=0), "positive integer"),
            (lambda r: r["reports"]["V13"].pop("date"), "missing key 'date'"),
            (
                lambda r: r["findings"][0].update(closure={"on": "2026-10-22", "proof": "x"}),
                "missing key 'report'",
            ),
        ],
    )
    def test_a_broken_shape_is_a_sentence(self, mutate: object, fragment: str) -> None:
        raw = copy.deepcopy(_register([_entry("AC-001")]))
        assert callable(mutate)
        mutate(raw)
        register, errors = register_tool.parse_register(raw)
        assert register is None
        assert any(fragment in error for error in errors), errors

    def test_a_register_that_is_not_an_object_is_refused(self) -> None:
        register, errors = register_tool.parse_register(["AC-001"])
        assert register is None and errors


class TestStructure:
    def test_a_consistent_synthetic_register_passes(self, tmp_path: Path) -> None:
        assert _errors(_repo(tmp_path, [_entry("AC-001"), _entry("AC-002")])) == []

    def test_a_duplicate_identifier_is_refused(self, tmp_path: Path) -> None:
        errors = _errors(_repo(tmp_path, [_entry("AC-001"), _entry("AC-001")]))
        assert any("AC-001" in e and "duplicate" in e for e in errors)

    def test_a_malformed_identifier_is_refused(self, tmp_path: Path) -> None:
        errors = _errors(_repo(tmp_path, [_entry("AC-1")], v13=_report_html()))
        assert any("invalid identifier" in e for e in errors)

    def test_a_title_that_differs_from_the_report_is_refused(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_entry("AC-001")], v13=_report_html(("ac-001", "Another title")))
        assert any("title" in e for e in _errors(root))

    def test_a_published_finding_missing_from_the_register_is_refused(self, tmp_path: Path) -> None:
        v13 = _report_html(("ac-001", "AC-001 — Title"), ("ac-002", "AC-002 — Title"))
        errors = _errors(_repo(tmp_path, [_entry("AC-001")], v13=v13))
        assert any("ac-002" in e and "not registered" in e for e in errors)

    def test_an_appearance_absent_from_its_report_is_refused(self, tmp_path: Path) -> None:
        root = _repo(
            tmp_path,
            [_entry("AC-001"), _entry("AC-002")],
            v13=_report_html(("ac-001", "AC-001 — Title")),
        )
        assert any("ac-002" in e and "absent" in e for e in _errors(root))

    def test_a_renumbered_appearance_needs_an_alias(self, tmp_path: Path) -> None:
        moved = _entry(
            "AC-040",
            appearances=[
                {"report": "V13", "article": "ac-014", "kind": "finding", "title": "AC-014 — T"}
            ],
        )
        root = _repo(tmp_path, [moved])
        assert any("alias" in e for e in _errors(root))
        moved["aliases"] = ["V13:AC-014"]
        (root / "docs" / "audit" / "findings_register.json").write_text(
            json.dumps(_register([moved])), encoding="utf-8"
        )
        assert _errors(root) == []

    def test_a_stale_alias_is_refused(self, tmp_path: Path) -> None:
        errors = _errors(_repo(tmp_path, [_entry("AC-001", aliases=["V13:AC-099"])]))
        assert any("alias" in e for e in errors)

    def test_an_appearance_of_the_wrong_kind_is_refused(self, tmp_path: Path) -> None:
        card = {"report": "V13", "article": "clos-ac-001", "kind": "finding", "title": "Closed"}
        errors = _errors(_repo(tmp_path, [_entry("AC-001", appearances=[card])]))
        assert any("kind closure" in e for e in errors)

    @pytest.mark.parametrize(
        ("overrides", "fragment"),
        [
            ({"status": "closed"}, "closure"),
            ({"status": "remediated"}, "remediation"),
            ({"status": "open", "horizon": None}, "horizon"),
            ({"status": "open", "horizon": "H9"}, "horizon"),
            ({"level": "severe"}, "level"),
            ({"priority": "P9"}, "priority"),
            ({"effort": "E0"}, "effort"),
            ({"status": "fixed"}, "status"),
            ({"opened_on": None}, "opened_on"),
            (
                {"status": "closed", "deferral": None, "closure": None},
                "closure",
            ),
            (
                {
                    "status": "closed",
                    "closure": {"on": "2026-10-22", "report": "V13", "proof": ["ADR-001"]},
                    "deferral": {
                        "until": "2026-11-01",
                        "reason": "Waiting.",
                        "decided_on": "2026-10-23",
                    },
                },
                "deferral",
            ),
        ],
    )
    def test_an_inconsistent_entry_is_refused(
        self, tmp_path: Path, overrides: dict[str, object], fragment: str
    ) -> None:
        errors = _errors(_repo(tmp_path, [_entry("AC-001", **overrides)]))
        assert any(fragment in e for e in errors), errors

    def test_an_unpublished_identifier_has_no_appearance(self, tmp_path: Path) -> None:
        reserved = _entry(
            "AC-002",
            status="unpublished",
            appearances=[],
            horizon=None,
            level=None,
            priority=None,
            effort=None,
            opened_on=None,
        )
        root = _repo(tmp_path, [_entry("AC-001"), reserved])
        assert _errors(root) == []
        reserved["appearances"] = [
            {"report": "V13", "article": "ac-002", "kind": "finding", "title": "AC-002 — Title"}
        ]
        root = _repo(tmp_path / "second", [_entry("AC-001"), reserved])
        assert any("unpublished" in e for e in _errors(root))

    def test_a_new_report_cannot_be_added_without_registering_it(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_entry("AC-001")])
        (root / V14_REL).write_text(_report_html(), encoding="utf-8")
        errors = _errors(root)
        assert any("AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14.html" in e for e in errors)

    def test_a_registered_report_must_exist(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_entry("AC-001")])
        (root / V13_REL).unlink()
        assert any("does not exist" in e for e in _errors(root))


class TestProofs:
    """A proof is something a reader can open: protocol section 4.2."""

    def test_every_kind_of_proof_is_accepted(self, tmp_path: Path) -> None:
        closed = _closed(f"{V13_REL}#ac-001", V13_REL, "V13:r01", "ADR-001", "0123abc")
        assert _errors(_repo(tmp_path, [closed])) == []

    @pytest.mark.parametrize(
        ("proof", "fragment"),
        [
            ("apps/api/src/module.py:12", "line number"),
            ("docs/missing.md", "does not exist"),
            (f"{V13_REL}#nowhere", "anchor"),
            ("V13:r99", "run"),
            ("V99:r01", "unknown report"),
            ("ADR-999", "ADR-999"),
            ("see the report", "not a proof"),
        ],
    )
    def test_a_proof_nobody_can_open_is_refused(
        self, tmp_path: Path, proof: str, fragment: str
    ) -> None:
        errors = _errors(_repo(tmp_path, [_closed(proof)]))
        assert any(fragment in e for e in errors), errors

    def test_an_empty_proof_list_is_refused(self, tmp_path: Path) -> None:
        errors = _errors(_repo(tmp_path, [_closed()]))
        assert any("proof" in e for e in errors)

    def test_a_closure_names_a_registered_report(self, tmp_path: Path) -> None:
        closed = _entry(
            "AC-001",
            status="closed",
            closure={"on": "2026-10-22", "report": "V99", "proof": ["ADR-001"]},
        )
        assert any("V99" in e for e in _errors(_repo(tmp_path, [closed])))


class TestDeadlines:
    """The date-dependent half, on an injected date: never on the real register."""

    @staticmethod
    def _parsed(finding: dict[str, object], **reports: dict[str, str]) -> object:
        register, errors = register_tool.parse_register(_register([finding], **reports))
        assert errors == []
        return register

    @staticmethod
    def _p1(**overrides: object) -> dict[str, object]:
        return _entry("AC-003", **{"priority": "P1", "horizon": "H0", **overrides})

    def test_a_p1_past_its_horizon_is_overdue(self) -> None:
        register = self._parsed(self._p1())
        assert register_tool.overdue(register, date(2026, 8, 9)) == []
        late = register_tool.overdue(register, date(2026, 8, 10))
        assert [item.finding_id for item in late] == ["AC-003"]
        assert late[0].due_on == date(2026, 8, 9)
        assert not late[0].deferred

    def test_a_dated_and_reasoned_deferral_holds_until_it_expires(self) -> None:
        deferral = {"until": "2026-09-01", "reason": "Waiting.", "decided_on": "2026-08-05"}
        register = self._parsed(self._p1(deferral=deferral))
        assert register_tool.overdue(register, date(2026, 8, 20))[0].deferred
        assert register_tool.overdue(register, date(2026, 9, 1))[0].deferred
        assert not register_tool.overdue(register, date(2026, 9, 2))[0].deferred

    @pytest.mark.parametrize(
        "deferral",
        [
            {"until": "2026-09-01", "reason": " ", "decided_on": "2026-08-05"},
            {"until": "2026-09-01", "reason": "Waiting.", "decided_on": None},
            {"until": "soon", "reason": "Waiting.", "decided_on": "2026-08-05"},
        ],
    )
    def test_a_deferral_without_its_reason_or_dates_is_refused(
        self, deferral: dict[str, object]
    ) -> None:
        register, errors = register_tool.parse_register(_register([self._p1(deferral=deferral)]))
        assert register is None and any("deferral" in e for e in errors), errors

    @pytest.mark.parametrize(
        "overrides",
        [
            {"priority": "P2"},
            {"status": "remediated"},
            {
                "status": "presumed_closed",
                "closure": {"on": "2026-10-22", "report": "V13", "proof": ["ADR-001"]},
            },
        ],
    )
    def test_only_an_open_p1_can_be_overdue(self, overrides: dict[str, object]) -> None:
        register = self._parsed(self._p1(**overrides))
        assert register_tool.overdue(register, date(2027, 1, 1)) == []

    def test_the_deadline_starts_at_the_last_report_that_carried_it(self) -> None:
        carried = self._p1(
            appearances=[
                {"report": "V13", "article": "ac-003", "kind": "finding", "title": "t"},
                {"report": "V14", "article": "AC-003", "kind": "finding", "title": "t"},
            ]
        )
        register = self._parsed(carried, V14={"file": V14_REL, "date": "2026-10-22"})
        assert register_tool.overdue(register, date(2026, 10, 29)) == []
        assert register_tool.overdue(register, date(2026, 10, 30))[0].due_on == date(2026, 10, 29)


class TestCommandLine:
    def test_a_late_p1_warns_and_fails_only_in_strict_mode(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path, [_entry("AC-003", priority="P1", horizon="H0")])
        assert register_tool.main([str(root)]) == 0
        assert "AC-003" in capsys.readouterr().out
        assert register_tool.main([str(root), "--strict"]) == 1

    def test_a_structural_error_fails_in_both_modes(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_entry("AC-001"), _entry("AC-001")])
        assert register_tool.main([str(root)]) == 1
        assert register_tool.main([str(root), "--strict"]) == 1

    def test_an_unreadable_register_is_a_sentence(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path, [_entry("AC-001")])
        (root / "docs" / "audit" / "findings_register.json").write_text("{", encoding="utf-8")
        assert register_tool.main([str(root)]) == 1
        assert "cannot read" in capsys.readouterr().out
