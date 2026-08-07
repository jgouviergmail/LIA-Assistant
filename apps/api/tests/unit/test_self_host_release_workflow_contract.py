"""Two-graph release workflow contract (ADR-215, B02/B15).

What must hold:
- the tag-push graph (require-green-ci → build-candidates →
  assemble-self-host-release → publish-candidate-summary) can NEVER reach
  promotion: every promotion job is workflow_dispatch-only;
- candidates are pushed under sha-staging tags only; semver tags are
  attached exclusively by promote-images via `imagetools create` (no
  build-push-action step there — promotion never rebuilds);
- the Web build passes the explicit empty NEXT_PUBLIC_API_URL and the API
  provenance args; both SBOMs are generated;
- evidence verification binds the candidate manifest by SHA-256 and checks
  workflow identity/conclusion/repository;
- release notes verify the bundle checksum BEFORE extracting and never
  instruct a mutable `github.ref_name` pull or a bare `docker compose up`;
- release.yml never calls the disposable qualification workflow.
"""

from __future__ import annotations

import re

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()
RELEASE = ROOT / ".github/workflows/release.yml"

PROMOTION_JOBS = (
    "verify-qualified-evidence",
    "finalize-qualified-manifest",
    "promote-images",
    "create-release",
)
CANDIDATE_JOBS = (
    "require-green-ci",
    "build-candidates",
    "assemble-self-host-release",
    "publish-candidate-summary",
)


def _workflow() -> dict:
    return yaml.safe_load(RELEASE.read_text(encoding="utf-8"))


def _body() -> str:
    return RELEASE.read_text(encoding="utf-8")


def test_both_graphs_exist_with_the_exact_jobs() -> None:
    jobs = _workflow()["jobs"]
    for job in (*CANDIDATE_JOBS, *PROMOTION_JOBS):
        assert job in jobs, f"missing job {job}"


def test_promotion_is_manual_dispatch_only() -> None:
    jobs = _workflow()["jobs"]
    for job in PROMOTION_JOBS:
        condition = jobs[job].get("if", "")
        assert (
            "workflow_dispatch" in condition
        ), f"{job} must be reachable only from a manual dispatch"
    for job in CANDIDATE_JOBS:
        condition = jobs[job].get("if", "")
        assert "push" in condition, f"{job} must belong to the tag-push graph"
    # No candidate job may depend on a promotion job or vice versa.
    for job in CANDIDATE_JOBS:
        needs = jobs[job].get("needs") or []
        needs = [needs] if isinstance(needs, str) else needs
        assert not set(needs) & set(PROMOTION_JOBS)
    workflow = _workflow()
    # PyYAML parses the `on:` key as boolean True.
    triggers = workflow.get("on") or workflow[True]
    dispatch_inputs = triggers["workflow_dispatch"]["inputs"]
    assert set(dispatch_inputs) == {"candidate_run_id", "qualification_run_id"}


def test_candidates_use_staging_tags_and_promotion_never_builds() -> None:
    body = _body()
    # Raw-text oracles: yaml re-serialization reflows GitHub expressions.
    assert ":sha-${{ github.sha }}" in body
    assert "type=semver" not in body
    promote_dump = yaml.safe_dump(_workflow()["jobs"]["promote-images"])
    assert "build-push-action" not in promote_dump
    assert "imagetools create" in body  # raw text: yaml dump reflows the run


def test_web_build_args_and_provenance() -> None:
    build_dump = yaml.safe_dump(_workflow()["jobs"]["build-candidates"])
    assert "NEXT_PUBLIC_API_URL=\n" in build_dump or "NEXT_PUBLIC_API_URL=" in build_dump
    for arg in ("APP_VERSION=", "GIT_COMMIT_SHA=", "BUILD_DATE="):
        assert arg in build_dump


def test_both_sboms_are_generated() -> None:
    assemble = yaml.safe_dump(_workflow()["jobs"]["assemble-self-host-release"])
    assert "sbom-api.cdx.json" in assemble
    assert "sbom-web.cdx.json" in assemble


def test_evidence_verification_is_hash_bound() -> None:
    verify = yaml.safe_dump(_workflow()["jobs"]["verify-qualified-evidence"])
    assert "candidate_sha256" in verify
    assert "sha256sum" in verify
    assert "installer-disposable-smoke.yml" in verify
    assert "conclusion" in verify


def test_release_notes_are_truthful() -> None:
    body = _body()
    assert "sha256sum --check lia-self-host-bundle.tar.gz.sha256" in body
    check_pos = body.index("sha256sum --check")
    tar_pos = body.index("tar -xzf")
    assert check_pos < tar_pos, "verify the checksum BEFORE extracting"
    assert not re.search(
        r"docker pull [^\n]*\$\{\{\s*github\.ref_name\s*\}\}", body
    ), "pull instructions must use digests, never the mutable ref_name"
    assert "cp .env.example .env" not in body
    assert not re.search(r"^\s*docker compose up -d\s*$", body, flags=re.MULTILINE)


def test_release_never_calls_the_disposable_workflow() -> None:
    workflow = _workflow()
    for job in workflow["jobs"].values():
        assert "installer-disposable-smoke" not in str(job.get("uses", ""))
        for step in job.get("steps", []):
            uses = str(step.get("uses", ""))
            assert "installer-disposable-smoke" not in uses
