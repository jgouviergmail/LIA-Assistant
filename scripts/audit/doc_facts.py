#!/usr/bin/env python3
"""Documentation fact drift: a quoted version or threshold must equal its source.

``doc_audit.py`` proves the documentation *navigates* correctly (no broken link,
no stale code path). It cannot see a sentence that is well-formed and false.
This module covers that second class: the numbers documents state about the
system — stack versions and the enforced coverage floor.

Why it exists (measured 2026-08-27, on a tree where ``task lint:docs`` was green)
--------------------------------------------------------------------------------
The backend coverage floor is ``67`` in both places that own it
(``apps/api/pyproject.toml`` addopts and ``Taskfile.yml``). Six documents stated
it, each with a different wrong value: 60 (``docs/technical/CI_CD.md``, which
additionally certified it had "une seule source de verite"), 62
(``docs/guides/GUIDE_TESTING.md``), 45 and 65 (``README.md``), 43
(``AGENTS.md``), 80 (``CONTRIBUTING.md``). LangGraph was quoted as 1.1.6 in four
documents and 1.0.4 in two more, against a pinned ``1.2.11``; Next.js as 16.2.10
against 16.2.11; FastAPI as 0.135.1 against 0.136.3.

None of that is an editorial mistake — it is the predictable outcome of copying
a value instead of pointing at it. The repository already answers this class for
release versions (``scripts/release/version_surfaces.py``: one declaration, read
by both the bump script and the CI guard). This module is the same doctrine for
facts that change when the *stack* changes rather than when a release ships.

Design
------
Two mechanisms, chosen per fact and never mixed by accident:

* **Discovery** — the fact has an unambiguous written shape (``LangGraph
  1.2.11``, ``--cov-fail-under=67``), so every occurrence in every LIVING
  document is found and checked. Discovery is preferred: a *new* document that
  quotes the fact is seen without anyone declaring it, the same reason
  ``discover_guide_stamps`` beats a hand-maintained table.
* **Exemption** — a legitimately different value, declared with a written
  reason. Two real ones: the self-host installer's Python 3.10 floor (ADR-215
  targets an operator's host interpreter, not ours), and narratives recording a
  version that *used* to apply (the ``python-compat`` job on 3.13, retired by
  ADR-241). An exemption without a reason fails its own guard.

Writing convention this enforces
--------------------------------
A document is free to choose its precision, but not to be precise and wrong:
``Next.js 16`` and ``Next.js 16.2.11`` are both accepted, ``LangGraph 1.0``
against a pinned ``1.2.11`` is not (see :func:`truncate_to_precision`). When a
sentence means "the 1.x generation" rather than a specific release, write
``LangGraph 1.x`` — no digit after the dot, nothing to keep up to date, and the
statement stays true across every minor bump. Prefer that to ``1.0+``, which
reads as a minimum and is checked like any other quoted value.

HISTORICAL documents (``docs/architecture/ADR-*``, ``docs/superpowers/``) are
out of scope by construction: they record what was true when they were written,
and the classification is imported from ``doc_audit`` so "living document" keeps
exactly one implementation.

Usage (from the repo root):
    python scripts/audit/doc_facts.py [REPO_ROOT] [--fix] [--include-unstaged]

Standard library only — no dependencies.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# ``doc_facts`` reuses ``doc_audit``'s scan base and LIVING/HISTORICAL
# classification rather than restating them: two definitions of "living
# document" would drift, which is the very defect this module exists to catch.
# The directory is injected explicitly because the CI guard loads this file
# out-of-tree (``spec_from_file_location``), where ``sys.path`` does not contain
# ``scripts/audit/``.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(_HERE))

from doc_audit import (  # noqa: E402  (deliberate: needs the sys.path line above)
    blank_code_regions,
    classify_document,
    doc_files,
    tracked_paths,
)

__all__ = [
    "FACTS",
    "FACT_HISTORICAL",
    "Exemption",
    "Fact",
    "Occurrence",
    "SourceError",
    "audit_facts",
    "drifted",
    "fix_facts",
    "floor_values",
    "resolve_facts",
    "rewrite_document",
    "truncate_to_precision",
]


#: Living documents whose *numbers* are nonetheless history, with the reason.
#:
#: ``classify_document`` answers a navigation question — an index's links must
#: work, so ``ADR_INDEX.md`` is rightly LIVING there. It answers the fact
#: question differently: every row summarises a decision and quotes the value
#: that applied when it was taken ("le plancher de couverture 60 % absent en
#: local", ADR-151). Rewriting those to today's value would falsify the record.
#: The two notions genuinely differ, so this set is declared here rather than
#: bent into the shared classifier.
FACT_HISTORICAL: dict[str, str] = {
    "docs/architecture/ADR_INDEX.md": (
        "Every entry summarises a past decision and quotes the value that "
        "applied at decision time; updating them would rewrite history."
    ),
}

#: ``--cov-fail-under=0`` is the idiom for "no gate on this targeted run", not a
#: claim about the enforced floor. Documenting that idiom must stay possible.
_COVERAGE_DISABLED_SENTINEL = "0"


class SourceError(RuntimeError):
    """A fact's source of truth is missing or unreadable.

    Never swallowed: a fact whose source cannot be read must fail the run, not
    silently make every quotation "match".
    """


# ---------------------------------------------------------------------------
# Sources of truth
# ---------------------------------------------------------------------------


def _read(root: Path, relative: str) -> str:
    """Read a repository file, or fail loudly.

    Args:
        root: Repository root.
        relative: POSIX path relative to ``root``.

    Returns:
        The file's text.

    Raises:
        SourceError: If the file is absent.
    """
    path = root / relative
    if not path.is_file():
        raise SourceError(f"source of truth missing: {relative}")
    return path.read_text(encoding="utf-8")


def _single(pattern: re.Pattern[str], text: str, what: str) -> str:
    """Return the one ``value`` group ``pattern`` matches in ``text``.

    Args:
        pattern: Regex exposing a ``value`` group.
        text: Text to search.
        what: Human label used in the error message.

    Returns:
        The matched value.

    Raises:
        SourceError: If the pattern matches zero times, or matches several
            times with disagreeing values.
    """
    values = {match.group("value") for match in pattern.finditer(text)}
    if not values:
        raise SourceError(f"cannot read {what}: pattern never matched")
    if len(values) > 1:
        raise SourceError(f"{what} is ambiguous: found {sorted(values)}")
    return values.pop()


_COV_FAIL_UNDER = re.compile(r"--cov-fail-under=(?P<value>\d+)")
_REQUIRES_PYTHON = re.compile(r'requires-python\s*=\s*">=(?P<value>\d+\.\d+)')


def floor_values(text: str) -> set[str]:
    """Every ``--cov-fail-under`` value in ``text`` that states a real floor.

    ``--cov-fail-under=0`` is excluded: it is the idiom for "no gate on this
    targeted run", never a claim that the floor is zero. Without this, a
    Taskfile gaining one targeted command would make the source read as
    ambiguous and abort ``task lint:docs`` for a reason unrelated to any
    document.

    Args:
        text: Contents of a file that owns the floor.

    Returns:
        The distinct floor values stated, sentinel excluded.
    """
    return {
        match.group("value")
        for match in _COV_FAIL_UNDER.finditer(text)
        if match.group("value") != _COVERAGE_DISABLED_SENTINEL
    }


def _coverage_floor(root: Path) -> str:
    """The enforced backend coverage floor, cross-validated across its owners.

    ``pyproject.toml`` carries the default and ``Taskfile.yml`` the CI command.
    Both are read and required to agree: taking only one would let the other
    drift unnoticed, which is exactly what happened to
    ``test_task_ci_pytest_parity_guard`` when ADR-151 moved the pytest commands
    out of ``ci.yml`` and left its comparison loop iterating over nothing.

    Args:
        root: Repository root.

    Returns:
        The floor as a decimal string (e.g. ``"67"``).

    Raises:
        SourceError: If either owner states several different floors, states
            none, or the two disagree.
    """
    owners = {
        "apps/api/pyproject.toml": floor_values(_read(root, "apps/api/pyproject.toml")),
        "Taskfile.yml": floor_values(_read(root, "Taskfile.yml")),
    }
    for name, values in owners.items():
        if not values:
            raise SourceError(f"cannot read the coverage floor from {name}: no --cov-fail-under")
        if len(values) > 1:
            raise SourceError(f"{name} states several coverage floors: {sorted(values)}")

    stated = {name: values.pop() for name, values in owners.items()}
    if len(set(stated.values())) > 1:
        detail = ", ".join(f"{name}={value}" for name, value in sorted(stated.items()))
        raise SourceError(
            f"coverage floor disagrees between its owners: {detail}. "
            "Align them before documenting either."
        )
    return next(iter(stated.values()))


def _python_version(root: Path) -> str:
    """The supported Python minor version, from ``requires-python``."""
    return _single(_REQUIRES_PYTHON, _read(root, "apps/api/pyproject.toml"), "requires-python")


def _node_major(root: Path) -> str:
    """The required Node.js major, from the root manifest's ``engines``."""
    manifest = json.loads(_read(root, "package.json"))
    spec = str((manifest.get("engines") or {}).get("node", ""))
    match = re.search(r"(?P<value>\d+)", spec)
    if not match:
        raise SourceError(f"cannot read engines.node from package.json (got {spec!r})")
    return match.group("value")


