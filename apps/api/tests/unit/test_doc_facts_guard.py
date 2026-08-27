"""Guard: no document states a version or threshold its source contradicts.

Why
---
``doc_audit.py`` proves the documentation *navigates* correctly. Nothing proved
it was *true*. Measured on 2026-08-27, on a tree where ``task lint:docs`` was
green and every other gate passed:

- the backend coverage floor is ``67`` in the two files that own it, and six
  documents stated it — 60, 62, 43, 45, 65 and 80, all wrong, all different.
  ``docs/technical/CI_CD.md`` additionally certified the value had "une seule
  source de verite" while quoting the wrong one;
- ``docs/guides/GUIDE_TESTING.md`` contradicted *itself* eleven lines apart
  (a gate of 62 % in one paragraph, >= 67 % in the next table);
- LangGraph was quoted as 1.1.6 in four documents and 1.0.4 in two more against
  a pinned 1.2.11; Next.js as 16.2.10 against 16.2.11; FastAPI as 0.135.1
  against 0.136.3;
- ``AGENTS.md`` — the instruction file a second AI agent reads and acts on —
  was outside every scan and claimed a 43 % floor.

Every one of those is mechanically checkable, so none of them belongs in a
human review. This guard is the mechanical owner of that class.

Design
------
The registry lives in ``scripts/audit/doc_facts.py`` and is shared with
``task lint:docs`` and ``task docs:fix-facts``: what CI verifies and what the
fixer rewrites come from ONE declaration — the same reason the file-size ratchet
imports ``measure_sloc.py`` instead of re-implementing it.

The ``TestScanSanity`` class exists because of the failure mode found next door:
``test_task_ci_pytest_parity_guard::test_coverage_threshold_has_a_single_source_of_truth``
had been comparing an empty list since ADR-151 moved the pytest commands out of
``ci.yml``. A guard that scans nothing passes forever. These tests fail instead.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
DOC_FACTS_PATH = REPO_ROOT / "scripts" / "audit" / "doc_facts.py"

pytestmark = pytest.mark.unit

#: Import name for the out-of-tree module. Namespaced so it can never collide
#: with a real package, and registered in ``sys.modules`` BEFORE execution
#: because ``@dataclass`` resolves its annotations through
#: ``sys.modules[cls.__module__].__dict__`` (on Python 3.14 an unregistered
#: module raises ``AttributeError: 'NoneType' object has no attribute
#: '__dict__'`` at import time). Same plumbing as the version-surface guard.
_MODULE_NAME = "_lia_audit_doc_facts"

#: Anti-rot floor for the real repository. Measured at 95 tracked occurrences on
#: 2026-08-27; a scan that suddenly sees a handful is broken, not clean.
MIN_EXPECTED_OCCURRENCES = 60


def _load_doc_facts() -> ModuleType:
    """Load the canonical fact registry shared with the linter and the fixer.

    Returns:
        The loaded ``doc_facts`` module.
    """
    cached = sys.modules.get(_MODULE_NAME)
    if cached is not None:
        return cached

    if not DOC_FACTS_PATH.is_file():
        pytest.skip("guard needs the full repository checkout (scripts/audit/doc_facts.py).")
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, DOC_FACTS_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {DOC_FACTS_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception:  # pragma: no cover - a failed import must not leave a stub
        del sys.modules[_MODULE_NAME]
        raise
    return module


_facts = _load_doc_facts()


class TestSourcesOfTruth:
    """Every fact must resolve to a plausible value from a real file."""

    def test_every_fact_resolves(self) -> None:
        """A source that cannot be read must fail loudly, never default to ''."""
        try:
            resolved = _facts.resolve_facts(REPO_ROOT)
        except _facts.SourceError as error:  # pragma: no cover - failure path
            pytest.fail(str(error))

        assert set(resolved) == {fact.key for fact in _facts.FACTS}
        for key, value in resolved.items():
            assert value and value[0].isdigit(), (
                f"fact {key!r} resolved to {value!r}, which is not a version or "
                "threshold. An empty source would make every quotation 'match'."
            )

    def test_coverage_floor_owners_agree(self) -> None:
        """pyproject and the Taskfile own one number between them, not two."""
        floor = _facts.resolve_facts(REPO_ROOT)["coverage_floor"]

        assert floor.isdigit() and 0 < int(floor) <= 100, f"implausible floor {floor!r}"

    def test_fact_keys_are_unique(self) -> None:
        """A duplicated key would silently shadow one fact's expectations."""
        keys = [fact.key for fact in _facts.FACTS]

        assert len(keys) == len(set(keys)), f"duplicate fact keys: {keys}"


