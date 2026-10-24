#!/usr/bin/env python3
"""The audit findings register agrees with the reports it registers (AC-031).

Why
---
Until 2026-10-23 the register of quality audit findings lived only inside the
successive HTML reports, and nothing checked that one report carried the
previous one forward. The revision of V14 measured the cost: three P0 findings of
V13 still open after 86 releases, a V13 finding dropped by V14 without a status,
and V14 reusing the identifier AC-014 for another subject. Building this register
found a wider drift: V11, V12 and V13 each numbered their findings from AC-001
again, so the identifiers were never stable across those reports.

Contract
--------
``docs/audit/findings_register.json`` holds one entry per finding, under a
stable ``AC-NNN`` identifier. It is edited by hand, so its SHAPE is checked
first, key by key: a typo comes back as a sentence naming where it is, never as
a traceback. Then every report it registers is parsed, and each finding card
(``<article id="ac-NNN">``) or closure card (``clos-ac-NNN``,
``clos-v13-ac-NNN``) must match exactly one appearance, title included. An
appearance published under another number must be declared as an alias, so a
renumbering or a reuse is always explicit. A closure or a remediation carries
proofs a reader can open (protocol section 4.2): a repository path, optionally
with an anchor that exists in it, an ADR, a commit, or a run of a registered
report (``V14R:R07``) — never a line number.

Structural errors fail in every mode. The deadline rule is a warning: an open or
reopened P1 whose horizon has elapsed since the last report that carried it.
``--strict`` (``task release:check``) fails on it, unless the entry carries a
deferral with a reason, a decision date and an ``until`` date not yet passed.

Usage (from any working directory):
    python scripts/audit/findings_register.py [REPO_ROOT] [--strict]

Standard library only — no dependencies.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

__all__ = [
    "REGISTER_REL",
    "Appearance",
    "Deferral",
    "Evidence",
    "Finding",
    "Overdue",
    "Register",
    "Report",
    "check",
    "load_register",
    "main",
    "overdue",
    "parse_register",
    "parse_report",
    "validate",
]

REGISTER_REL = "docs/audit/findings_register.json"
SCHEMA_VERSION = 1
_AUDIT_DIR = "docs/audit"
_ADR_DIR = "docs/architecture"
_REPORT_GLOB = "AUDIT_CODEBASE_*_CONSOLIDE_V*.html"
_REPORT_VERSION = re.compile(r"_CONSOLIDE_V(\d+)")
#: The first report of the AC era. Older reports used R-/F- identifiers.
FIRST_AC_REPORT_VERSION = 11

_ARTICLE = re.compile(
    r'<article\b[^>]*\bid="((?:clos-)?(?:v\d+-)?(?:ac|AC)-\d{3})"[^>]*>(.*?)</article>', re.S
)
_H3 = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")
_ANY_ID = re.compile(r"""\bid=["']([^"']+)["']""")
_ID = re.compile(r"^AC-\d{3}$")
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_LINE_NUMBER = re.compile(r"\.\w+:\d+")
_ADR = re.compile(r"^ADR-(?P<number>\d{3})$")
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
_RUN = re.compile(r"^(?P<report>[A-Z0-9]+):(?P<run>[A-Za-z]\w*)$")
_PATH = re.compile(r"^[\w.@\[\]][\w./@\[\]-]*(?:#(?P<anchor>[\w-]+))?$")

LEVELS = frozenset({"major", "moderate", "minor"})
PRIORITIES = frozenset(f"P{n}" for n in range(6))
EFFORTS = frozenset(f"E{n}" for n in range(1, 6))
OPEN_STATUSES = frozenset({"open", "reopened"})
CLOSURE_STATUSES = frozenset({"closed", "partially_closed", "presumed_closed"})
STATUSES = OPEN_STATUSES | CLOSURE_STATUSES | {"remediated", "unpublished"}

_TOP_KEYS = frozenset({"schema_version", "horizon_days", "reports", "legacy_reports", "findings"})
_FINDING_KEYS = frozenset(
    {
        "id",
        "level",
        "priority",
        "effort",
        "horizon",
        "status",
        "opened_on",
        "appearances",
        "aliases",
        "closure",
        "remediation",
        "deferral",
        "note",
    }
)
_APPEARANCE_KEYS = frozenset({"report", "article", "kind", "title"})
_EVIDENCE_KEYS = frozenset({"on", "report", "proof"})
_DEFERRAL_KEYS = frozenset({"until", "reason", "decided_on"})
_REPORT_KEYS = frozenset({"file", "date"})
_LEGACY_REPORT_KEYS = frozenset({"file", "reason"})


@dataclass(frozen=True)
class Appearance:
    """One card of one report that carries the finding."""

    report: str
    article: str
    kind: str
    title: str


@dataclass(frozen=True)
class Evidence:
    """A closure or a remediation: when, on which report's word, and its proofs."""

    on: date
    report: str | None
    proof: tuple[str, ...]