def _web_dependency(name: str) -> Callable[[Path], str]:
    """Build a resolver for a frontend dependency's pinned version.

    Args:
        name: Package name in ``apps/web/package.json``.

    Returns:
        A resolver returning the version without its range prefix.
    """

    def resolve(root: Path) -> str:
        manifest = json.loads(_read(root, "apps/web/package.json"))
        raw = str((manifest.get("dependencies") or {}).get(name, ""))
        match = re.search(r"(?P<value>\d+\.\d+\.\d+)", raw)
        if not match:
            raise SourceError(f"cannot read dependency {name!r} (got {raw!r})")
        return match.group("value")

    return resolve


def _requirement(name: str) -> Callable[[Path], str]:
    """Build a resolver for a backend requirement's pinned version.

    Reads the intent manifest rather than the lockfile: the manifest is what a
    human curates and what the documentation is describing. Extras are tolerated
    (``sqlalchemy[asyncio]==2.0.50``).

    Args:
        name: Distribution name in ``apps/api/requirements.txt``.

    Returns:
        A resolver returning the pinned version.
    """
    pattern = re.compile(
        rf"^{re.escape(name)}(?:\[[^\]]*\])?==(?P<value>\d+\.\d+\.\d+)",
        re.IGNORECASE | re.MULTILINE,
    )

    def resolve(root: Path) -> str:
        return _single(pattern, _read(root, "apps/api/requirements.txt"), f"requirement {name}")

    return resolve


