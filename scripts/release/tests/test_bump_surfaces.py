"""Release surface bump CLI — the mechanical half of a version bump.

What must hold:

- ``--check`` reports drift and writes nothing (it is what a human runs before
  a release, and what the failure message of the CI guard points at);
- a bump rewrites every tracked version surface AND realigns every derived
  count in one call, because forgetting the second is its own historical defect
  (``LANDING_STATS.adrs`` stranded at 183 for five releases);
- the landing timestamp is written only when supplied — never invented;
- a downgrade requires an explicit flag: a typo that ships 1.3.2 for 1.31.2
  would silently rewrite eighteen guides;
- the editorial remainder (CHANGELOG, FAQ, README theme, measured stats) is
  REPORTED, never faked, so the operator knows exactly what is left to do.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.bump_surfaces import main  # noqa: E402
from scripts.release.tests.test_version_surfaces import (  # noqa: E402
    _fake_counts,
    _fake_repo,
    _write,
)
from scripts.release.version_surfaces import (  # noqa: E402
    canonical_version,
    read_last_updated,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal repository with every surface aligned at 1.31.2."""
    root = _fake_repo(tmp_path)
    _fake_counts(root, adr_files=241, adr_latest=242, releases=223)
    return root


class TestCheckMode:
    """``--check`` is a read-only verdict."""

    def test_aligned_repository_returns_zero(self, repo: Path, capsys) -> None:
        assert main(["--check", "--root", str(repo)]) == 0
        assert "aligned" in capsys.readouterr().out.lower()

    def test_version_drift_is_reported_with_location(self, repo: Path, capsys) -> None:
        _write(repo / "docs" / "GETTING_STARTED.md", "**Compatibility**: LIA v1.21.21\n")

        assert main(["--check", "--root", str(repo)]) == 1

        out = capsys.readouterr().out
        assert "docs/GETTING_STARTED.md:1" in out
        assert "1.21.21" in out

    def test_count_drift_is_reported(self, repo: Path, capsys) -> None:
        _write(repo / "docs" / "architecture" / "ADR-243-new.md", "# ADR 243\n")

        assert main(["--check", "--root", str(repo)]) == 1

        out = capsys.readouterr().out
        assert "adr_files" in out
        assert "242" in out

    def test_check_writes_nothing(self, repo: Path) -> None:
        _write(repo / "docs" / "GETTING_STARTED.md", "**Compatibility**: LIA v1.21.21\n")
        before = {path: path.read_bytes() for path in repo.rglob("*") if path.is_file()}

        main(["--check", "--root", str(repo)])

        assert {path: path.read_bytes() for path in repo.rglob("*") if path.is_file()} == before

    def test_unclassified_stamp_fails_the_check(self, repo: Path, capsys) -> None:
        _write(
            repo / "apps/web/src/data/guides/charter.fr.md",
            "**Application** : LIA v1.31.2\n",
        )

        assert main(["--check", "--root", str(repo)]) == 1
        assert "charter" in capsys.readouterr().out