class TestScanSanity:
    """Anti-rot: a guard that scans nothing passes forever (see module docstring)."""

    def test_the_scan_still_sees_the_documentation(self) -> None:
        """A layout or classification change that empties the scan must fail here."""
        occurrences = _facts.audit_facts(REPO_ROOT)

        assert len(occurrences) >= MIN_EXPECTED_OCCURRENCES, (
            f"only {len(occurrences)} quoted facts discovered (expected at least "
            f"{MIN_EXPECTED_OCCURRENCES}). Either the patterns stopped matching or "
            "the scan is looking at the wrong place."
        )

    def test_the_root_documents_are_in_the_scan_base(self) -> None:
        """CONTRIBUTING.md and AGENTS.md were outside every scan until 2026-08-27."""
        scanned = {item.path for item in _facts.audit_facts(REPO_ROOT)}

        for required in ("README.md", "CONTRIBUTING.md", "AGENTS.md", "CLAUDE.md"):
            assert required in scanned, (
                f"{required} quotes no tracked fact, which means it left the scan "
                "base or stopped describing the stack. Both are regressions."
            )

    def test_several_distinct_facts_are_actually_exercised(self) -> None:
        """One fact matching everywhere would hide eleven silently-dead patterns."""
        seen = {item.fact for item in _facts.audit_facts(REPO_ROOT)}

        assert len(seen) >= 8, (
            f"only {sorted(seen)} are quoted anywhere. A pattern that matches "
            "nothing verifies nothing — check it before trusting this guard."
        )


class TestExemptions:
    """An exemption is a written decision, not a way to silence the guard."""

    def test_every_exemption_carries_a_written_reason(self) -> None:
        for fact in _facts.FACTS:
            for exemption in fact.exemptions:
                assert exemption.reason.strip(), (
                    f"exemption {fact.key}/{exemption.path}/{exemption.value} has "
                    "no written reason."
                )

    def test_every_exemption_is_still_live(self) -> None:
        """A stale exemption hides the next real drift in the same file."""
        live = {(item.fact, item.path, item.value) for item in _facts.audit_facts(REPO_ROOT)}
        dead = [
            f"{fact.key}/{exemption.path}/{exemption.value}"
            for fact in _facts.FACTS
            for exemption in fact.exemptions
            if (fact.key, exemption.path, exemption.value) not in live
        ]

        assert not dead, (
            f"these exemptions no longer match anything: {dead}. Remove them — a "
            "dead exemption is a blanket over whatever appears there next."
        )

    def test_every_fact_historical_entry_exists_and_is_justified(self) -> None:
        for path, reason in _facts.FACT_HISTORICAL.items():
            assert reason.strip(), f"FACT_HISTORICAL[{path!r}] has no written reason."
            assert (REPO_ROOT / path).is_file(), (
                f"FACT_HISTORICAL names {path}, which does not exist. Remove the "
                "entry or restore the document."
            )


class TestPrecision:
    """A document chooses its precision; it may not be precise and wrong."""

    @pytest.mark.parametrize(
        ("expected", "quoted", "want"),
        [
            ("1.2.11", "1", "1"),
            ("1.2.11", "1.2", "1.2"),
            ("1.2.11", "1.2.11", "1.2.11"),
            ("16.2.11", "16", "16"),
            ("3.14", "3.14", "3.14"),
            ("67", "67", "67"),
        ],
    )
    def test_truncation_matches_the_quoted_depth(
        self, expected: str, quoted: str, want: str
    ) -> None:
        assert _facts.truncate_to_precision(expected, quoted) == want

    def test_a_wrong_minor_is_still_caught(self) -> None:
        """ "LangGraph 1.0" against a pinned 1.2.11 is a false claim, not a loose one."""
        assert _facts.truncate_to_precision("1.2.11", "1.0") == "1.2" != "1.0"


