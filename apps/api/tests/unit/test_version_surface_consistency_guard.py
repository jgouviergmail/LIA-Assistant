"""Guard: every release surface carries the canonical version and count.

Why
---
The release version and the counts quoted on public surfaces used to be
propagated by hand across a dozen files. Every miss drifted silently for weeks:

- ``story.*`` guides stranded at v1.21.17 (caught by the user, not by CI);
- ``docs/GETTING_STARTED.md`` stranded at v1.21.21;
- ``apps/api/pyproject.toml`` stranded at 1.21.9 while 1.24.0 shipped (F030,
  which produced the narrower :mod:`test_version_drift_guard`);
- ``LANDING_STATS.adrs`` stranded at 183 from v1.27.0 to v1.27.4;
- ``LANDING_STATS.releases`` showing 129 for 130 real entries.

Every one of those is mechanically checkable, so none of them belongs in a
human checklist. This guard is the mechanical owner of that class; the release
skill/procedure must not re-list what is verified here.

Design
------
The surface table lives in ``scripts/release/version_surfaces.py`` and is shared
with ``scripts/release/bump_surfaces.py``: what a release writes and what CI
verifies come from ONE declaration, the same reason the file-size ratchet
imports ``scripts/audit/measure_sloc.py`` instead of re-implementing it.

Two deliberate non-goals, both documented in that module:

- ``LANDING_STATS.tests`` is a real measurement, not a derivation — asserting a
  number nobody measured is exactly the defect ADR-185 forbids;
- ``LAST_UPDATED``, the README theme sentence and the ``Re-measured at vX.Y.Z``
  comments are editorial or historical; rewriting them would state something
  untrue.

Relationship to :mod:`test_version_drift_guard`: that guard is the F030 manifest
contract (three manifests agree) with its own message; this one covers the whole
surface map, manifests included, against the same single source of truth. Both
compare to the root ``package.json``, so they cannot disagree.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
VERSION_SURFACES_PATH = REPO_ROOT / "scripts" / "release" / "version_surfaces.py"

pytestmark = pytest.mark.unit


#: Import name for the out-of-tree module. Namespaced so it can never collide
#: with a real package: the module MUST be registered in ``sys.modules`` before
#: execution, because ``@dataclass`` resolves its annotations through
#: ``sys.modules[cls.__module__].__dict__`` (Python 3.12+; on 3.14 an
#: unregistered module raises ``AttributeError: 'NoneType' object has no
#: attribute '__dict__'`` at import time).
_MODULE_NAME = "_lia_release_version_surfaces"


def _load_version_surfaces() -> ModuleType:
    """Load the canonical surface declaration shared with the bump script.

    Returns:
        The loaded ``version_surfaces`` module.
    """
    cached = sys.modules.get(_MODULE_NAME)
    if cached is not None:
        return cached

    assert VERSION_SURFACES_PATH.is_file(), (
        f"version_surfaces.py not found at {VERSION_SURFACES_PATH} — this guard "
        "needs the full repository checkout (scripts/release/)."
    )
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, VERSION_SURFACES_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {VERSION_SURFACES_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception:  # pragma: no cover - failed import must not leave a stub
        del sys.modules[_MODULE_NAME]
        raise
    return module


_surfaces = _load_version_surfaces()

#: The six locales every stamped guide family must cover (frontend codes: ``zh``
#: here, ``zh-CN`` on the backend — see CLAUDE.md).
LOCALES: tuple[str, ...] = ("en", "fr", "de", "es", "it", "zh")


class TestScanSanity:
    """Anti-rot: the scan must keep seeing the real surfaces."""

    def test_discovery_finds_at_least_the_known_stamps(self) -> None:
        """A layout change that makes discovery scan nothing must fail here."""
        stamps = _surfaces.discover_guide_stamps(REPO_ROOT)
        tracked = [stamp for stamp in stamps if stamp.tracked]

        assert len(tracked) >= _surfaces.MIN_EXPECTED_GUIDE_STAMPS, (
            f"Only {len(tracked)} tracked guide stamps discovered under "
            f"{_surfaces.GUIDES_DIR} (expected at least "
            f"{_surfaces.MIN_EXPECTED_GUIDE_STAMPS}). Either the stamp format "
            "changed or the scan is looking at the wrong place."
        )

    def test_every_stamped_family_covers_the_six_locales(self) -> None:
        """A missing locale file is a missing translation, not a missing stamp."""
        stamps = _surfaces.discover_guide_stamps(REPO_ROOT)
        seen: dict[str, set[str]] = {}
        for stamp in stamps:
            if not stamp.tracked:
                continue
            name = stamp.path.rsplit("/", 1)[-1]  # how.fr.md
            stem, locale = name.split(".")[0], name.split(".")[1]
            seen.setdefault(stem, set()).add(locale)

        for stem in _surfaces.STAMPED_GUIDE_STEMS:
            assert seen.get(stem) == set(LOCALES), (
                f"Guide family {stem!r} is stamped in {sorted(seen.get(stem, ()))} "
                f"but must cover exactly {sorted(LOCALES)}."
            )

    def test_every_exemption_carries_a_written_reason(self) -> None:
        """An exemption without a reason is an oversight waiting to be swept."""
        for stem, reason in _surfaces.EXEMPT_GUIDE_STEMS.items():
            assert reason.strip(), f"Exemption {stem!r} has no written reason."

    def test_exempt_stamps_still_exist(self) -> None:
        """If the exempt guides lost their stamp, the exemption is dead code."""
        stamps = _surfaces.discover_guide_stamps(REPO_ROOT)
        exempt_stems = {stamp.stem for stamp in stamps if not stamp.tracked}

        assert exempt_stems == set(_surfaces.EXEMPT_GUIDE_STEMS), (
            "The exempt-stamp set drifted: discovered "
            f"{sorted(exempt_stems)} vs declared "
            f"{sorted(_surfaces.EXEMPT_GUIDE_STEMS)}. Remove the stale exemption "
            "or restore the stamp."
        )


class TestVersionSurfaces:
    """Every tracked surface equals the canonical version."""

    def test_all_surfaces_carry_the_canonical_version(self) -> None:
        canonical = _surfaces.canonical_version(REPO_ROOT)
        drifted = [
            item for item in _surfaces.version_occurrences(REPO_ROOT) if item.version != canonical
        ]

        assert not drifted, (
            f"Release-version drift (canonical = {canonical} from root "
            "package.json). Run `task release:bump -- <version>`:\n"
            + "\n".join(
                f"  {item.path}:{item.line} — {item.label} carries {item.version}"
                for item in drifted
            )
        )

    def test_no_stamped_guide_is_unclassified(self) -> None:
        """A new stamped guide must be declared tracked or exempt, explicitly."""
        try:
            _surfaces.version_occurrences(REPO_ROOT)
        except _surfaces.UnknownStampError as error:  # pragma: no cover - failure path
            pytest.fail(str(error))


class TestDerivedCounts:
    """Public counts equal their source, recomputed — never carried over."""

    def test_quoted_counts_match_their_sources(self) -> None:
        counts = _surfaces.derived_counts(REPO_ROOT)
        stale = [
            item
            for item in _surfaces.count_occurrences(REPO_ROOT)
            if item.value != counts[item.source]
        ]

        assert not stale, "Derived-count drift. Run `task release:sync-counts`:\n" + "\n".join(
            f"  {item.path}:{item.line} — {item.label} quotes {item.value}, "
            f"source {item.source} is {counts[item.source]}"
            for item in stale
        )

    def test_sources_are_plausible(self) -> None:
        """Guard the guard: an empty source would make every quote 'match'."""
        counts = _surfaces.derived_counts(REPO_ROOT)

        assert counts["adr_files"] >= 200, "ADR scan found implausibly few files"
        assert counts["adr_latest"] >= counts["adr_files"], (
            "The highest ADR number cannot be below the file count "
            "(ADR-008 has no separate file, so it runs one above)."
        )
        assert counts["changelog_releases"] >= 200, "CHANGELOG scan found too few entries"
