"""Systemic guard: file-size ratchet — a logical file never grows, it shrinks.

The 2026-07 full-codebase audit measured 41 files >= 800 logical SLOC
concentrating 27% of the backend code, and proved that nothing structural
prevents growth: ADR-117 alone grew ``stream_chat`` from 335 to 412 SLOC and
``event_generator`` from 300 to 342. The ratchet mechanism has already proven
itself in this repository (backend coverage 43 -> 45, vitest thresholds locked
at 100% on the state machines) — this guard applies it to file size.

Mechanism (baseline: ``tests/unit/file_size_baseline.json``):

1. Every ``src/**/*.py`` file must stay under ``global_max_sloc`` (600 logical
   SLOC) — including every NEW file.
2. Files that already exceeded the ceiling when the baseline was created are
   grandfathered ("frozen") at their audited size +2% margin. They may shrink,
   never grow: after extracting code from a frozen file, run
   ``task ratchet:update`` to lower its cap (the script can ONLY lower caps
   and drop entries — see ``scripts/audit/update_file_size_baseline.py``).
3. Sizes are logical SLOC — tokenize + AST, excluding docstrings, comments and
   blank lines — computed by ``scripts/audit/measure_sloc.py``, the single
   source of truth shared with the audit protocol (raw line counts overstate
   code size by ~40% in this repository).
4. Data modules (``core/i18n_*``, ``core/config/``, ``core/constants``,
   ``domains/llm_config/constants``) are exempt, mirroring the audit's
   god-file scoring: they are declarative data (translation tables,
   configuration defaults) with near-zero cyclomatic complexity, their
   remediation lever is a format change rather than decomposition, and they
   grow legitimately with every feature (6 languages). The exemption list is
   imported from ``measure_sloc.py`` — one list, no drift.

Raising a cap or adding a frozen entry by hand in the JSON is an explicit,
reviewable decision that requires justification in the PR — do not weaken the
scan. Renaming a frozen file keeps its cap only if the JSON key is renamed in
the same change (visible diff); a deleted entry is never resurrected — a file
recreated at the same path starts back at the global ceiling.

Doctrine: docs/guides/GUIDE_DEVELOPPEMENT.md § "Taille des fichiers (doctrine
ratchet)".

Context: 2026-07 full-codebase audit ("god files" finding, B1).
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
SRC_DIR = Path(__file__).parents[2] / "src"
BASELINE_PATH = Path(__file__).parent / "file_size_baseline.json"
MEASURE_SLOC_PATH = REPO_ROOT / "scripts" / "audit" / "measure_sloc.py"

# Anti-rot: the scan must keep seeing the codebase (855 files as of 2026-07).
# A silent path/layout change dropping below this means the guard scans nothing.
MIN_EXPECTED_FILES = 500


def _load_measure_sloc() -> ModuleType:
    """Load the canonical SLOC counter shared with the audit protocol.

    The guard deliberately imports ``scripts/audit/measure_sloc.py`` (repo
    root) instead of duplicating the counter: the sizes it enforces are the
    sizes the public audit report publishes, by construction. The import fails
    loudly on a partial checkout — pre-commit (host) and CI (runner) always
    have the full repository.

    Returns:
        The loaded ``measure_sloc`` module.
    """
    assert MEASURE_SLOC_PATH.is_file(), (
        f"measure_sloc.py not found at {MEASURE_SLOC_PATH} — the file-size ratchet "
        "guard needs the full repository checkout (scripts/audit/)."
    )
    spec = importlib.util.spec_from_file_location("measure_sloc", MEASURE_SLOC_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {MEASURE_SLOC_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_measure_sloc = _load_measure_sloc()


def _sloc_of_source(source: str) -> int | None:
    """Logical SLOC of a source string, or None when it cannot be parsed."""
    result = _measure_sloc.code_lines(source)
    return None if result is None else len(result[0])


def _load_baseline() -> dict:
    """Parse the baseline JSON (structure validated by TestBaselineIntegrity)."""
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _src_files() -> list[Path]:
    """Every Python file of the production tree, sorted for stable output."""
    return sorted(SRC_DIR.rglob("*.py"))


class TestSlocCounterSanity:
    """Sanity checks on the imported SLOC counter (guards against scan rot)."""

    def test_counter_excludes_docstrings_comments_and_blanks(self) -> None:
        """The counter must count logical lines only, on a synthetic snippet."""
        snippet = (
            '"""Module docstring.\n'
            "\n"
            "Two lines of prose that must not count.\n"
            '"""\n'
            "\n"
            "# a comment that must not count\n"
            "\n"
            "\n"
            "def f(a, b):\n"
            '    """Function docstring — must not count."""\n'
            "    total = (\n"
            "        a\n"
            "        + b\n"
            "    )\n"
            "    return total\n"
        )
        # Logical lines: def (9), the 4 physical lines of the multi-line
        # assignment (11-14), return (15).
        assert _sloc_of_source(snippet) == 6, (
            "The SLOC counter imported from scripts/audit/measure_sloc.py no longer "
            "counts the synthetic snippet as expected — its semantics changed. Fix "
            "the counter (or re-baseline consciously) before trusting the guard."
        )

    def test_counter_returns_none_on_unparsable_source(self) -> None:
        """Unparsable sources must surface as None (reported as violations)."""
        assert _sloc_of_source("def broken(:\n") is None

    def test_data_module_exemption_sentinels(self) -> None:
        """The exemption predicate must match the audit's data modules exactly."""
        is_data = _measure_sloc.is_data_module
        assert is_data("core/i18n_v3.py")
        assert is_data("core/config/agents.py")
        assert is_data("core/constants.py")
        assert is_data("domains/llm_config/constants.py")
        assert not is_data("domains/agents/nodes/response_node.py")
        assert not is_data("core/exceptions.py")


