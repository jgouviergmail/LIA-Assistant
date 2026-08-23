"""Release version-surface declaration, discovery, and rewriting.

What must hold:

- the canonical version is the root ``package.json`` and nothing else;
- every *tracked* surface (guide stamps, GETTING_STARTED, README, manifests)
  is read through ONE declaration shared by the CI guard and the bump script,
  so the two can never disagree about what a release must touch;
- guide stamps are DISCOVERED, not listed: a stamp that is neither tracked nor
  explicitly exempted is reported, so a guide added tomorrow reddens the build
  instead of drifting in silence (the failure mode this whole module exists to
  kill — ``story.*`` was stranded at v1.21.17, ``GETTING_STARTED`` at
  v1.21.21, ``pyproject.toml`` at 1.21.9);
- exemptions are named with a reason (``privacy.*``/``terms.*`` carry a
  deliberately frozen contractual stamp);
- derived counts (ADR files, latest ADR number, CHANGELOG entries) are checked
  against their SOURCE, never carried over from the previous release;
- rewriting is byte-preserving: only the matched group is replaced, so CRLF,
  encoding, and every surrounding character survive untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.version_surfaces import (  # noqa: E402
    EXEMPT_GUIDE_STEMS,
    GUIDES_DIR,
    STAMPED_GUIDE_STEMS,
    CountOccurrence,
    Occurrence,
    SurfaceError,
    UnknownStampError,
    bump_version_surfaces,
    canonical_version,
    count_occurrences,
    derived_counts,
    discover_guide_stamps,
    read_last_updated,
    set_last_updated,
    sync_derived_counts,
    version_occurrences,
)

pytestmark = pytest.mark.unit


def _write(path: Path, text: str, *, newline: str = "\n") -> None:
    """Write ``text`` with explicit line endings (no platform translation)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline=newline) as handle:
        handle.write(text)


def _fake_repo(tmp_path: Path, version: str = "1.31.2") -> Path:
    """Build a minimal repository carrying one occurrence of every surface."""
    root = tmp_path / "repo"

    _write(root / "package.json", '{\n  "name": "lia",\n  "version": "%s"\n}\n' % version)
    _write(
        root / "apps" / "web" / "package.json",
        '{\n  "name": "web",\n  "version": "%s"\n}\n' % version,
    )
    _write(
        root / "apps" / "api" / "pyproject.toml",
        '[project]\nname = "lia-api"\nversion = "%s"\n' % version,
    )
    _write(
        root / "apps" / "web" / "public" / "firebase-messaging-sw.js",
        "const CACHE_VERSION = '%s';\n" % version,
    )

    guides = root / "apps" / "web" / "src" / "data" / "guides"
    # The six localized label/separator shapes actually used by the guides.
    _write(guides / "how.en.md", "# How\n\n**Application**: LIA v%s\n" % version)
    _write(guides / "how.fr.md", "# How\n\n**Application** : LIA v%s\n" % version)
    _write(guides / "why.de.md", "# Why\n\n**Anwendung**: LIA v%s\n" % version)
    _write(guides / "why.es.md", "# Why\n\n**Aplicación**: LIA v%s\n" % version)
    _write(guides / "story.it.md", "# Story\n\n**Applicazione**: LIA v%s\n" % version)
    _write(guides / "story.zh.md", "# Story\n\n**应用**：LIA v%s\n" % version)
    # Deliberately frozen contractual stamps — must never follow the release.
    _write(guides / "privacy.fr.md", "# Privacy\n\n**Application** : LIA v1.14.2\n")
    _write(guides / "terms.en.md", "# Terms\n\n**Application**: LIA v1.14.2\n")

    _write(
        root / "apps" / "web" / "src" / "lib" / "version.ts",
        "import pkg from '../../package.json';\n\n"
        "export const APP_VERSION: string = pkg.version;\n\n"
        "export const LAST_UPDATED = '2026-08-22T07:00:00';\n",
    )
    _write(
        root / "docs" / "GETTING_STARTED.md",
        "# Getting Started\n\n**Compatibility**: LIA v%s\n" % version,
    )
    _write(
        root / "README.md",
        '<p align="center">\n  <strong>Version %s</strong> — <strong>A theme</strong>. '
        "Prose that must survive. — 22 August 2026.\n</p>\n" % version,
    )
    return root


