"""Shared self-host release-manifest schema (ADR-215, B02/B05/B06).

Python-3.10 stdlib ONLY: the installer runs on a bare Linux host with no
virtualenv. This module owns the schema, digest validation, image-lock
rendering, and bundle-tree verification; `scripts/release` imports these
types for candidate assembly and never redeclares them.

Every image reference is digest-addressed (`repository@sha256:<64 hex>`) —
a mutable tag is never a valid installer input, in any mode.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DIGEST_PATTERN = re.compile(r"^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
BARE_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_PLATFORMS: tuple[str, ...] = ("linux/amd64", "linux/arm64")


class ManifestError(ValueError):
    """A structurally invalid, unqualified, or mismatched manifest input."""


@dataclass(frozen=True)
class PlatformArtifact:
    """One architecture row of a multi-platform image.

    Attributes:
        platform: Exact platform string (linux/amd64 or linux/arm64).
        manifest_digest: Child image-manifest digest for this platform.
        config_digest: OCI config digest (what a running container reports
            as `.Image`), for this platform.
    """

    platform: Literal["linux/amd64", "linux/arm64"]
    manifest_digest: str
    config_digest: str


@dataclass(frozen=True)
class ImageArtifact:
    """One Compose service's immutable image identity.

    Attributes:
        service: Compose service name the reference locks.
        reference: Digest-only pull reference (`repository@sha256:...`).
        platforms: Exactly the two required architecture rows.
    """

    service: str
    reference: str
    platforms: tuple[PlatformArtifact, ...]


@dataclass(frozen=True)
class SelfHostManifest:
    """The complete release identity a prebuilt install consumes.

    Attributes:
        schema_version: Manifest schema revision (currently 1).
        release_version: Human release version (display only, never pulled).
        source_sha: Full 40-hex source commit of every artifact.
        built_at: UTC ISO-8601 assembly timestamp.
        bundle_archive_sha256: SHA-256 of the host-bundle tarball.
        bundle_tree_sha256: Canonical extracted-tree SHA-256 of the bundle.
        source_context_archive_sha256: SHA-256 of the embedded source
            context tarball (local-build fallback input).
        source_context_tree_sha256: Canonical tree SHA-256 of that context.
        images: App plus dependency image identities.
        sboms: SBOM file SHA-256 per app (api/web).
        qualification: candidate (built, unproven) or passed (G3/G4 green).
    """

    schema_version: int
    release_version: str
    source_sha: str
    built_at: str
    bundle_archive_sha256: str
    bundle_tree_sha256: str
    source_context_archive_sha256: str
    source_context_tree_sha256: str
    images: tuple[ImageArtifact, ...]
    sboms: Mapping[str, str]
    qualification: Literal["candidate", "passed"]


def _catalogue_services() -> tuple[str, ...]:
    """Service names every complete manifest must lock (apps + catalogue)."""
    catalogue = (
        Path(__file__).resolve().parent.parent
        / "release"
        / "self_host_dependencies.json"
    )
    entries = json.loads(catalogue.read_text(encoding="utf-8"))
    return ("api", "web", *(entry["service"] for entry in entries))


def validate_manifest(manifest: SelfHostManifest) -> tuple[str, ...]:
    """Return every blocking structural error (empty tuple when valid)."""
    errors: list[str] = []
    if manifest.schema_version != 1:
        errors.append(f"unsupported schema_version {manifest.schema_version}")
    if not SOURCE_SHA_PATTERN.fullmatch(manifest.source_sha):
        errors.append("source_sha must be a full 40-hex commit")
    for field in (
        "bundle_archive_sha256",
        "bundle_tree_sha256",
        "source_context_archive_sha256",
        "source_context_tree_sha256",
    ):
        if not BARE_SHA256_PATTERN.fullmatch(getattr(manifest, field)):
            errors.append(f"{field} must be a 64-lowercase-hex SHA-256")
    if manifest.qualification not in ("candidate", "passed"):
        errors.append(f"unknown qualification {manifest.qualification!r}")

    seen: set[str] = set()
    for image in manifest.images:
        if image.service in seen:
            errors.append(f"duplicate image entry for service {image.service}")
        seen.add(image.service)
        if not DIGEST_PATTERN.fullmatch(image.reference):
            errors.append(
                f"{image.service}: reference must be digest-only "
                "(repository@sha256:<64 lowercase hex>), never a tag"
            )
        platforms = {p.platform for p in image.platforms}
        for required in REQUIRED_PLATFORMS:
            if required not in platforms:
                errors.append(f"{image.service}: missing platform {required}")
        for row in image.platforms:
            for field_name in ("manifest_digest", "config_digest"):
                if not SHA256_PATTERN.fullmatch(getattr(row, field_name)):
                    errors.append(
                        f"{image.service}/{row.platform}: {field_name} must be "
                        "sha256:<64 lowercase hex>"
                    )
    for required_service in _catalogue_services():
        if required_service not in seen:
            errors.append(f"missing image entry for service {required_service}")
    for app in ("api", "web"):
        if app not in manifest.sboms:
            errors.append(f"missing SBOM hash for {app}")
        elif not BARE_SHA256_PATTERN.fullmatch(manifest.sboms[app]):
            errors.append(f"sboms[{app}] must be a 64-lowercase-hex SHA-256")
    return tuple(errors)


def manifest_to_payload(manifest: SelfHostManifest) -> dict[str, object]:
    """Serialize to the canonical JSON payload (stable key order)."""
    return {
        "schema_version": manifest.schema_version,
        "release_version": manifest.release_version,
        "source_sha": manifest.source_sha,
        "built_at": manifest.built_at,
        "bundle_archive_sha256": manifest.bundle_archive_sha256,
        "bundle_tree_sha256": manifest.bundle_tree_sha256,
        "source_context_archive_sha256": manifest.source_context_archive_sha256,
        "source_context_tree_sha256": manifest.source_context_tree_sha256,
        "images": [
            {
                "service": image.service,
                "reference": image.reference,
                "platforms": [
                    {
                        "platform": row.platform,
                        "manifest_digest": row.manifest_digest,
                        "config_digest": row.config_digest,
                    }
                    for row in image.platforms
                ],
            }
            for image in manifest.images
        ],
        "sboms": dict(manifest.sboms),
        "qualification": manifest.qualification,
    }


def _as_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ManifestError(f"malformed manifest payload: {context} is not a mapping")
    return value


def _as_sequence(value: object, context: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ManifestError(f"malformed manifest payload: {context} is not a list")
    return value


def _as_platform(value: object) -> Literal["linux/amd64", "linux/arm64"]:
    if value == "linux/amd64":
        return "linux/amd64"
    if value == "linux/arm64":
        return "linux/arm64"
    raise ManifestError(f"malformed manifest payload: unknown platform {value!r}")


def _as_qualification(value: object) -> Literal["candidate", "passed"]:
    if value == "candidate":
        return "candidate"
    if value == "passed":
        return "passed"
    raise ManifestError(f"malformed manifest payload: unknown qualification {value!r}")


def _payload_to_manifest(payload: Mapping[str, object]) -> SelfHostManifest:
    try:
        images = tuple(
            ImageArtifact(
                service=str(_as_mapping(entry, "image")["service"]),
                reference=str(_as_mapping(entry, "image")["reference"]),
                platforms=tuple(
                    PlatformArtifact(
                        platform=_as_platform(_as_mapping(row, "platform")["platform"]),
                        manifest_digest=str(
                            _as_mapping(row, "platform")["manifest_digest"]
                        ),
                        config_digest=str(_as_mapping(row, "platform")["config_digest"]),
                    )
                    for row in _as_sequence(
                        _as_mapping(entry, "image")["platforms"], "platforms"
                    )
                ),
            )
            for entry in _as_sequence(payload["images"], "images")
        )
        schema_version = payload["schema_version"]
        if not isinstance(schema_version, int):
            raise ManifestError(
                "malformed manifest payload: schema_version is not an integer"
            )
        return SelfHostManifest(
            schema_version=schema_version,
            release_version=str(payload["release_version"]),
            source_sha=str(payload["source_sha"]),
            built_at=str(payload["built_at"]),
            bundle_archive_sha256=str(payload["bundle_archive_sha256"]),
            bundle_tree_sha256=str(payload["bundle_tree_sha256"]),
            source_context_archive_sha256=str(
                payload["source_context_archive_sha256"]
            ),
            source_context_tree_sha256=str(payload["source_context_tree_sha256"]),
            images=images,
            sboms={
                str(k): str(v)
                for k, v in _as_mapping(payload["sboms"], "sboms").items()
            },
            qualification=_as_qualification(payload["qualification"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"malformed manifest payload: {exc}") from exc


def load_manifest(
    path: Path,
    *,
    required_qualification: Literal["candidate", "passed"] = "passed",
) -> SelfHostManifest:
    """Load and fully validate a manifest file.

    Args:
        path: Manifest JSON file.
        required_qualification: `passed` (the public default — the CLI never
            accepts a candidate) or `candidate` (workflow harness only).

    Returns:
        The validated manifest.

    Raises:
        ManifestError: On malformed JSON, structural errors, or a
            qualification mismatch.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"unreadable manifest {path.name}: {exc}") from exc
    manifest = _payload_to_manifest(payload)
    errors = validate_manifest(manifest)
    if errors:
        raise ManifestError("; ".join(errors))
    if manifest.qualification != required_qualification:
        raise ManifestError(
            f"manifest qualification is {manifest.qualification!r}, "
            f"required {required_qualification!r}"
        )
    return manifest