class TestBaselineIntegrity:
    """Sanity checks on the baseline file itself (guards against baseline rot)."""

    def test_baseline_structure(self) -> None:
        """The baseline must carry a positive global ceiling and int caps."""
        baseline = _load_baseline()
        global_max = baseline["global_max_sloc"]
        frozen = baseline["frozen"]
        assert isinstance(global_max, int) and global_max > 0
        assert isinstance(frozen, dict)
        bad = {k: v for k, v in frozen.items() if not isinstance(v, int) or v <= 0}
        assert not bad, f"non-integer or non-positive frozen caps: {bad}"

    def test_frozen_entries_point_to_existing_files(self) -> None:
        """Guard against stale entries (deleted/renamed files keeping a cap).

        A stale entry is dangerous: a NEW file later created at that path would
        silently inherit a huge cap. Deleting a frozen file must drop its entry
        (``task ratchet:update`` does it); renaming one must rename the key.
        """
        frozen: dict[str, int] = _load_baseline()["frozen"]
        stale = sorted(rel for rel in frozen if not (SRC_DIR / rel).is_file())
        assert not stale, (
            "Stale frozen entries in file_size_baseline.json (file deleted or "
            "renamed) — run `task ratchet:update`, or rename the JSON key if the "
            "file moved:\n  - " + "\n  - ".join(stale)
        )

    def test_frozen_caps_stay_above_global_ceiling(self) -> None:
        """A frozen cap <= the global ceiling is dead weight — drop the entry."""
        baseline = _load_baseline()
        global_max: int = baseline["global_max_sloc"]
        redundant = {k: v for k, v in baseline["frozen"].items() if v <= global_max}
        assert not redundant, (
            f"Frozen caps at or under the global ceiling ({global_max}) are redundant "
            f"— run `task ratchet:update` to drop them: {redundant}"
        )

    def test_frozen_entries_are_not_data_modules(self) -> None:
        """Data modules are exempt — freezing one is a baseline mistake."""
        frozen: dict[str, int] = _load_baseline()["frozen"]
        misfrozen = sorted(rel for rel in frozen if _measure_sloc.is_data_module(rel))
        assert not misfrozen, (
            "Frozen entries for exempt data modules (remove them from the "
            "baseline):\n  - " + "\n  - ".join(misfrozen)
        )

    def test_scan_sees_the_codebase(self) -> None:
        """Guard against path rot silently shrinking the scan to nothing."""
        count = len(_src_files())
        assert count >= MIN_EXPECTED_FILES, (
            f"Only {count} files found under {SRC_DIR} (expected >= "
            f"{MIN_EXPECTED_FILES}) — the scan path is broken, fix it before "
            "trusting the guard."
        )


class TestFileSizeRatchet:
    """CI guard: any logical file growing past its cap fails the build."""

    def test_no_file_exceeds_its_cap(self) -> None:
        """Scan all production files against the global ceiling / frozen caps."""
        baseline = _load_baseline()
        global_max: int = baseline["global_max_sloc"]
        frozen: dict[str, int] = baseline["frozen"]

        violations: list[str] = []
        for py_file in _src_files():
            rel = py_file.relative_to(SRC_DIR).as_posix()
            if _measure_sloc.is_data_module(rel):
                continue
            cap = frozen.get(rel, global_max)
            source = py_file.read_text(encoding="utf-8", errors="replace")
            # Performance pre-filter: logical SLOC <= raw line count, so a file
            # whose raw count fits its cap cannot violate — only ~1/5 of the
            # tree gets tokenized (keeps the guard well under the 5s budget).
            if source.count("\n") + 1 <= cap:
                continue
            sloc = _sloc_of_source(source)
            if sloc is None:
                violations.append(f"src/{rel}: unparsable (tokenize/AST failed) — fix the file")
            elif sloc > cap:
                violations.append(f"src/{rel}: {sloc} logical SLOC > cap {cap} (+{sloc - cap})")

        if violations:
            pytest.fail(
                "File-size ratchet exceeded — a logical file never grows: extract "
                "instead.\n" + "\n".join(f"  - {v}" for v in violations) + "\n\nHow to fix:\n"
                f"  1. Extract cohesive units (a class, a tool family, a section) into "
                f"a new module — new files must stay under {global_max} logical SLOC "
                "(docstrings/comments/blanks do not count).\n"
                "  2. After shrinking a frozen file, run `task ratchet:update` so its "
                "cap follows it down (caps only go down, never up).\n"
                "  3. Raising a cap in tests/unit/file_size_baseline.json is an "
                "explicit, reviewable decision requiring justification in the PR.\n"
                "Doctrine: docs/guides/GUIDE_DEVELOPPEMENT.md § 'Taille des fichiers "
                "(doctrine ratchet)'."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