def _fake_counts(root: Path, *, adr_files: int, adr_latest: int, releases: int) -> None:
    """Populate the count sources and the surfaces that quote them."""
    adr_dir = root / "docs" / "architecture"
    for index in range(1, adr_files + 1):
        number = adr_latest if index == adr_files else index
        _write(adr_dir / f"ADR-{number:03d}-topic.md", f"# ADR {number}\n")

    changelog = "# Changelog\n\n" + "".join(
        f"## [1.0.{index}] - 2026-01-01\n\nEntry.\n\n" for index in range(releases)
    )
    _write(root / "CHANGELOG.md", changelog)

    _write(
        root / "apps" / "web" / "src" / "components" / "landing" / "constants.ts",
        "/**\n"
        " * - adrs: docs/architecture/ ADR files — recount every release.\n"
        " *   Re-measured at v1.31.2: backend 20,565 collected.\n"
        " */\n"
        "export const LANDING_STATS = {\n"
        "  tests: 26600,\n"
        f"  adrs: {adr_files},\n"
        f"  releases: {releases},\n"
        "} as const;\n",
    )
    _write(
        root / "CLAUDE.md",
        f"- ADR index ({adr_files} ADR files, ADR-{adr_latest} latest — ADR-008 has no "
        "separate file): `docs/architecture/ADR_INDEX.md`\n",
    )
    guides = root / "apps" / "web" / "src" / "data" / "guides"
    zh = guides / "how.zh.md"
    existing = zh.read_text(encoding="utf-8") if zh.exists() else "# How\n"
    _write(
        zh,
        existing + f"\n可靠性：{adr_files} 篇 ADR。\n\n结论：{adr_files} 篇 ADR。\n\n"
        f"*页脚：{adr_files} 篇 ADR*\n",
    )