def _compose_image_tag(pattern: re.Pattern[str]) -> Callable[[Path], str]:
    """Build a resolver reading a service's image tag from the prod Compose file.

    Args:
        pattern: Regex over ``docker-compose.prod.yml`` exposing a ``value``
            group.

    Returns:
        A resolver returning the tag.
    """

    def resolve(root: Path) -> str:
        return _single(pattern, _read(root, "docker-compose.prod.yml"), "compose image tag")

    return resolve


# ---------------------------------------------------------------------------
# Declaration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Exemption:
    """One document allowed to state a different value, and why.

    Attributes:
        path: Document, repository-relative POSIX path.
        value: The value that is legitimate *in that document*.
        reason: Why it differs. Mandatory — an exemption nobody justified is an
            oversight waiting to be swept in with the rest.
    """

    path: str
    value: str
    reason: str


@dataclass(frozen=True)
class Fact:
    """A value the documentation may quote, and the source that owns it.

    Attributes:
        key: Stable identifier used in reports.
        label: Human name shown in the drift report.
        source: Where the truth lives, for the error message.
        resolve: Recomputes the truth from the repository.
        pattern: Discovery regex exposing a ``value`` group. Never allowed to
            span a newline: a table header and the next row's number are not one
            statement.
        exemptions: Legitimately divergent occurrences.
    """

    key: str
    label: str
    source: str
    resolve: Callable[[Path], str]
    pattern: re.Pattern[str]
    exemptions: tuple[Exemption, ...] = ()

    def exemption_for(self, path: str, value: str) -> Exemption | None:
        """Return the exemption covering ``value`` in ``path``, if any."""
        for exemption in self.exemptions:
            if exemption.path == path and exemption.value == value:
                return exemption
        return None


@dataclass(frozen=True)
class Occurrence:
    """One quoted value found in one document.

    Attributes:
        fact: Key of the :class:`Fact` this quotation belongs to.
        path: Document, repository-relative POSIX path.
        line: 1-indexed line of the quotation.
        value: The value as written in the document.
        expected: The source value, truncated to ``value``'s precision.
        exempt: Whether a declared :class:`Exemption` covers it.
        start: Offset of ``value`` in the document's raw text.
        end: Offset just past ``value``.

    ``start``/``end`` exist so the fixer edits exactly what the scan found,
    rather than re-scanning with its own rules. The two used to diverge (code
    fences were blanked for the audit and not for the fix), which made
    ``--fix`` rewrite 18 occurrences the report never listed.
    """

    fact: str
    path: str
    line: int
    value: str
    expected: str
    exempt: bool
    start: int
    end: int