class TestBump:
    """A bump writes versions and counts together."""

    def test_writes_every_surface_and_realigns_counts(self, repo: Path, capsys) -> None:
        _write(repo / "docs" / "architecture" / "ADR-243-new.md", "# ADR 243\n")

        assert main(["1.32.0", "--root", str(repo)]) == 0

        assert canonical_version(repo) == "1.32.0"
        assert main(["--check", "--root", str(repo)]) == 0
        out = capsys.readouterr().out
        assert "README.md" in out
        assert "CLAUDE.md" in out

    def test_reports_the_editorial_remainder(self, repo: Path, capsys) -> None:
        main(["1.32.0", "--root", str(repo)])

        out = capsys.readouterr().out.lower()
        for reminder in ("changelog", "faq", "theme", "tests"):
            assert reminder in out, f"the operator must be reminded about {reminder}"

    def test_timestamp_is_written_only_when_supplied(self, repo: Path) -> None:
        main(["1.32.0", "--root", str(repo)])
        assert read_last_updated(repo) == "2026-08-22T07:00:00"

        main(["1.32.1", "--root", str(repo), "--last-updated", "2026-09-01T18:30:00"])
        assert read_last_updated(repo) == "2026-09-01T18:30:00"

    def test_timestamp_now_uses_the_injected_clock(self, repo: Path) -> None:
        main(
            ["1.32.0", "--root", str(repo), "--last-updated", "now"],
            now="2026-12-25T09:15:00",
        )
        assert read_last_updated(repo) == "2026-12-25T09:15:00"

    def test_a_downgrade_is_refused_by_default(self, repo: Path, capsys) -> None:
        assert main(["1.3.2", "--root", str(repo)]) == 2

        assert canonical_version(repo) == "1.31.2", "nothing written"
        assert "downgrade" in capsys.readouterr().out.lower()

    def test_a_downgrade_is_allowed_explicitly(self, repo: Path) -> None:
        assert main(["1.3.2", "--root", str(repo), "--allow-downgrade"]) == 0
        assert canonical_version(repo) == "1.3.2"

    def test_same_version_is_a_no_op_not_an_error(self, repo: Path, capsys) -> None:
        assert main(["1.31.2", "--root", str(repo)]) == 0
        assert "already" in capsys.readouterr().out.lower()

    def test_malformed_version_is_rejected(self, repo: Path, capsys) -> None:
        assert main(["1.32", "--root", str(repo)]) == 2
        assert canonical_version(repo) == "1.31.2"

    def test_unclassified_stamp_aborts_before_writing(self, repo: Path, capsys) -> None:
        _write(
            repo / "apps/web/src/data/guides/charter.fr.md",
            "**Application** : LIA v1.31.2\n",
        )

        assert main(["1.32.0", "--root", str(repo)]) == 2
        assert canonical_version(repo) == "1.31.2", "no partial bump"
        assert "charter" in capsys.readouterr().out


class TestAtomicity:
    """A bump either does both halves or neither."""

    def test_a_malformed_count_surface_aborts_before_any_version_write(
        self, repo: Path, capsys
    ) -> None:
        """Version surfaces must not be rewritten if the count half cannot run."""
        zh = repo / "apps/web/src/data/guides/how.zh.md"
        _write(zh, "# How\n\n**应用**：LIA v1.31.2\n\n只有一次：241 篇 ADR。\n")
        before = (repo / "README.md").read_bytes()

        assert main(["1.32.0", "--root", str(repo)]) == 2

        assert canonical_version(repo) == "1.31.2"
        assert (repo / "README.md").read_bytes() == before
        assert "expected 3 occurrence" in capsys.readouterr().out


class TestCountsOnly:
    """``--counts-only`` realigns derived counts without touching the version."""

    def test_realigns_counts_and_leaves_the_version_alone(self, repo: Path) -> None:
        _write(repo / "docs" / "architecture" / "ADR-243-new.md", "# ADR 243\n")

        assert main(["--counts-only", "--root", str(repo)]) == 0

        assert canonical_version(repo) == "1.31.2"
        claude_md = (repo / "CLAUDE.md").read_text(encoding="utf-8")
        assert "242 ADR files" in claude_md
        assert "ADR-243 latest" in claude_md

    def test_is_a_no_op_when_counts_already_match(self, repo: Path, capsys) -> None:
        assert main(["--counts-only", "--root", str(repo)]) == 0
        assert "nothing" in capsys.readouterr().out.lower()

    def test_rejects_a_version_argument(self, repo: Path) -> None:
        with pytest.raises(SystemExit):
            main(["1.32.0", "--counts-only", "--root", str(repo)])


class TestArgumentContract:
    """The CLI refuses ambiguous invocations rather than guessing."""

    def test_version_or_check_is_required(self, repo: Path) -> None:
        with pytest.raises(SystemExit):
            main(["--root", str(repo)])

    def test_check_and_version_are_mutually_exclusive(self, repo: Path) -> None:
        with pytest.raises(SystemExit):
            main(["1.32.0", "--check", "--root", str(repo)])