class TestCanonicalVersion:
    """The single source of truth is the root package.json."""

    def test_reads_root_package_json(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path, "9.8.7")
        assert canonical_version(root) == "9.8.7"

    def test_rejects_a_non_semver_value(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        (root / "package.json").write_text('{"version": "1.2"}', encoding="utf-8")
        with pytest.raises(ValueError, match="semver"):
            canonical_version(root)


class TestVersionOccurrences:
    """Every tracked surface is read through the shared declaration."""

    def test_all_tracked_surfaces_are_found_and_aligned(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        found = version_occurrences(root)

        assert {occurrence.version for occurrence in found} == {"1.31.2"}
        paths = {occurrence.path for occurrence in found}
        for expected in (
            "package.json",
            "apps/web/package.json",
            "apps/api/pyproject.toml",
            "apps/web/public/firebase-messaging-sw.js",
            "docs/GETTING_STARTED.md",
            "README.md",
            "apps/web/src/data/guides/how.fr.md",
            "apps/web/src/data/guides/story.zh.md",
        ):
            assert expected in paths, f"{expected} is not covered by the declaration"

    def test_a_drifting_surface_is_reported_with_its_line(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        stale = root / "docs" / "GETTING_STARTED.md"
        _write(stale, "# Getting Started\n\n**Compatibility**: LIA v1.21.21\n")

        drifted = [item for item in version_occurrences(root) if item.version != "1.31.2"]

        assert len(drifted) == 1
        assert drifted[0].path == "docs/GETTING_STARTED.md"
        assert drifted[0].line == 3
        assert drifted[0].version == "1.21.21"

    def test_missing_surface_file_is_reported_not_skipped(self, tmp_path: Path) -> None:
        """A deleted/renamed surface must fail loudly, never scan nothing."""
        root = _fake_repo(tmp_path)
        (root / "README.md").unlink()
        with pytest.raises(FileNotFoundError, match="README.md"):
            version_occurrences(root)

    def test_readme_prose_is_not_part_of_the_match(self, tmp_path: Path) -> None:
        """Only the version token is captured — the theme sentence is editorial."""
        root = _fake_repo(tmp_path)
        readme = next(item for item in version_occurrences(root) if item.path == "README.md")
        assert readme.version == "1.31.2"


class TestGuideStampDiscovery:
    """Stamps are discovered; anything unclassified is a hard failure."""

    def test_localized_labels_and_separators_are_all_captured(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        stamps = discover_guide_stamps(root)

        stems = {stamp.path.rsplit("/", 1)[-1] for stamp in stamps}
        assert {"how.en.md", "how.fr.md", "why.de.md", "why.es.md"} <= stems
        assert "story.zh.md" in stems, "full-width colon (：) must be recognized"
        assert "privacy.fr.md" in stems, "exempt stamps must still be DISCOVERED"

    def test_exempt_guides_are_classified_and_never_tracked(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        tracked = {item.path for item in version_occurrences(root)}

        assert "apps/web/src/data/guides/privacy.fr.md" not in tracked
        assert "apps/web/src/data/guides/terms.en.md" not in tracked
        assert "privacy" in EXEMPT_GUIDE_STEMS
        assert EXEMPT_GUIDE_STEMS["privacy"], "an exemption must carry a written reason"

    def test_an_unclassified_stamped_guide_fails_loudly(self, tmp_path: Path) -> None:
        """The anti-rot contract: a new stamped guide cannot drift unnoticed."""
        root = _fake_repo(tmp_path)
        guides = root / "apps" / "web" / "src" / "data" / "guides"
        _write(guides / "charter.fr.md", "# Charter\n\n**Application** : LIA v1.31.2\n")

        with pytest.raises(UnknownStampError, match="charter"):
            version_occurrences(root)

    def test_tracked_stems_are_the_three_release_stamped_guides(self) -> None:
        assert STAMPED_GUIDE_STEMS == ("how", "why", "story")


class TestDerivedCounts:
    """Counts are recomputed from their source, never carried over."""

    def test_counts_are_read_from_the_sources(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        _fake_counts(root, adr_files=241, adr_latest=242, releases=223)

        counts = derived_counts(root)

        assert counts["adr_files"] == 241
        assert counts["adr_latest"] == 242
        assert counts["changelog_releases"] == 223

    def test_unreleased_heading_is_not_a_release(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        _fake_counts(root, adr_files=3, adr_latest=4, releases=5)
        changelog = root / "CHANGELOG.md"
        _write(changelog, "# Changelog\n\n## [Unreleased]\n\n" + changelog.read_text("utf-8"))

        assert derived_counts(root)["changelog_releases"] == 5

    def test_quoting_surfaces_are_located(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        _fake_counts(root, adr_files=241, adr_latest=242, releases=223)

        quoted = count_occurrences(root)
        by_path: dict[str, list[CountOccurrence]] = {}
        for item in quoted:
            by_path.setdefault(item.path, []).append(item)

        assert any(item.source == "adr_files" for item in by_path["CLAUDE.md"])
        assert any(item.source == "adr_latest" for item in by_path["CLAUDE.md"])
        zh = by_path["apps/web/src/data/guides/how.zh.md"]
        assert len(zh) == 3, "the Chinese guide quotes the ADR count three times"
        assert all(item.value == 241 for item in zh)

    def test_a_stale_quoted_count_is_visible(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        _fake_counts(root, adr_files=241, adr_latest=242, releases=223)
        _write(
            root / "CLAUDE.md",
            "- ADR index (183 ADR files, ADR-242 latest): `docs/architecture/ADR_INDEX.md`\n",
        )

        counts = derived_counts(root)
        stale = [item for item in count_occurrences(root) if item.value != counts[item.source]]

        assert [(item.path, item.value) for item in stale] == [("CLAUDE.md", 183)]

    def test_measurement_comments_are_not_quoted_counts(self, tmp_path: Path) -> None:
        """`Re-measured at v1.31.2` is history: bumping it would be a lie."""
        root = _fake_repo(tmp_path)
        _fake_counts(root, adr_files=241, adr_latest=242, releases=223)

        constants = "apps/web/src/components/landing/constants.ts"
        quoted = [item for item in count_occurrences(root) if item.path == constants]

        assert {item.source for item in quoted} == {"adr_files", "changelog_releases"}
        assert len(quoted) == 2, "only the LANDING_STATS literal, never the comment"


class TestBumpVersionSurfaces:
    """Rewriting touches the version token and nothing else."""

    def test_every_tracked_surface_is_rewritten(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        changed = bump_version_surfaces(root, "1.32.0")

        assert canonical_version(root) == "1.32.0"
        assert {item.version for item in version_occurrences(root)} == {"1.32.0"}
        assert "README.md" in changed
        assert "apps/web/src/data/guides/story.zh.md" in changed

    def test_exempt_and_editorial_content_survive(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        guides = root / "apps" / "web" / "src" / "data" / "guides"
        bump_version_surfaces(root, "1.32.0")

        assert "v1.14.2" in (guides / "privacy.fr.md").read_text(encoding="utf-8")
        assert "v1.14.2" in (guides / "terms.en.md").read_text(encoding="utf-8")
        readme = (root / "README.md").read_text(encoding="utf-8")
        assert "<strong>A theme</strong>" in readme
        assert "Prose that must survive." in readme
        assert "22 August 2026" in readme, "the release date stays editorial"

    def test_rewrite_preserves_crlf_and_surrounding_bytes(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        target = root / "docs" / "GETTING_STARTED.md"
        _write(
            target,
            "# Getting Started\r\n\r\n**Compatibility**: LIA v1.31.2\r\n",
            newline="",
        )

        bump_version_surfaces(root, "1.32.0")

        raw = target.read_bytes()
        assert raw == b"# Getting Started\r\n\r\n**Compatibility**: LIA v1.32.0\r\n"

    def test_bump_is_idempotent(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        bump_version_surfaces(root, "1.32.0")
        snapshot = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

        assert bump_version_surfaces(root, "1.32.0") == []
        after = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }
        assert after == snapshot

    def test_bump_refuses_a_non_semver_target(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        with pytest.raises(ValueError, match="semver"):
            bump_version_surfaces(root, "1.32")

    def test_bump_refuses_when_a_stamp_is_unclassified(self, tmp_path: Path) -> None:
        """Discovery runs BEFORE any write: a partial bump is worse than none."""
        root = _fake_repo(tmp_path)
        guides = root / "apps" / "web" / "src" / "data" / "guides"
        _write(guides / "charter.fr.md", "# Charter\n\n**Application** : LIA v1.31.2\n")
        before = (root / "README.md").read_bytes()

        with pytest.raises(UnknownStampError):
            bump_version_surfaces(root, "1.32.0")

        assert (root / "README.md").read_bytes() == before, "no partial write"


class TestLastUpdated:
    """The landing timestamp is written on demand, never invented."""

    def test_reads_the_current_timestamp(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        assert read_last_updated(root) == "2026-08-22T07:00:00"

    def test_writes_a_new_timestamp(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        assert set_last_updated(root, "2026-09-01T18:30:00") is True
        assert read_last_updated(root) == "2026-09-01T18:30:00"

    def test_writing_the_same_timestamp_is_a_no_op(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        assert set_last_updated(root, "2026-08-22T07:00:00") is False

    def test_rejects_a_malformed_timestamp(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        with pytest.raises(ValueError, match="ISO"):
            set_last_updated(root, "2026-09-01 18:30")
        assert read_last_updated(root) == "2026-08-22T07:00:00", "no partial write"

    def test_surrounding_code_survives(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        set_last_updated(root, "2026-09-01T18:30:00")
        text = (root / "apps/web/src/lib/version.ts").read_text(encoding="utf-8")
        assert "export const APP_VERSION: string = pkg.version;" in text


class TestSyncDerivedCounts:
    """Quoted counts are realigned on their source, never carried over."""

    def test_stale_quotes_are_realigned_everywhere(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        _fake_counts(root, adr_files=241, adr_latest=242, releases=223)
        # Simulate the real drift: a new ADR landed, nobody recounted.
        _write(root / "docs" / "architecture" / "ADR-243-new.md", "# ADR 243\n")

        changed = sync_derived_counts(root)

        counts = derived_counts(root)
        assert counts == {
            "adr_files": 242,
            "adr_latest": 243,
            "changelog_releases": 223,
        }
        assert all(item.value == counts[item.source] for item in count_occurrences(root))
        assert "CLAUDE.md" in changed
        assert f"{GUIDES_DIR}/how.zh.md" in changed

    def test_all_three_chinese_occurrences_are_updated(self, tmp_path: Path) -> None:
        """The zh guide quotes the exact count three times — a partial sweep lies."""
        root = _fake_repo(tmp_path)
        _fake_counts(root, adr_files=10, adr_latest=11, releases=4)
        _write(root / "docs" / "architecture" / "ADR-012-new.md", "# ADR 12\n")

        sync_derived_counts(root)

        zh = (root / GUIDES_DIR / "how.zh.md").read_text(encoding="utf-8")
        assert zh.count("11 篇 ADR") == 3
        assert "10 篇 ADR" not in zh

    def test_measurement_comment_is_left_alone(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        _fake_counts(root, adr_files=241, adr_latest=242, releases=223)
        _write(root / "docs" / "architecture" / "ADR-243-new.md", "# ADR 243\n")

        sync_derived_counts(root)

        constants = (root / "apps/web/src/components/landing/constants.ts").read_text(
            encoding="utf-8"
        )
        assert "Re-measured at v1.31.2: backend 20,565 collected." in constants
        assert "  adrs: 242," in constants
        assert "  tests: 26600," in constants, "a measured stat is never derived"

    def test_sync_is_idempotent(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        _fake_counts(root, adr_files=241, adr_latest=242, releases=223)

        assert sync_derived_counts(root) == []

    def test_sync_validates_before_writing(self, tmp_path: Path) -> None:
        """A malformed count surface aborts with nothing written."""
        root = _fake_repo(tmp_path)
        _fake_counts(root, adr_files=241, adr_latest=242, releases=223)
        _write(root / "docs" / "architecture" / "ADR-243-new.md", "# ADR 243\n")
        zh_path = root / GUIDES_DIR / "how.zh.md"
        _write(zh_path, "# How\n\n**应用**：LIA v1.31.2\n\n仅有一次：241 篇 ADR。\n")
        before = (root / "CLAUDE.md").read_bytes()

        with pytest.raises(SurfaceError, match="expected 3 occurrence"):
            sync_derived_counts(root)

        assert (root / "CLAUDE.md").read_bytes() == before, "no partial write"


class TestOccurrenceContract:
    """The shared record carries what a human needs to fix the drift."""

    def test_occurrence_fields(self, tmp_path: Path) -> None:
        root = _fake_repo(tmp_path)
        sample = version_occurrences(root)[0]
        assert isinstance(sample, Occurrence)
        assert sample.path and sample.line > 0 and sample.version
        assert sample.label, "a human-readable surface label is required"