#: Separator run allowed between a technology's name and its version: markdown
#: emphasis, table pipes, code ticks, badge hyphens and colons. Newlines are
#: excluded on purpose (see ``Fact.pattern``).
#:
#: ``=`` is deliberately absent. It was there in the first draft and made
#: "Par defaut PostgreSQL = 100 connections" (a ``max_connections`` default in
#: docs/runbooks/alerts/CriticalDatabaseConnections.md) read as a claim that we
#: run PostgreSQL 100. An assignment introduces a setting, not a version.
_SEP = r"[ \t*_`|:-]{0,10}"

#: Gap allowed between a threshold phrase and its number: anything on the same
#: line that is not itself a digit. Bounded and non-greedy so it cannot reach
#: across a sentence to an unrelated number, but permissive enough for the real
#: spellings — "est **60 %**", ">= **60 %**", and a padded table cell.
_THRESHOLD_GAP = r"[^\n\d]{0,30}?"


def truncate_to_precision(expected: str, quoted: str) -> str:
    """Trim ``expected`` to the number of dot-separated parts ``quoted`` uses.

    A document is free to be as precise as it likes — "SQLAlchemy 2.0" and
    "SQLAlchemy 2.0.50" are both true — but it may not be precise and WRONG.
    Comparing at the quoted precision is what separates the two: "LangGraph 1.0"
    is a claim about the minor and is false against a pinned 1.2.11, while
    "Next.js 16" states only the major and stays true across patch bumps.

    Args:
        expected: The full version from the source of truth.
        quoted: The version as written in the document.

    Returns:
        ``expected`` truncated to ``quoted``'s number of components.
    """
    depth = quoted.count(".") + 1
    return ".".join(expected.split(".")[:depth])


def _version_pattern(name: str, digits: str = r"\d+(?:\.\d+){1,2}") -> re.Pattern[str]:
    """Discovery regex for ``<Technology> <version>``.

    A leading ``(?<![A-Za-z])`` guard is what keeps ``ApprovalGateNode`` followed
    by a numbered list item from being read as "Node 2" — measured, that exact
    false positive appeared in ``docs/technical/HITL.md``.

    Args:
        name: Technology name as written in prose (regex-escaped by the caller
            when it contains a dot).
        digits: Version shape to accept.

    Returns:
        A compiled pattern exposing a ``value`` group.
    """
    return re.compile(rf"(?<![A-Za-z]){name}{_SEP}v?(?P<value>{digits})(?![\d.])")