class TestFixerMatchesAuditor:
    """The fixer must rewrite exactly what the report lists — no more.

    Found by code review, 2026-08-27, and measured before being fixed: the two
    functions scanned DIFFERENT text. ``audit_facts`` blanks code fences for
    every fact except the coverage floor; ``fix_facts`` re-scanned the raw
    document for all of them. 18 occurrences inside fenced examples were
    therefore invisible to the report and would have been rewritten by
    ``task docs:fix-facts`` — including "PostgreSQL 10" in a ``max_connections``
    discussion and "FastAPI 3.0" where the 3.0 belongs to OpenAPI.

    A second scan with its own rules is the very defect this module exists to
    catch, committed inside the module itself. The fix is structural: one scan,
    and the fixer edits the spans that scan recorded.
    """

    def test_the_fixer_touches_only_reported_occurrences(self) -> None:
        occurrences = _facts.audit_facts(REPO_ROOT)
        reported = {(item.path, item.fact, item.start, item.end) for item in occurrences}
        planned = {
            (item.path, item.fact, item.start, item.end) for item in _facts.drifted(occurrences)
        }

        assert planned <= reported, (
            "the fixer would edit spans the report never listed: " f"{sorted(planned - reported)}"
        )

    def test_every_occurrence_span_points_at_its_own_value(self) -> None:
        """A wrong span would rewrite neighbouring text instead of the value."""
        mismatched: list[str] = []
        for item in _facts.audit_facts(REPO_ROOT):
            raw = (REPO_ROOT / item.path).read_text(encoding="utf-8", errors="replace")
            if raw[item.start : item.end] != item.value:
                mismatched.append(
                    f"{item.path}:{item.line} span holds {raw[item.start:item.end]!r}, "
                    f"value is {item.value!r}"
                )

        assert not mismatched, "\n".join(mismatched)


class TestFixerSafety:
    """Rewriting must change the value and nothing else."""

    def test_fix_preserves_crlf_line_endings(self, tmp_path: Path) -> None:
        """93 markdown files carry CRLF; a fix must not rewrite every line.

        Offsets are LF-based by contract — that is what ``audit_facts`` records,
        because ``Path.read_text`` applies universal-newline translation. This
        test pins that contract on a CRLF file, where the two numberings differ.
        """
        document = tmp_path / "README.md"
        document.write_bytes(b"# T\r\n\r\nBuilt on LangGraph 1.1.6 here.\r\n")
        start = "# T\n\nBuilt on LangGraph ".index("LangGraph ") + len("LangGraph ")

        rewritten = _facts.rewrite_document(document, [(start, start + len("1.1.6"), "1.2.11")])

        assert rewritten is True
        content = document.read_bytes()
        assert b"\r\n" in content, "CRLF was flattened to LF"
        assert b"LangGraph 1.2.11 here." in content
        assert content.count(b"\r\n") == 3, "line count or endings changed"

    def test_fix_preserves_a_lf_document_as_lf(self, tmp_path: Path) -> None:
        document = tmp_path / "README.md"
        document.write_bytes(b"# T\n\nLangGraph 1.1.6\n")
        start = len("# T\n\nLangGraph ")

        _facts.rewrite_document(document, [(start, start + len("1.1.6"), "1.2.11")])

        content = document.read_bytes()
        assert b"\r\n" not in content, "LF document gained CRLF"
        assert b"LangGraph 1.2.11" in content

    def test_a_mixed_newline_document_keeps_every_line_as_it_was(self, tmp_path: Path) -> None:
        """One document here mixes CRLF and LF (docs/knowledge/02_chat.md).

        Round-tripping through a single detected style would rewrite the 14 LF
        lines it contains - a spurious diff on lines nobody edited. Only the
        edited span may change.
        """
        document = tmp_path / "README.md"
        before = b"# T\r\n\nLangGraph 1.1.6\r\nkept\ntail\r\n"
        after = b"# T\r\n\nLangGraph 1.2.11\r\nkept\ntail\r\n"
        document.write_bytes(before)
        start = len("# T\n\nLangGraph ")

        _facts.rewrite_document(document, [(start, start + len("1.1.6"), "1.2.11")])

        assert document.read_bytes() == after

    def test_overlapping_edits_are_refused(self, tmp_path: Path) -> None:
        """A writer that silently corrupts is worse than one that refuses.

        Edits are applied back-to-front so earlier offsets stay valid; two spans
        that overlap break that invariant and would splice the middle of a
        replacement. No caller produces them today (one regex match cannot
        overlap itself, and the facts match different words), but the function
        is public and writes to disk — it must fail loudly, not corrupt.
        """
        document = tmp_path / "README.md"
        document.write_bytes(b"LangGraph 1.1.6\n")
        before = document.read_bytes()

        with pytest.raises(ValueError, match="overlap"):
            _facts.rewrite_document(document, [(10, 15, "1.2.11"), (12, 14, "X")])

        assert document.read_bytes() == before, "the document was touched anyway"

    def test_repository_occurrences_never_overlap(self) -> None:
        """The invariant the fixer relies on, checked against the real corpus."""
        by_doc: dict[str, list[tuple[int, int]]] = {}
        for item in _facts.audit_facts(REPO_ROOT):
            by_doc.setdefault(item.path, []).append((item.start, item.end))

        clashes = []
        for path, spans in by_doc.items():
            ordered = sorted(spans)
            for (a_start, a_end), (b_start, b_end) in zip(ordered, ordered[1:], strict=False):
                if b_start < a_end:
                    clashes.append(f"{path}: ({a_start},{a_end}) overlaps ({b_start},{b_end})")

        assert not clashes, chr(10).join(clashes)

    def test_a_no_op_edit_leaves_the_file_untouched(self, tmp_path: Path) -> None:
        """Rewriting to the same value must not rewrite the file's bytes."""
        document = tmp_path / "README.md"
        document.write_bytes(b"# T\r\n\r\nLangGraph 1.2.11\r\n")
        before = document.read_bytes()
        start = len("# T\n\nLangGraph ")

        rewritten = _facts.rewrite_document(document, [(start, start + 6, "1.2.11")])

        assert rewritten is False
        assert document.read_bytes() == before


