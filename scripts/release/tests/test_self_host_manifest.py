"""Self-host release manifest schema and promotion contract (B02/B06).

What must hold:
- image references are digest-only (`repository@sha256:64-lowercase-hex`);
  tags, uppercase, and short digests are rejected;
- every app and dependency service declares exactly linux/amd64 and
  linux/arm64, each with one child-manifest digest and one OCI config
  digest — a missing architecture blocks, never silently omits;
- every dependency-catalogue service appears exactly once;
- the image lock maps requested Compose services to digests, rejects an
  unknown service, and introduces no extra service;
- default/public loading requires qualification="passed"; only the
  workflow harness may explicitly load a candidate;
- promotion copies every canonical field and flips ONLY the qualification,
  and rejects evidence whose candidate hash or four-row matrix mismatches.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.install.manifest import (  # noqa: E402
    ImageArtifact,
    ManifestError,
    PlatformArtifact,
    SelfHostManifest,
    load_manifest,
    render_image_lock,
    validate_manifest,
)
from scripts.release.self_host_manifest import (  # noqa: E402
    load_dependency_catalogue,
    write_candidate_manifest,
    write_passed_manifest,
)

pytestmark = pytest.mark.unit

DIG = "sha256:" + "a" * 64
DIG2 = "sha256:" + "b" * 64


def _platforms() -> tuple[PlatformArtifact, ...]:
    return (
        PlatformArtifact("linux/amd64", DIG, DIG2),
        PlatformArtifact("linux/arm64", DIG2, DIG),
    )


def _image(service: str) -> ImageArtifact:
    return ImageArtifact(
        service=service,
        reference=f"ghcr.io/x/{service}@{DIG}",
        platforms=_platforms(),
    )


def _catalogue_services() -> list[str]:
    return [entry["service"] for entry in load_dependency_catalogue()]


def _manifest(qualification: str = "passed") -> SelfHostManifest:
    images = tuple(_image(s) for s in ["api", "web", *_catalogue_services()])
    return SelfHostManifest(
        schema_version=1,
        release_version="1.29.0",
        source_sha="c" * 40,
        built_at="2026-08-06T00:00:00Z",
        bundle_archive_sha256="d" * 64,
        bundle_tree_sha256="e" * 64,
        source_context_archive_sha256="f" * 64,
        source_context_tree_sha256="0" * 64,
        images=images,
        sboms={"api": "1" * 64, "web": "2" * 64},
        qualification=qualification,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Digest and platform validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_reference",
    [
        "ghcr.io/x/api:latest",
        "ghcr.io/x/api:1.29.0",
        f"ghcr.io/x/api@sha256:{'A' * 64}",
        f"ghcr.io/x/api@sha256:{'a' * 63}",
        "ghcr.io/x/api",
    ],
)
def test_tag_or_malformed_reference_is_rejected(bad_reference: str) -> None:
    image = ImageArtifact("api", bad_reference, _platforms())
    manifest = _manifest()
    mutated = SelfHostManifest(
        **{**manifest.__dict__, "images": (image, *manifest.images[1:])}
    )
    assert any("reference" in e for e in validate_manifest(mutated))


def test_missing_architecture_blocks() -> None:
    image = ImageArtifact(
        "api",
        f"ghcr.io/x/api@{DIG}",
        (PlatformArtifact("linux/amd64", DIG, DIG2),),
    )
    manifest = _manifest()
    mutated = SelfHostManifest(
        **{**manifest.__dict__, "images": (image, *manifest.images[1:])}
    )
    assert any("linux/arm64" in e for e in validate_manifest(mutated))


def test_every_catalogue_service_appears_once() -> None:
    manifest = _manifest()
    assert validate_manifest(manifest) == ()
    # Drop one dependency -> blocking error naming it.
    missing = manifest.images[:-1]
    mutated = SelfHostManifest(**{**manifest.__dict__, "images": missing})
    dropped = manifest.images[-1].service
    assert any(dropped in e for e in validate_manifest(mutated))


# ---------------------------------------------------------------------------
# Image lock rendering
# ---------------------------------------------------------------------------


def test_image_lock_maps_requested_services_only() -> None:
    manifest = _manifest()
    lock = render_image_lock(manifest, ["api", "web", "postgres"])
    assert f"ghcr.io/x/api@{DIG}" in lock
    assert f"ghcr.io/x/postgres@{DIG}" in lock
    assert "caddy" not in lock  # not requested -> never introduced
    with pytest.raises(ManifestError):
        render_image_lock(manifest, ["api", "nonexistent-service"])


# ---------------------------------------------------------------------------
# Loading and qualification
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, manifest: SelfHostManifest) -> Path:
    path = tmp_path / "lia-self-host-manifest.json"
    payload = {
        **{k: v for k, v in manifest.__dict__.items() if k not in {"images", "sboms"}},
        "images": [
            {
                "service": i.service,
                "reference": i.reference,
                "platforms": [p.__dict__ for p in i.platforms],
            }
            for i in manifest.images
        ],
        "sboms": dict(manifest.sboms),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_public_loading_rejects_candidate(tmp_path: Path) -> None:
    path = _write(tmp_path, _manifest("candidate"))
    with pytest.raises(ManifestError, match="candidate"):
        load_manifest(path)
    # The workflow harness may load it explicitly.
    loaded = load_manifest(path, required_qualification="candidate")
    assert loaded.qualification == "candidate"


def test_passed_loading_roundtrips(tmp_path: Path) -> None:
    path = _write(tmp_path, _manifest("passed"))
    loaded = load_manifest(path)
    assert loaded == _manifest("passed")


# ---------------------------------------------------------------------------
# Candidate assembly and promotion
# ---------------------------------------------------------------------------


def test_promotion_flips_only_qualification(tmp_path: Path) -> None:
    candidate = _manifest("candidate")
    candidate_path = tmp_path / "candidate.json"
    write_candidate_manifest(manifest=candidate, output=candidate_path)
    digest = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    evidence = tmp_path / "qualification-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "candidate_sha256": digest,
                "rows": [
                    {"platform": "linux/amd64", "mode": "local", "result": "passed"},
                    {"platform": "linux/amd64", "mode": "prebuilt", "result": "passed"},
                    {"platform": "linux/arm64", "mode": "local", "result": "passed"},
                    {"platform": "linux/arm64", "mode": "prebuilt", "result": "passed"},
                ],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "passed.json"
    promoted = write_passed_manifest(
        candidate_path=candidate_path,
        qualification_evidence_path=evidence,
        output=out,
    )
    assert promoted.qualification == "passed"
    assert promoted == SelfHostManifest(
        **{**candidate.__dict__, "qualification": "passed"}
    )


def test_promotion_rejects_mismatched_evidence(tmp_path: Path) -> None:
    candidate = _manifest("candidate")
    candidate_path = tmp_path / "candidate.json"
    write_candidate_manifest(manifest=candidate, output=candidate_path)
    for evidence_payload in [
        {"candidate_sha256": "0" * 64, "rows": []},  # wrong hash
        {
            "candidate_sha256": hashlib.sha256(
                candidate_path.read_bytes()
            ).hexdigest(),
            "rows": [
                {"platform": "linux/amd64", "mode": "local", "result": "passed"}
            ],  # incomplete matrix
        },
        {
            "candidate_sha256": hashlib.sha256(
                candidate_path.read_bytes()
            ).hexdigest(),
            "rows": [
                {"platform": "linux/amd64", "mode": "local", "result": "passed"},
                {"platform": "linux/amd64", "mode": "prebuilt", "result": "failed"},
                {"platform": "linux/arm64", "mode": "local", "result": "passed"},
                {"platform": "linux/arm64", "mode": "prebuilt", "result": "passed"},
            ],  # one failing row
        },
    ]:
        evidence = tmp_path / "evidence.json"
        evidence.write_text(json.dumps(evidence_payload), encoding="utf-8")
        with pytest.raises(ManifestError):
            write_passed_manifest(
                candidate_path=candidate_path,
                qualification_evidence_path=evidence,
                output=tmp_path / "out.json",
            )


def test_dependency_catalogue_covers_the_compose_stack() -> None:
    services = set(_catalogue_services())
    expected = {
        "postgres",
        "postgres-backup",
        "redis",
        "tempo",
        "prometheus",
        "alertmanager",
        "blackbox-exporter",
        "grafana",
        "loki",
        "promtail",
        "node-exporter",
        "cadvisor",
        "postgres-exporter",
        "redis-exporter",
        "portainer",
        "caddy",
    }
    assert services == expected
