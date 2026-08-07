"""Host-neutral Web release artifact contract (B03, ADR-215).

What must hold:
- the Web Dockerfile bakes NO deployment hostname: the API URL argument
  defaults to the explicit empty string (same-origin), the app-URL argument
  has no default, and the unused Google public client ID is gone;
- the release workflow builds the Web image with the explicit empty API URL;
- no source module keeps a hardcoded deployment-host fallback.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()
WEB_DOCKERFILE = ROOT / "apps/web/Dockerfile.prod"
RELEASE_WORKFLOW = ROOT / ".github/workflows/release.yml"


def test_web_dockerfile_defaults_to_same_origin() -> None:
    body = WEB_DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG NEXT_PUBLIC_API_URL=\n" in body or body.rstrip().endswith(
        "ARG NEXT_PUBLIC_API_URL="
    ), "the API URL build arg must default to the explicit empty string"
    assert "NEXT_PUBLIC_API_URL=http://localhost:8000" not in body
    assert "NEXT_PUBLIC_APP_URL=http://localhost:3000" not in body
    assert "NEXT_PUBLIC_GOOGLE_CLIENT_ID" not in body


def test_release_workflow_builds_web_same_origin() -> None:
    body = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert re.search(
        r"NEXT_PUBLIC_API_URL=\s*$", body, flags=re.MULTILINE
    ), "the release Web build must pass the explicit empty NEXT_PUBLIC_API_URL"


def test_showroom_build_arguments_are_wired_end_to_end() -> None:
    """The two baked showroom values must be settable through the IMAGE path.

    They are `NEXT_PUBLIC_*`, so Next inlines them at build time: without a
    build argument in the Dockerfile AND a passthrough in Compose, the
    documented deployment procedure cannot be executed at all.
    """
    dockerfile = WEB_DOCKERFILE.read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    for variable in (
        "NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT",
        "NEXT_PUBLIC_SHOWROOM_PROOF_SHA",
    ):
        assert f"ARG {variable}" in dockerfile, f"{variable} is not a build arg"
        assert (
            f"ENV {variable}=${variable}" in dockerfile
        ), f"{variable} is declared but never promoted to the build env"
        assert (
            f"{variable}=${{{variable}" in compose
        ), f"{variable} is not passed through docker-compose.prod.yml"
    # Safe defaults: the passive mockup, and links that degrade honestly.
    assert "ARG NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=legacy" in dockerfile
    assert "ARG NEXT_PUBLIC_SHOWROOM_PROOF_SHA=\n" in dockerfile


def test_release_bakes_the_commit_sha_as_the_proof_sha() -> None:
    """A release must never need a manual (forgeable) proof SHA."""
    body = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert (
        "NEXT_PUBLIC_SHOWROOM_PROOF_SHA=${{ github.sha }}" in body
    ), "the release build must derive the proof SHA from the built commit"
    assert "NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=" in body


def test_no_source_module_hardcodes_the_hosted_origin() -> None:
    web_src = ROOT / "apps/web/src"
    offenders: list[str] = []
    for path in web_src.rglob("*.ts*"):
        if "__tests__" in path.parts or path.suffix not in {".ts", ".tsx"}:
            continue
        if "lia.jeyswork.com" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], (
        "hardcoded deployment hostnames must resolve through site-origin: " f"{offenders}"
    )