@dataclass(frozen=True)
class Deferral:
    """A dated, reasoned decision to let a late P1 through the release gate."""

    until: date
    reason: str
    decided_on: date


@dataclass(frozen=True)
class Finding:
    """One register entry, as the file declares it."""

    id: str
    level: str | None
    priority: str | None
    effort: str | None
    horizon: str | None
    status: str
    opened_on: date | None
    appearances: tuple[Appearance, ...]
    aliases: tuple[str, ...]
    closure: Evidence | None
    remediation: Evidence | None
    deferral: Deferral | None
    note: str | None


@dataclass(frozen=True)
class Report:
    """A registered report: its file, and its date when it opens deadlines."""

    file: str
    date: date | None


@dataclass(frozen=True)
class Register:
    """The decoded register."""

    horizon_days: dict[str, int]
    reports: dict[str, Report]
    legacy_reports: dict[str, Report]
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class Overdue:
    """An open P1 whose horizon has elapsed."""

    finding_id: str
    due_on: date
    deferred: bool


def _iso(value: object) -> date | None:
    """Read a ``YYYY-MM-DD`` date; any other spelling is refused."""
    if not isinstance(value, str) or not _ISO_DAY.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class _Shape:
    """Narrow decoded JSON to typed values, collecting one sentence per defect."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def fields(
        self,
        value: object,
        where: str,
        keys: frozenset[str],
        optional: frozenset[str] = frozenset(),
    ) -> dict[str, object] | None:
        """The object's declared keys, or None after reporting why it is unusable."""
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            self.fail(where, "expected an object")
            return None
        unknown = sorted(set(value) - keys - optional)
        missing = sorted(keys - set(value))
        for key in unknown:
            self.fail(where, f"unknown key {key!r}")
        for key in missing:
            self.fail(where, f"missing key {key!r}")
        if unknown or missing:
            return None
        return {key: value[key] for key in keys}

    def text(self, value: object, where: str) -> str | None:
        if isinstance(value, str) and value.strip():
            return value
        self.fail(where, "expected a string")
        return None

    def optional_text(self, value: object, where: str) -> str | None:
        return None if value is None else self.text(value, where)

    def day(self, value: object, where: str) -> date | None:
        parsed = _iso(value)
        if parsed is None:
            self.fail(where, "expected an ISO date (YYYY-MM-DD)")
        return parsed

    def optional_day(self, value: object, where: str) -> date | None:
        return None if value is None else self.day(value, where)

    def items(self, value: object, where: str) -> list[object]:
        if isinstance(value, list):
            return list(value)
        self.fail(where, "expected a list")
        return []

    def texts(self, value: object, where: str) -> tuple[str, ...]:
        found = (
            self.text(item, f"{where}[{i}]") for i, item in enumerate(self.items(value, where))
        )
        return tuple(item for item in found if item is not None)


def _appearance(shape: _Shape, value: object, where: str) -> Appearance | None:
    fields = shape.fields(value, where, _APPEARANCE_KEYS)
    if fields is None:
        return None
    report = shape.text(fields["report"], f"{where}.report")
    article = shape.text(fields["article"], f"{where}.article")
    kind = shape.text(fields["kind"], f"{where}.kind")
    title = shape.text(fields["title"], f"{where}.title")
    if report is None or article is None or kind is None or title is None:
        return None
    return Appearance(report, article, kind, title)


