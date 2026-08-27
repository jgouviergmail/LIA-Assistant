"""Guard: no living document is unreachable from the documentation.

Why
---
A document nobody links to is a document nobody opens — and it is the shape
every stale duplicate in this repository took before it became one. Measured
2026-08-27, on a tree where ``task lint:docs`` was green:

* ``docs/metrics/CODE_METRICS_2025-01-21.md`` — a hand-counted snapshot 19
  months out of date, linked from nothing, superseded by four committed
  measurement instruments;
* ``docs/runbooks/redis/RedisConnectionPoolExhaustion.md`` — a SECOND runbook
  for one alert, unlinked, telling an on-call operator to edit a setting that
  the maintained runbook explicitly documents as non-existent;
* two implementation plans stranded in ``docs/plans/`` while the other forty
  lived in ``docs/superpowers/plans/``, and one at the repository root.

Broken links were already caught; unreachable documents were caught by nothing,
because nothing pointed at them to break.

Exemptions, not blanket silence
-------------------------------
Two prefixes are legitimately unreachable by link and are declared with their
reason in ``scripts/audit/doc_audit.py``:

* ``docs/knowledge/`` is a PRODUCT surface — indexed into the system RAG space
  at boot and served to users as answers, never navigated to;
* ``docs/runbooks/alerts/`` is reached from a firing alert's ``runbook``
  annotation, which ``test_alerts_core_guard`` already verifies.

HISTORICAL documents (ADRs, dated plans) are records, not navigation, and are
out of scope by classification.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
DOC_AUDIT_PATH = REPO_ROOT / "scripts" / "audit" / "doc_audit.py"

pytestmark = pytest.mark.unit

_MODULE_NAME = "_lia_audit_doc_audit_orphans"


def _load() -> ModuleType:
    cached = sys.modules.get(_MODULE_NAME)
    if cached is not None:
        return cached
    if not DOC_AUDIT_PATH.is_file():
        pytest.skip("guard needs the full repository checkout (scripts/audit/doc_audit.py).")
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, DOC_AUDIT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception:  # pragma: no cover - a failed import must not leave a stub
        del sys.modules[_MODULE_NAME]
        raise
    return module


_audit = _load()


def _git(root: Path, *args: str) -> None:
    """Run one git command in ``root``, quietly, failing loudly."""
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(root: Path) -> None:
    """Create a throwaway git repository with a deterministic identity."""
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "guard@example.test")
    _git(root, "config", "user.name", "guard")
    _git(root, "config", "commit.gpgsign", "false")


def _write(root: Path, files: dict[str, str]) -> None:
    """Write ``{relative path: content}`` under ``root``, creating parents."""
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


class TestExemptionsAreDeclared:
    """An exemption is a written decision, never an oversight."""

    def test_every_prefix_exemption_carries_a_reason(self) -> None:
        for prefix, reason in _audit.ORPHAN_EXEMPT_PREFIXES.items():
            assert reason.strip(), f"orphan exemption {prefix!r} has no written reason."

    def test_every_exempt_prefix_still_holds_documents(self) -> None:
        """A prefix that matches nothing is a blanket over whatever lands there."""
        for prefix in _audit.ORPHAN_EXEMPT_PREFIXES:
            directory = REPO_ROOT / prefix
            assert directory.is_dir() and any(directory.rglob("*.md")), (
                f"orphan exemption {prefix!r} covers no document. Remove it, or "
                "restore the directory it was written for."
            )

    def test_every_entry_point_exists(self) -> None:
        for entry in _audit.ENTRY_POINTS:
            assert (REPO_ROOT / entry).is_file(), (
                f"{entry} is declared an entry point but does not exist. A stale "
                "entry point exempts a path nothing occupies."
            )

    def test_the_knowledge_corpus_is_exempt_for_the_stated_reason(self) -> None:
        """The RAG corpus must never be 'fixed' by linking it into the index."""
        assert _audit.is_orphan_exempt("docs/knowledge/29_self_hosting.md")
        assert "RAG" in _audit.ORPHAN_EXEMPT_PREFIXES["docs/knowledge/"]


class TestDetection:
    """The rule itself, on a repository built for the test."""

    def test_an_unlinked_living_document_is_an_orphan(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            {
                "docs/INDEX.md": "# Index\n\n- [Kept](guides/KEPT.md)\n",
                "docs/guides/KEPT.md": "# Kept\n",
                "docs/guides/STRANDED.md": "# Stranded\n",
            },
        )

        assert _audit.find_orphans(tmp_path) == ["docs/guides/STRANDED.md"]

    def test_a_linked_document_is_not_an_orphan(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            {
                "docs/INDEX.md": "# Index\n",
                "docs/guides/A.md": "# A\n\nSee [B](./B.md).\n",
                "docs/guides/B.md": "# B\n",
            },
        )

        assert "docs/guides/B.md" not in _audit.find_orphans(tmp_path)

    def test_a_link_inside_a_code_fence_does_not_count(self, tmp_path: Path) -> None:
        """Code is not navigation — an example link rescues nothing."""
        _write(
            tmp_path,
            {
                "docs/INDEX.md": "# Index\n\n```\n[B](guides/B.md)\n```\n",
                "docs/guides/B.md": "# B\n",
            },
        )

        assert "docs/guides/B.md" in _audit.find_orphans(tmp_path)

    def test_a_historical_document_is_never_an_orphan(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            {
                "docs/INDEX.md": "# Index\n",
                "docs/architecture/ADR-001-Foo.md": "# ADR-001\n",
                "docs/superpowers/plans/2026-01-01-plan.md": "# Plan\n",
            },
        )

        assert _audit.find_orphans(tmp_path) == []

    def test_an_exempt_prefix_is_never_an_orphan(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            {
                "docs/INDEX.md": "# Index\n",
                "docs/knowledge/01_intro.md": "# Intro\n",
                "docs/runbooks/alerts/ServiceDown.md": "# ServiceDown\n",
            },
        )

        assert _audit.find_orphans(tmp_path) == []


class TestRepository:
    """The real assertion: everything living is reachable."""

    def test_no_living_document_is_orphaned(self) -> None:
        orphans = _audit.find_orphans(REPO_ROOT)

        assert not orphans, (
            "these living documents are linked from nowhere, so nobody will "
            "open them and nothing will keep them true:\n"
            + "\n".join(f"  {rel}" for rel in orphans)
            + "\nLink them from docs/INDEX.md (or the relevant guide), move them "
            "to docs/superpowers/ if they are a record, or delete them."
        )


class TestStagedPreview:
    """`--include-unstaged` answers "what will CI say once I commit this?".

    The default must keep mirroring a fresh clone: existence is decided by the
    git INDEX so a locally-present-but-untracked file cannot make a link look
    valid when it is broken for everyone else. That is the right default and it
    is not negotiable.

    Its cost is a recurring false alarm. Every time this repository moves or
    adds a document, `task lint:docs` reports LIVING findings that vanish on
    `git add` — it happened during the reasoning-unification work and again
    during this one. Answering it by hand (a throwaway script that monkeypatches
    the scan) is how the same simulation got written twice.

    The flag is that simulation, committed: tracked files PLUS what `git add -A`
    would stage, MINUS what it would delete. Deliberately not the naive "read the
    disk" shortcut, which also reveals gitignored documents — `docs/runbooks/
    CLOUDFLARE_TUNNEL.md` carries production access details and reporting it as
    an orphan invites a maintainer to "fix" it by publishing a link that is
    broken in every clone.
    """

    def test_untracked_document_is_invisible_by_default(self, tmp_path: Path) -> None:
        """The default verdict is the fresh clone's, whatever sits on disk."""
        _init_repo(tmp_path)
        _write(tmp_path, {"docs/INDEX.md": "# Index\n\n- [New](guides/NEW.md)\n"})
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-m", "base")
        _write(tmp_path, {"docs/guides/NEW.md": "# New\n"})  # created, not staged

        broken = _audit.audit(tmp_path)["broken"]["LIVING"]

        assert [target for _, _, target in broken] == [
            "guides/NEW.md"
        ], "an unstaged file must stay invisible: CI clones the index, not the disk"

    def test_include_unstaged_previews_the_commit(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _write(tmp_path, {"docs/INDEX.md": "# Index\n\n- [New](guides/NEW.md)\n"})
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-m", "base")
        _write(tmp_path, {"docs/guides/NEW.md": "# New\n"})

        tracked = _audit.tracked_paths(tmp_path, include_unstaged=True)
        assert tracked is not None
        assert "docs/guides/NEW.md" in tracked[0]

    def test_include_unstaged_drops_a_deleted_document(self, tmp_path: Path) -> None:
        """A moved-away file must stop resolving, or the preview lies too."""
        _init_repo(tmp_path)
        _write(tmp_path, {"docs/INDEX.md": "# Index\n", "docs/guides/OLD.md": "# Old\n"})
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-m", "base")
        (tmp_path / "docs" / "guides" / "OLD.md").unlink()

        tracked = _audit.tracked_paths(tmp_path, include_unstaged=True)
        assert tracked is not None
        assert "docs/guides/OLD.md" not in tracked[0]

    def test_a_gitignored_document_is_never_previewed(self, tmp_path: Path) -> None:
        """The private-runbook trap: ignored files stay out of both verdicts."""
        _init_repo(tmp_path)
        _write(
            tmp_path,
            {
                "docs/INDEX.md": "# Index\n",
                ".gitignore": "docs/runbooks/PRIVATE.md\n",
                "docs/runbooks/PRIVATE.md": "# secrets\n",
            },
        )
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-m", "base")

        tracked = _audit.tracked_paths(tmp_path, include_unstaged=True)
        assert tracked is not None
        assert "docs/runbooks/PRIVATE.md" not in tracked[0]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