FACTS: tuple[Fact, ...] = (
    Fact(
        key="coverage_floor",
        label="backend coverage floor",
        source="apps/api/pyproject.toml + Taskfile.yml (--cov-fail-under)",
        resolve=_coverage_floor,
        # Only phrases that unambiguously name the ENFORCED FLOOR — a guarantee.
        # A measured percentage ("HITL services: ~75% coverage") is a different
        # statement and must stay free to differ; forcing the two to agree would
        # replace a real measurement with a threshold, which is the defect
        # ADR-185 forbids. Prose that cannot be told apart mechanically is
        # rewritten to be unambiguous instead of being pattern-matched.
        #
        # "plancher de couverture" and "ratchet couverture" are deliberately NOT
        # here: both introduce ADR narratives quoting the value of their day.
        pattern=re.compile(
            r"--cov-fail-under=(?P<value>\d+)"
            rf"|[Cc]overage (?:threshold|floor){_THRESHOLD_GAP}(?P<value2>\d+)\s*%"
            rf"|[Ss]euil de couverture{_THRESHOLD_GAP}(?P<value3>\d+)\s*%"
            rf"|[Cc]ouverture backend{_THRESHOLD_GAP}(?P<value4>\d+)\s*%"
            r"|[Cc]overage \((?P<value5>\d+)\s*%\)"
        ),
    ),
    Fact(
        key="python",
        label="Python version",
        source='apps/api/pyproject.toml (requires-python ">=3.14,<3.15")',
        resolve=_python_version,
        pattern=_version_pattern("Python", r"3\.\d+"),
        exemptions=(
            Exemption(
                path="docs/technical/CI_CD.md",
                value="3.10",
                reason=(
                    "ADR-215 installer floor: the self-host wizard must import under the "
                    "interpreter an OPERATOR's host ships, not ours. Proven by "
                    "scripts/install/tests_py310.py."
                ),
            ),
            Exemption(
                path="docs/technical/CI_CD.md",
                value="3.13",
                reason=(
                    "Narrative of the python-compat job RETIRED by ADR-241; the sentence "
                    "records the version that job used to run."
                ),
            ),
            Exemption(
                path="docs/guides/GUIDE_TESTING.md",
                value="3.13",
                reason="Same retired python-compat narrative as CI_CD.md (ADR-241).",
            ),
        ),
    ),
    Fact(
        key="node",
        label="Node.js major",
        source="package.json (engines.node)",
        resolve=_node_major,
        # ``Node.js`` in full: a bare ``Node`` is a graph node in this codebase
        # far more often than a runtime.
        pattern=_version_pattern(r"Node\.js", r"\d+"),
    ),
    Fact(
        key="next",
        label="Next.js",
        source="apps/web/package.json (dependencies.next)",
        resolve=_web_dependency("next"),
        pattern=_version_pattern(r"Next\.js"),
    ),
    Fact(
        key="react",
        label="React",
        source="apps/web/package.json (dependencies.react)",
        resolve=_web_dependency("react"),
        pattern=_version_pattern("React"),
    ),
    Fact(
        key="fastapi",
        label="FastAPI",
        source="apps/api/requirements.txt",
        resolve=_requirement("fastapi"),
        pattern=_version_pattern("FastAPI"),
    ),
    Fact(
        key="langgraph",
        label="LangGraph",
        source="apps/api/requirements.txt",
        resolve=_requirement("langgraph"),
        pattern=_version_pattern("LangGraph"),
    ),
    Fact(
        key="langchain",
        label="LangChain",
        source="apps/api/requirements.txt",
        resolve=_requirement("langchain"),
        pattern=_version_pattern("LangChain"),
    ),
    Fact(
        key="pydantic",
        label="Pydantic",
        source="apps/api/requirements.txt",
        resolve=_requirement("pydantic"),
        pattern=_version_pattern("Pydantic"),
    ),
    Fact(
        key="sqlalchemy",
        label="SQLAlchemy",
        source="apps/api/requirements.txt",
        resolve=_requirement("sqlalchemy"),
        pattern=_version_pattern("SQLAlchemy"),
    ),
    Fact(
        key="postgres",
        label="PostgreSQL major",
        source="docker-compose.prod.yml (pgvector image tag)",
        resolve=_compose_image_tag(re.compile(r"pgvector/pgvector:pg(?P<value>\d+)")),
        pattern=_version_pattern("PostgreSQL", r"\d+"),
        exemptions=(
            Exemption(
                path="docs/technical/STACK_TECHNIQUE.md",
                value="14",
                reason=(
                    "Third-party floor, not our deployment: langgraph-checkpoint-postgres "
                    "requires PostgreSQL 14+. A dependency's minimum is a different claim "
                    "from the major we run."
                ),
            ),
        ),
    ),
    Fact(
        key="redis",
        label="Redis",
        source="docker-compose.prod.yml (redis image tag)",
        resolve=_compose_image_tag(re.compile(r"image:\s*redis:(?P<value>\d+\.\d+)")),
        pattern=_version_pattern("Redis", r"\d+\.\d+"),
    ),
)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def resolve_facts(root: Path) -> dict[str, str]:
    """Recompute every fact from its source.

    Args:
        root: Repository root.

    Returns:
        Mapping of fact key to its current true value.

    Raises:
        SourceError: If any source is missing, unreadable or self-contradictory.
    """
    return {fact.key: fact.resolve(root) for fact in FACTS}


#: Alternative capture names one pattern may use for the same fact. ``re``
#: forbids reusing a group name inside one expression, so a fact accepting
#: several written shapes numbers them.
_VALUE_GROUPS = ("value", "value2", "value3", "value4", "value5")