def _evidence(shape: _Shape, value: object, where: str) -> Evidence | None:
    if value is None:
        return None
    fields = shape.fields(value, where, _EVIDENCE_KEYS)
    if fields is None:
        return None
    on = shape.day(fields["on"], f"{where}.on")
    report = shape.optional_text(fields["report"], f"{where}.report")
    proof = shape.texts(fields["proof"], f"{where}.proof")
    return None if on is None else Evidence(on, report, proof)


def _deferral(shape: _Shape, value: object, where: str) -> Deferral | None:
    if value is None:
        return None
    fields = shape.fields(value, where, _DEFERRAL_KEYS)
    if fields is None:
        return None
    until = shape.day(fields["until"], f"{where}.until")
    reason = shape.text(fields["reason"], f"{where}.reason")
    decided_on = shape.day(fields["decided_on"], f"{where}.decided_on")
    if until is None or reason is None or decided_on is None:
        return None
    return Deferral(until, reason, decided_on)


def _finding(shape: _Shape, value: object, where: str) -> Finding | None:
    fields = shape.fields(value, where, _FINDING_KEYS)
    if fields is None:
        return None
    sid = shape.text(fields["id"], f"{where}.id")
    label = sid or where
    appearances = (
        _appearance(shape, item, f"{label}.appearances[{i}]")
        for i, item in enumerate(shape.items(fields["appearances"], f"{label}.appearances"))
    )
    finding = Finding(
        id=sid or "",
        level=shape.optional_text(fields["level"], f"{label}.level"),
        priority=shape.optional_text(fields["priority"], f"{label}.priority"),
        effort=shape.optional_text(fields["effort"], f"{label}.effort"),
        horizon=shape.optional_text(fields["horizon"], f"{label}.horizon"),
        status=shape.text(fields["status"], f"{label}.status") or "",
        opened_on=shape.optional_day(fields["opened_on"], f"{label}.opened_on"),
        appearances=tuple(item for item in appearances if item is not None),
        aliases=shape.texts(fields["aliases"], f"{label}.aliases"),
        closure=_evidence(shape, fields["closure"], f"{label}.closure"),
        remediation=_evidence(shape, fields["remediation"], f"{label}.remediation"),
        deferral=_deferral(shape, fields["deferral"], f"{label}.deferral"),
        note=shape.optional_text(fields["note"], f"{label}.note"),
    )
    return finding if sid is not None else None


