"""Guard: the Release workflow must be gated on a green CI run (audit F008).

``release.yml`` triggers on a tag push. Without a gate it would build/publish
images and cut a GitHub release for a commit whose CI (``ci.yml``) never passed.
This guard fails if the ``require-green-ci`` gate is removed or if the
image-building jobs stop depending on it — keeping the release gated by
construction.

Paths are resolved from ``__file__`` (CWD-independent, per the F023 lesson).
"""

from __future__ import annotations

import yaml

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"

# Jobs that must not run before CI is confirmed green for the tagged commit.
GATED_JOBS = ("build-and-push", "generate-sbom")


def _load_release() -> dict:
    return yaml.safe_load(RELEASE_YML.read_text(encoding="utf-8"))


def test_release_has_require_green_ci_gate():
    """A dedicated gate job must exist and verify the ci.yml conclusion."""
    jobs = _load_release()["jobs"]
    assert "require-green-ci" in jobs, "release.yml lost its require-green-ci gate (F008)"
    body = yaml.safe_dump(jobs["require-green-ci"])
    assert "ci.yml" in body, "require-green-ci must check the ci.yml workflow conclusion"
    assert "success" in body, "require-green-ci must require conclusion == 'success'"


def test_image_jobs_depend_on_the_gate():
    """The image-building / SBOM jobs must not run before the gate passes."""
    jobs = _load_release()["jobs"]
    for job in GATED_JOBS:
        assert job in jobs, f"expected job '{job}' in release.yml"
        needs = jobs[job].get("needs")
        needs = [needs] if isinstance(needs, str) else (needs or [])
        assert "require-green-ci" in needs, (
            f"job '{job}' must declare needs: require-green-ci so a tag never "
            "publishes artifacts for a red-CI commit (F008)"
        )


def test_release_grants_actions_read_permission():
    """The gate reads workflow runs, which needs the actions:read permission."""
    permissions = _load_release().get("permissions", {})
    assert (
        permissions.get("actions") == "read"
    ), "release.yml needs 'actions: read' for require-green-ci to query ci.yml runs"