def _matched_span(match: re.Match[str]) -> tuple[str, int, int]:
    """Return the captured value and its exact offsets in the scanned text.

    The offsets come from ``match.span(name)``, never from searching the value
    inside ``match.group(0)``: a version that also appears earlier in the match
    would make that search rewrite the wrong characters.

    Args:
        match: A match produced by a :class:`Fact` pattern.

    Returns:
        ``(value, start, end)``.

    Raises:
        SourceError: If the pattern matched without capturing any value group —
            a declaration bug, never a document's fault.
    """
    for name in _VALUE_GROUPS:
        try:
            captured = match.group(name)
        except IndexError:  # pragma: no cover - this pattern lacks that group
            continue
        if captured:
            start, end = match.span(name)
            return captured, start, end
    raise SourceError(f"pattern matched without capturing a value: {match.group(0)!r}")


def _lf_to_raw_offsets(raw: str) -> list[int]:
    """Map every offset of the LF-normalised text to its offset in ``raw``.

    The scan reads with universal newlines, so its offsets count one character
    per line break; the file on disk may spend two. Translating rather than
    round-tripping the whole document is what keeps a MIXED-newline file intact:
    ``docs/knowledge/02_chat.md`` holds 406 CRLF and 14 LF, and normalising it
    to a single detected style would rewrite fourteen lines nobody edited.

    Args:
        raw: The document exactly as stored, newlines untouched.

    Returns:
        ``mapping[i]`` is the raw offset of normalised offset ``i``; a final
        entry marks the end of the text so a span may finish there.
    """
    mapping: list[int] = []
    index = 0
    length = len(raw)
    while index < length:
        mapping.append(index)
        index += 2 if raw.startswith("\r\n", index) else 1
    mapping.append(length)
    return mapping


def rewrite_document(path: Path, edits: list[tuple[int, int, str]]) -> bool:
    """Apply ``(start, end, replacement)`` edits to one document, in place.

    Only the edited spans change: every other byte, newlines included, is
    written back exactly as it was read. 93 markdown files here carry CRLF and
    one mixes both styles, so a document-wide normalisation would produce a
    whole-file diff for a one-character correction. ``.gitattributes`` hides
    that in the index, but a contributor with ``core.autocrlf=false`` would see
    every line change.

    Args:
        path: Document to rewrite. Left untouched when the edits are rejected.
        edits: ``(start, end, replacement)`` spans, in any order. Offsets are
            **LF-based** — the numbering :func:`audit_facts` produces, since
            ``Path.read_text`` applies universal-newline translation. On a CRLF
            file the two numberings differ, so passing raw-byte offsets here
            would corrupt the document.

    Returns:
        True when the document changed on disk; False when every edit was a
        no-op, in which case the file's bytes are left strictly untouched.

    Raises:
        ValueError: If two spans overlap. Edits are applied back-to-front so
            earlier offsets stay valid; overlapping spans break that invariant
            and would splice the middle of a replacement. A writer that
            corrupts silently is worse than one that refuses.
    """
    ordered = sorted(edits, reverse=True)
    for (start, _end, _repl), (_prev_start, prev_end, _prev_repl) in zip(
        ordered, ordered[1:], strict=False
    ):
        if prev_end > start:
            raise ValueError(
                f"edits overlap at [{start}, {prev_end}) in {path.name}: applying them back-to-front would splice the middle of a replacement"
            )
    original = path.read_text(encoding="utf-8", newline="")
    offsets = _lf_to_raw_offsets(original)
    rebuilt = original
    for span_start, span_end, replacement in ordered:
        rebuilt = rebuilt[: offsets[span_start]] + replacement + rebuilt[offsets[span_end] :]
    if rebuilt == original:
        return False
    path.write_text(rebuilt, encoding="utf-8", newline="")
    return True