def _horizons(shape: _Shape, value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        shape.fail("horizon_days", "expected an object")
        return {}
    horizons: dict[str, int] = {}
    for key, days in value.items():
        if not isinstance(key, str) or type(days) is not int or days <= 0:
            shape.fail(f"horizon_days.{key}", "expected a positive integer number of days")
            continue
        horizons[key] = days
    return horizons


def _reports(shape: _Shape, value: object, section: str) -> dict[str, Report]:
    if not isinstance(value, dict):
        shape.fail(section, "expected an object")
        return {}
    keys = _REPORT_KEYS if section == "reports" else _LEGACY_REPORT_KEYS
    reports: dict[str, Report] = {}
    for key, entry in value.items():
        fields = shape.fields(entry, f"{section}.{key}", keys)
        if fields is None:
            continue
        file = shape.text(fields["file"], f"{section}.{key}.file")
        if section == "reports":
            day = shape.day(fields["date"], f"{section}.{key}.date")
        else:
            day = None
            shape.text(fields["reason"], f"{section}.{key}.reason")
        if file is not None:
            reports[str(key)] = Report(file, day)
    return reports


def parse_register(data: object) -> tuple[Register | None, list[str]]:
    """Check the register's shape and decode it.

    Args:
        data: The register as ``json.loads`` returns it.

    Returns:
        ``(register, [])`` when every key has its expected type, else
        ``(None, sentences)`` naming each defect and where it is.
    """
    shape = _Shape()
    fields = shape.fields(data, "register", _TOP_KEYS, optional=frozenset({"$comment"}))
    if fields is None:
        return None, shape.errors
    version = fields["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        shape.fail("register", f"unsupported schema_version {version!r}")
        return None, shape.errors
    horizon_days = _horizons(shape, fields["horizon_days"])
    reports = _reports(shape, fields["reports"], "reports")
    legacy_reports = _reports(shape, fields["legacy_reports"], "legacy_reports")
    entries = (
        _finding(shape, item, f"findings[{i}]")
        for i, item in enumerate(shape.items(fields["findings"], "findings"))
    )
    findings = tuple(entry for entry in entries if entry is not None)
    if shape.errors:
        return None, shape.errors
    return Register(horizon_days, reports, legacy_reports, findings), []


def load_register(root: Path) -> object:
    """Read the register file.

    Args:
        root: Repository root.

    Returns:
        The decoded JSON, not yet checked (see :func:`parse_register`).

    Raises:
        OSError: If the file cannot be read.
        ValueError: If it is not JSON.
    """
    decoded: object = json.loads((root / REGISTER_REL).read_text(encoding="utf-8"))
    return decoded


def _text(fragment: str) -> str:
    return _SPACES.sub(" ", html.unescape(_TAG.sub(" ", fragment))).strip()


def parse_report(path: Path) -> list[tuple[str, str]]:
    """List the finding and closure cards of one report.

    Args:
        path: The report's HTML file.

    Returns:
        ``(article id, h3 title)`` for every card, in document order.
    """
    cards: list[tuple[str, str]] = []
    for article_id, body in _ARTICLE.findall(path.read_text(encoding="utf-8")):
        heading = _H3.search(body)
        cards.append((article_id, _text(heading.group(1)) if heading else ""))
    return cards


def _published_id(article_id: str) -> str:
    return f"AC-{article_id[-3:]}"


class _Ids:
    """The element ids of the files proofs point into, each file read once."""

    def __init__(self) -> None:
        self._by_path: dict[Path, frozenset[str]] = {}

    def has(self, path: Path, ident: str) -> bool:
        if path not in self._by_path:
            text = path.read_text(encoding="utf-8", errors="replace")
            self._by_path[path] = frozenset(m.lower() for m in _ANY_ID.findall(text))
        return ident.lower() in self._by_path[path]


def _check_fields(finding: Finding) -> list[str]:
    sid = finding.id
    errors = []
    if finding.status not in STATUSES:
        errors.append(f"{sid}: unknown status {finding.status!r}")
    if finding.status == "unpublished":
        return errors
    for field, value, allowed in (
        ("level", finding.level, LEVELS),
        ("priority", finding.priority, PRIORITIES),
        ("effort", finding.effort, EFFORTS),
    ):
        if value not in allowed:
            errors.append(f"{sid}: invalid {field} {value!r}")
    if finding.opened_on is None:
        errors.append(f"{sid}: a published finding needs its opened_on date")
    return errors


def _check_status(finding: Finding, register: Register) -> list[str]:
    sid, status = finding.id, finding.status
    errors = []
    if status in OPEN_STATUSES and finding.horizon not in register.horizon_days:
        errors.append(
            f"{sid}: an open finding needs a horizon among {sorted(register.horizon_days)}"
        )
    if status in CLOSURE_STATUSES and finding.closure is None:
        errors.append(f"{sid}: status {status} needs a closure with its proof")
    if status == "remediated" and finding.remediation is None:
        errors.append(f"{sid}: status remediated needs a remediation with its proof")
    if status == "unpublished" and finding.appearances:
        errors.append(f"{sid}: an unpublished identifier cannot appear in a report")
    if finding.deferral is not None and status not in OPEN_STATUSES:
        errors.append(f"{sid}: a deferral applies to an open finding only")
    for label, evidence in (("closure", finding.closure), ("remediation", finding.remediation)):
        if evidence is None:
            continue
        if evidence.report is not None and evidence.report not in register.reports:
            errors.append(f"{sid}: {label} names unknown report {evidence.report}")
        if not evidence.proof:
            errors.append(f"{sid}: {label} carries no proof")
    return errors


def _check_aliases(finding: Finding) -> list[str]:
    sid = finding.id
    expected = {
        f"{appearance.report}:{_published_id(appearance.article)}"
        for appearance in finding.appearances
        if _published_id(appearance.article) != sid
    }
    declared = set(finding.aliases)
    errors = [f"{sid}: appearance {alias} needs an alias" for alias in sorted(expected - declared)]
    errors += [f"{sid}: stale alias {alias}" for alias in sorted(declared - expected)]
    return errors


def _proof_error(proof: str, register: Register, root: Path, ids: _Ids) -> str | None:
    """Why ``proof`` is not something a reader can open, or None when it is."""
    if _LINE_NUMBER.search(proof):
        return f"{proof} quotes a line number, which a proof never does (protocol section 4.2)"
    if (adr := _ADR.match(proof)) is not None:
        if any((root / _ADR_DIR).glob(f"ADR-{adr['number']}-*.md")):
            return None
        return f"{proof} does not exist in {_ADR_DIR}"
    if _COMMIT.match(proof):
        return None
    if (run := _RUN.match(proof)) is not None:
        report = register.reports.get(run["report"])
        if report is None:
            return f"{proof} names unknown report {run['report']}"
        if not ids.has(root / report.file, run["run"]):
            return f"{proof}: run {run['run']} is absent from {run['report']}"
        return None
    if (path := _PATH.match(proof)) is not None:
        rel = proof.split("#", 1)[0]
        if not (root / rel).is_file():
            return f"{rel} does not exist"
        anchor = path["anchor"]
        if anchor and not ids.has(root / rel, anchor):
            return f"{proof}: anchor #{anchor} is absent from {rel}"
        return None
    return (
        f"{proof!r} is not a proof: a repository path, an ADR, a commit or a report run "
        "(protocol section 4.2)"
    )


def _check_proofs(finding: Finding, register: Register, root: Path, ids: _Ids) -> list[str]:
    errors = []
    for label, evidence in (("closure", finding.closure), ("remediation", finding.remediation)):
        for proof in evidence.proof if evidence is not None else ():
            problem = _proof_error(proof, register, root, ids)
            if problem is not None:
                errors.append(f"{finding.id}: {label} proof {problem}")
    return errors


def _check_reports(register: Register, root: Path) -> list[str]:
    errors = []
    declared: set[str] = set()
    for section, reports in (
        ("reports", register.reports),
        ("legacy_reports", register.legacy_reports),
    ):
        for key, report in reports.items():
            declared.add(report.file)
            if not (root / report.file).is_file():
                errors.append(f"{section}.{key}: {report.file} does not exist")
    for path in sorted((root / _AUDIT_DIR).glob(_REPORT_GLOB)):
        match = _REPORT_VERSION.search(path.name)
        rel = path.relative_to(root).as_posix()
        if match and int(match.group(1)) >= FIRST_AC_REPORT_VERSION and rel not in declared:
            errors.append(f"{rel} is an AC-era report missing from the register")
    return errors


def _check_claims(register: Register) -> list[str]:
    """One entry per card, of the kind its identifier says, in a known report."""
    errors = []
    claimed: dict[tuple[str, str], str] = {}
    for finding in register.findings:
        for appearance in finding.appearances:
            key = (appearance.report, appearance.article)
            if key in claimed:
                errors.append(f"{key[0]} {key[1]}: claimed by {claimed[key]} and {finding.id}")
            claimed[key] = finding.id
            if appearance.report not in register.reports:
                errors.append(f"{finding.id}: appearance refers to unknown report {key[0]}")
            expected_kind = "closure" if appearance.article.startswith("clos-") else "finding"
            if appearance.kind != expected_kind:
                errors.append(f"{finding.id}: {key[1]} must be of kind {expected_kind}")
    return errors


def _check_report_cards(report_key: str, path: Path, register: Register) -> list[str]:
    """The cards one report publishes and the appearances registered for it agree."""
    errors = []
    published: dict[str, str] = {}
    for article_id, title in parse_report(path):
        if article_id in published:
            errors.append(f"{report_key} {article_id}: duplicate card in the report")
        published[article_id] = title
    registered = {
        appearance.article: appearance
        for finding in register.findings
        for appearance in finding.appearances
        if appearance.report == report_key
    }
    for article_id in sorted(set(published) - set(registered)):
        errors.append(f"{report_key} {article_id}: published but not registered")
    for article_id in sorted(set(registered) - set(published)):
        errors.append(f"{report_key} {article_id}: registered but absent from the report")
    for article_id in sorted(set(published) & set(registered)):
        if registered[article_id].title != published[article_id]:
            errors.append(f"{report_key} {article_id}: title differs from the report")
    return errors


def validate(register: Register, root: Path) -> list[str]:
    """Every rule tying the register to its reports and proofs, independent of the date.

    Args:
        register: The decoded register (see :func:`parse_register`).
        root: Repository root (where the reports and the proofs live).

    Returns:
        One sentence per violation; empty when the register is consistent.
    """
    errors = _check_reports(register, root)
    ids = _Ids()
    seen: set[str] = set()
    for finding in register.findings:
        if not _ID.match(finding.id):
            errors.append(f"invalid identifier {finding.id!r}")
        elif finding.id in seen:
            errors.append(f"{finding.id}: duplicate identifier")
        seen.add(finding.id)
        errors += _check_fields(finding) + _check_status(finding, register)
        errors += _check_aliases(finding) + _check_proofs(finding, register, root, ids)
    errors += _check_claims(register)
    for report_key, report in register.reports.items():
        path = root / report.file
        if path.is_file():
            errors += _check_report_cards(report_key, path, register)
    return errors


def check(root: Path) -> tuple[Register | None, list[str]]:
    """Read, decode and verify the register of the repository at ``root``.

    Args:
        root: Repository root.

    Returns:
        The register (None when it could not be decoded) and every error found.
    """
    try:
        data = load_register(root)
    except (OSError, ValueError) as exc:
        return None, [f"cannot read {REGISTER_REL}: {exc}"]
    register, errors = parse_register(data)
    if register is None:
        return None, errors
    return register, validate(register, root)


def overdue(register: Register, today: date) -> list[Overdue]:
    """Open P1 findings whose horizon elapsed since the last report that carried them.

    Args:
        register: The decoded register.
        today: The date to judge against.

    Returns:
        One item per late finding, telling whether a valid deferral covers it.
    """
    late = []
    for finding in register.findings:
        if finding.status not in OPEN_STATUSES or finding.priority != "P1":
            continue
        horizon = register.horizon_days.get(finding.horizon or "")
        reports = (register.reports.get(item.report) for item in finding.appearances)
        dates = [report.date for report in reports if report is not None and report.date]
        if horizon is None or not dates:
            continue
        due_on = max(dates) + timedelta(days=horizon)
        if today > due_on:
            deferred = finding.deferral is not None and finding.deferral.until >= today
            late.append(Overdue(finding.id, due_on, deferred))
    return late


def _default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    """Verify the register; in ``--strict`` mode, refuse an undeferred late P1.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        0 when the register passes, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("root", nargs="?", type=Path, default=None)
    parser.add_argument("--strict", action="store_true", help="fail on an undeferred late P1")
    args = parser.parse_args(argv)
    root: Path = args.root if args.root is not None else _default_root()
    register, errors = check(root)
    for error in errors:
        print(f"findings_register: error: {error}")
    if register is None or errors:
        return 1
    still_open = [f for f in register.findings if f.status in OPEN_STATUSES]
    remediated = sum(f.status == "remediated" for f in register.findings)
    late = overdue(register, datetime.now(UTC).date())
    print(
        f"findings_register: {len(register.findings)} findings, {len(still_open)} open "
        f"({sum(f.priority == 'P1' for f in still_open)} P1), {remediated} remediated "
        f"pending re-audit, {len(late)} P1 past their horizon "
        f"({sum(item.deferred for item in late)} deferred)"
    )
    for item in late:
        state = "deferred" if item.deferred else "not deferred"
        message = f"{item.finding_id} is past its horizon (due {item.due_on.isoformat()}, {state})"
        print(f"findings_register: warning: {message}")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=Audit finding overdue::{message}")
    if args.strict and any(not item.deferred for item in late):
        print("findings_register: error: --strict refuses an undeferred late P1")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
