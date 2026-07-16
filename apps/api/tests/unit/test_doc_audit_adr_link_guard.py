"""doc_audit must fail on broken ADR→ADR links inside actively-indexed ADRs (F024).

The 2026-07 audit found 15 broken relative links masked by the blanket
``HISTORICAL`` classification of every ``docs/architecture/ADR-*`` file: since
exit code 1 fires only on ``LIVING`` broken links, an ADR that cross-links a
sibling ADR which no longer exists never failed the audit. Eight of them were
genuine ADR→ADR drift (renamed/removed targets); the rest are annotated stale
code/session paths that are deliberately tolerated.

This guard proves the refined contract of ``scripts/audit/doc_audit.py``:

* a broken markdown link whose target is *another ADR file*
  (``ADR-<n>-*.md`` / ``ADR_INDEX.md``), inside an ADR whose number is present
  in ``ADR_INDEX.md`` (actively indexed), is escalated to ``LIVING`` and fails
  the run;
* a broken link to a source-code path (``*.py`` / ``*.ts``) or a deleted
  session/optim document inside the same ADR stays ``HISTORICAL`` (tolerated);
* an ADR whose number is *not* indexed keeps the lenient HISTORICAL treatment
  for its stale ADR cross-links.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
DOC_AUDIT_PATH = REPO_ROOT / "scripts" / "audit" / "doc_audit.py"


def _load_doc_audit():
    if not DOC_AUDIT_PATH.exists():
        pytest.skip("guard needs the full repository checkout (scripts/audit/doc_audit.py).")
    spec = importlib.util.spec_from_file_location("doc_audit", DOC_AUDIT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_repo(root: Path, adr_body: str, *, index_lists_adr_001: bool = True) -> None:
    """Build a minimal repo: docs/architecture/{ADR_INDEX.md, ADR-001-Foo.md}."""
    arch = root / "docs" / "architecture"
    arch.mkdir(parents=True)
    indexed = "- [ADR-001](ADR-001-Foo.md)\n" if index_lists_adr_001 else "- (no ADRs)\n"
    (arch / "ADR_INDEX.md").write_text(
        f"# ADR Index\n\n## ADRs Actifs\n\n{indexed}", encoding="utf-8"
    )
    (arch / "ADR-001-Foo.md").write_text(adr_body, encoding="utf-8")


def test_adr_to_adr_broken_link_in_indexed_adr_is_living(tmp_path: Path) -> None:
    """A broken sibling-ADR link inside an indexed ADR escalates to LIVING."""
    doc_audit = _load_doc_audit()
    _write_repo(
        tmp_path,
        "# ADR-001\n\n**Related**: [ADR-999](ADR-999-Ghost.md) (does not exist)\n",
    )
    report = doc_audit.audit(tmp_path)
    living_targets = [t for _rel, _ln, t in report["broken"]["LIVING"]]
    historical_targets = [t for _rel, _ln, t in report["broken"]["HISTORICAL"]]
    assert "ADR-999-Ghost.md" in living_targets
    assert "ADR-999-Ghost.md" not in historical_targets


def test_broken_code_path_link_in_adr_stays_historical(tmp_path: Path) -> None:
    """A broken code-path link inside an ADR is NOT escalated (tolerated)."""
    doc_audit = _load_doc_audit()
    _write_repo(
        tmp_path,
        "# ADR-001\n\nSee [planner](../../apps/api/src/domains/agents/nodes/gone.py) "
        "and [session](../optim/SESSION_99_FINAL.md).\n",
    )
    report = doc_audit.audit(tmp_path)
    living_targets = [t for _rel, _ln, t in report["broken"]["LIVING"]]
    historical_targets = [t for _rel, _ln, t in report["broken"]["HISTORICAL"]]
    assert "../../apps/api/src/domains/agents/nodes/gone.py" in historical_targets
    assert "../optim/SESSION_99_FINAL.md" in historical_targets
    assert not living_targets


def test_adr_link_in_unindexed_adr_not_escalated(tmp_path: Path) -> None:
    """An ADR whose number is absent from the index keeps lenient treatment."""
    doc_audit = _load_doc_audit()
    _write_repo(
        tmp_path,
        "# ADR-001\n\n**Related**: [ADR-999](ADR-999-Ghost.md)\n",
        index_lists_adr_001=False,
    )
    report = doc_audit.audit(tmp_path)
    living_targets = [t for _rel, _ln, t in report["broken"]["LIVING"]]
    historical_targets = [t for _rel, _ln, t in report["broken"]["HISTORICAL"]]
    assert "ADR-999-Ghost.md" in historical_targets
    assert not living_targets


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


def test_git_checkout_existence_is_index_based(tmp_path: Path) -> None:
    """Inside a git checkout, link targets resolve against the INDEX, not the disk.

    Two CI-vs-Windows divergences hid real broken links (F024 wave 2):

    * a link whose case drifts from the tracked file resolves on NTFS/APFS
      (case-insensitive) but 404s on the Linux runner's checkout;
    * a link to a locally present but git-ignored/untracked file resolves on
      the author's disk but is broken in every fresh clone.

    Both must be findings even when the audit runs on a case-insensitive
    filesystem with the untracked file present.
    """
    doc_audit = _load_doc_audit()
    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    (docs / "Guide.md").write_text("# Guide\n", encoding="utf-8")
    (docs / "INDEX.md").write_text(
        "# Index\n\n"
        "- [ok](Guide.md)\n"
        "- [case drift](guide.md)\n"
        "- [untracked](LOCAL_ONLY.md)\n",
        encoding="utf-8",
    )
    (docs / "LOCAL_ONLY.md").write_text("# local, never committed\n", encoding="utf-8")
    (docs / "CODE.md").write_text(
        "# Code refs\n\nRuntime reads src/local_secret.py at boot.\n", encoding="utf-8"
    )
    src = repo / "src"
    src.mkdir()
    (src / "local_secret.py").write_text("SECRET = 1\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "docs/Guide.md", "docs/INDEX.md", "docs/CODE.md")
    _git(repo, "commit", "-q", "-m", "init")

    report = doc_audit.audit(repo)
    living_targets = sorted(t for _rel, _ln, t in report["broken"]["LIVING"])
    assert living_targets == ["LOCAL_ONLY.md", "guide.md"]
    # Same contract for inline code paths: locally present but untracked
    # (git-ignored secrets/config) is stale in every fresh checkout.
    stale_living = sorted(t for _rel, _ln, t in report["stale"]["LIVING"])
    assert stale_living == ["src/local_secret.py"]


def test_repository_doc_audit_has_no_living_broken_links() -> None:
    """The real repository must be clean: 0 LIVING broken links after F024 repair."""
    doc_audit = _load_doc_audit()
    report = doc_audit.audit(REPO_ROOT)
    assert report["broken"]["LIVING"] == [], (
        "LIVING broken links regressed (F024): " f"{report['broken']['LIVING']}"
    )


def test_repository_doc_audit_has_no_living_stale_code_paths() -> None:
    """LIVING docs must not reference code paths that no longer exist.

    Ratchets the documentation cleanup that brought LIVING stale code paths from
    38 to 0: every ``file.py:line`` reference in a LIVING doc must resolve to a
    real file, unless it is an illustrative placeholder (``my_tool.py``) or is
    explicitly annotated as an example/obsolete/proposed reference. A regression
    here means a doc silently drifted from the code and now misleads the reader.
    """
    doc_audit = _load_doc_audit()
    report = doc_audit.audit(REPO_ROOT)
    stale_living = report["stale"]["LIVING"]
    assert stale_living == [], (
        "LIVING docs regressed with stale code paths: annotate the reference "
        "(example/obsolete/proposed) or fix the path. Offenders: "
        f"{stale_living}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