def audit_facts(root: Path, *, include_unstaged: bool = False) -> list[Occurrence]:
    """Find every quoted value of every fact across the LIVING documentation.

    Code fences and inline code are blanked out first — with one deliberate
    exception, the coverage flag, which only ever appears *inside* a fenced
    command and is unambiguous there. That exception is handled by scanning the
    raw text for that fact alone.

    Args:
        root: Repository root.
        include_unstaged: Preview the next commit rather than the git index —
            see :func:`doc_audit.tracked_paths`. Both instruments must accept
            it: a preview that only re-ran the navigation audit would clear a
            moved document's links while silently skipping the versions it
            quotes, which is a green run nobody should trust.

    Returns:
        Every occurrence found, drifted and correct alike, in document order.

    Raises:
        SourceError: Propagated from :func:`resolve_facts`.
    """
    expected = resolve_facts(root)
    tracked = tracked_paths(root, include_unstaged=include_unstaged)
    occurrences: list[Occurrence] = []

    for doc in doc_files(root, tracked):
        rel = doc.relative_to(root).as_posix()
        if classify_document(rel) != "LIVING" or rel in FACT_HISTORICAL:
            continue
        raw = doc.read_text(encoding="utf-8", errors="replace")
        prose = blank_code_regions(raw)
        for fact in FACTS:
            # The coverage flag is a command; every other fact is a claim in
            # prose, where a fenced example must not be read as documentation.
            # ``blank_code_regions`` preserves length, so an offset in ``prose``
            # is the same offset in ``raw`` — which is what lets the fixer edit
            # the spans recorded here instead of scanning again.
            haystack = raw if fact.key == "coverage_floor" else prose
            for match in fact.pattern.finditer(haystack):
                value, start, end = _matched_span(match)
                if fact.key == "coverage_floor" and value == _COVERAGE_DISABLED_SENTINEL:
                    continue
                occurrences.append(
                    Occurrence(
                        fact=fact.key,
                        path=rel,
                        line=haystack[:start].count("\n") + 1,
                        value=value,
                        expected=truncate_to_precision(expected[fact.key], value),
                        exempt=fact.exemption_for(rel, value) is not None,
                        start=start,
                        end=end,
                    )
                )
    return occurrences


def drifted(occurrences: list[Occurrence]) -> list[Occurrence]:
    """Filter the occurrences that state something untrue and are not exempt."""
    return [item for item in occurrences if item.value != item.expected and not item.exempt]


def fix_facts(root: Path, *, include_unstaged: bool = False) -> list[Occurrence]:
    """Rewrite every drifted occurrence to its source value.

    The fixer edits **exactly the spans** :func:`audit_facts` recorded — it does
    not scan again. A second scan with its own rules is how the two diverged:
    the audit blanked code fences and the fix did not, so ``--fix`` would have
    rewritten 18 occurrences inside fenced examples that the report never listed
    (measured 2026-08-27), including a ``max_connections`` discussion reading
    "PostgreSQL 10" and an OpenAPI "3.0" next to the word FastAPI.

    Exempt occurrences are never touched.

    Args:
        root: Repository root.

    Returns:
        The occurrences that were rewritten.
    """
    repaired: list[Occurrence] = []
    by_doc: dict[str, list[Occurrence]] = {}
    for item in drifted(audit_facts(root, include_unstaged=include_unstaged)):
        by_doc.setdefault(item.path, []).append(item)

    for rel, items in by_doc.items():
        edits = [(item.start, item.end, item.expected) for item in items]
        if rewrite_document(root / rel, edits):
            repaired.extend(items)
    return repaired


def main(argv: list[str]) -> int:
    """Report (or repair) documentation fact drift."""
    args = [arg for arg in argv[1:] if not arg.startswith("--")]
    root = Path(args[0]).resolve() if args else Path.cwd()
    include_unstaged = "--include-unstaged" in argv
    if not (root / "docs").is_dir():
        print(f"error: no docs/ directory under {root}", file=sys.stderr)
        return 2

    try:
        expected = resolve_facts(root)
    except SourceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if "--fix" in argv:
        repaired = fix_facts(root, include_unstaged=include_unstaged)
        for item in repaired:
            print(f"fixed {item.path}:{item.line}: {item.fact} {item.value} -> {item.expected}")
        print(f"\n{len(repaired)} occurrence(s) rewritten.")
        return 0

    occurrences = audit_facts(root, include_unstaged=include_unstaged)
    bad = drifted(occurrences)

    print("=== SOURCES OF TRUTH ===")
    for fact in FACTS:
        print(f"  {fact.label:<26} {expected[fact.key]:<10} <- {fact.source}")

    exempt = [item for item in occurrences if item.exempt]
    print(
        f"\n=== QUOTED OCCURRENCES: {len(occurrences)} "
        f"({len(exempt)} exempt, {len(bad)} drifted) ==="
    )
    for item in bad:
        print(
            f"{item.path}:{item.line}: {item.fact} quotes {item.value}, source is {item.expected}"
        )

    if bad:
        print(
            f"\n{len(bad)} documentation fact(s) drifted. Run `task docs:fix-facts` "
            "(or add an exemption with a written reason in scripts/audit/doc_facts.py).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