class TestSourceResolution:
    """The floor's owners may legitimately carry the disable sentinel."""

    def test_the_disable_sentinel_never_makes_the_source_ambiguous(self) -> None:
        """``--cov-fail-under=0`` in a targeted task must not break resolution.

        It means "no gate on this run", never "the floor is zero". Reading it as
        a second floor value would abort the whole `lint:docs` for an unrelated
        Taskfile edit.
        """
        assert _facts.floor_values("pytest --cov-fail-under=67 x\npytest --cov-fail-under=0 y") == {
            "67"
        }

    def test_two_real_floors_still_conflict(self) -> None:
        """Guard the guard: filtering the sentinel must not hide a real drift."""
        assert _facts.floor_values("a --cov-fail-under=67\nb --cov-fail-under=64") == {"64", "67"}


class TestStagedPreview:
    """The preview must cover BOTH instruments, or it answers half the question.

    ``doc_audit`` and ``doc_facts`` share the same scan base, so both resolve
    existence from the git index. A preview that only re-ran the navigation
    audit would clear the links of a moved document while silently skipping the
    versions it quotes — the exact partial answer that makes a developer trust a
    green run they should not.
    """

    def test_audit_facts_accepts_the_preview_flag(self) -> None:
        occurrences = _facts.audit_facts(REPO_ROOT, include_unstaged=True)

        assert occurrences, "the preview scan found nothing at all"

    def test_the_preview_sees_documents_the_index_does_not(self, tmp_path: Path) -> None:
        """An unstaged document's quoted facts must be checked by the preview."""
        scanned_default = {item.path for item in _facts.audit_facts(REPO_ROOT)}
        scanned_preview = {
            item.path for item in _facts.audit_facts(REPO_ROOT, include_unstaged=True)
        }

        assert scanned_default <= scanned_preview, (
            "the preview must be a superset of the index verdict, never a "
            f"different set: {sorted(scanned_default - scanned_preview)}"
        )


class TestRepository:
    """The real assertion: the documentation tells the truth."""

    def test_no_document_contradicts_its_source(self) -> None:
        drifted = _facts.drifted(_facts.audit_facts(REPO_ROOT))

        assert not drifted, (
            "Documentation fact drift. Run `task docs:fix-facts`, or add an "
            "exemption with a written reason in scripts/audit/doc_facts.py:\n"
            + "\n".join(
                f"  {item.path}:{item.line} — {item.fact} quotes {item.value}, "
                f"source is {item.expected}"
                for item in drifted
            )
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