def render_image_lock(
    manifest: SelfHostManifest, services: Collection[str]
) -> str:
    """Render the Compose image-lock override for the requested services.

    Args:
        manifest: A validated manifest.
        services: Exact Compose service names of the selected layers.

    Returns:
        YAML content pinning each requested service to its digest.

    Raises:
        ManifestError: When a requested service has no manifest entry.
    """
    by_service = {image.service: image for image in manifest.images}
    lines = [
        "# Generated image lock (ADR-215) — digest-only, never edit by hand.",
        "services:",
    ]
    for service in sorted(services):
        image = by_service.get(service)
        if image is None:
            raise ManifestError(f"no manifest image for service {service!r}")
        lines.append(f"  {service}:")
        lines.append(f"    image: {image.reference}")
    return "\n".join(lines) + "\n"


def hash_file(path: Path) -> str:
    """SHA-256 of a file's raw bytes (lowercase hex)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_tree_sha256(
    root: Path, relative_paths: Collection[str]
) -> str:
    """Canonical tree digest: per-path name, mode class, and content hash.

    Args:
        root: Extracted tree root.
        relative_paths: Allowlisted POSIX-relative paths, hashed in sorted
            order. Symlinks are rejected (never followed).

    Returns:
        The 64-hex canonical tree SHA-256.

    Raises:
        ManifestError: On a missing path or a symlink.
    """
    digest = hashlib.sha256()
    for rel in sorted(relative_paths):
        target = root / rel
        if target.is_symlink():
            raise ManifestError(f"symlink in bundle tree: {rel}")
        if not target.is_file():
            raise ManifestError(f"missing bundled path: {rel}")
        executable = "x" if (target.stat().st_mode & 0o100) else "-"
        digest.update(rel.encode("utf-8") + b"\0" + executable.encode("ascii"))
        digest.update(bytes.fromhex(hash_file(target)) + b"\n")
    return digest.hexdigest()


def validate_bundle_tree(
    root: Path, manifest: SelfHostManifest, relative_paths: Collection[str]
) -> tuple[str, ...]:
    """Compare an extracted tree against the manifest's canonical digest.

    Args:
        root: Extracted bundle root.
        manifest: The governing manifest.
        relative_paths: The bundle allowlist actually present on disk.

    Returns:
        Blocking errors (empty when the tree matches).
    """
    try:
        actual = compute_tree_sha256(root, relative_paths)
    except ManifestError as exc:
        return (str(exc),)
    if actual != manifest.bundle_tree_sha256:
        return (
            "bundle tree digest mismatch: the extracted files are not the "
            "qualified release content",
        )
    return ()
