"""Assemble the complete candidate release identity (ADR-215, B02/B05/B06).

One CLI the release workflow orchestrates (the workflow never implements):
consumes the per-app digest records and the dependency digest resolution
produced by the buildx steps, builds the deterministic source-context and
host bundle, and writes the candidate manifest whose hashes bind them all.

Usage::

    python -m scripts.release.assemble_candidate \
        --version v1.29.0 --source-sha <40hex> --built-at <iso8601-utc> \
        --app-digests api=api.json --app-digests web=web.json \
        --dependency-digests deps.json \
        --sbom api=sbom-api.cdx.json --sbom web=sbom-web.cdx.json \
        --out-dir dist/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.install.manifest import (  # noqa: E402
    ImageArtifact,
    PlatformArtifact,
    SelfHostManifest,
    hash_file,
)
from scripts.release.build_self_host_bundle import (  # noqa: E402
    build_bundle,
)
from scripts.release.build_self_host_source_context import (  # noqa: E402
    build_source_context,
)
from scripts.release.self_host_manifest import (  # noqa: E402
    write_candidate_manifest,
)

BUNDLE_NAME = "lia-self-host-bundle.tar.gz"
SOURCE_CONTEXT_NAME = "lia-self-host-source-context.tar.gz"
MANIFEST_NAME = "lia-self-host-manifest.json"


def _load_image(service: str, path: Path) -> ImageArtifact:
    record = json.loads(path.read_text(encoding="utf-8"))
    return ImageArtifact(
        service=service,
        reference=str(record["reference"]),
        platforms=tuple(
            PlatformArtifact(
                platform=row["platform"],
                manifest_digest=str(row["manifest_digest"]),
                config_digest=str(row["config_digest"]),
            )
            for row in record["platforms"]
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Assemble bundle, source context, SBOM hashes, and the manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--built-at", required=True)
    parser.add_argument(
        "--app-digests", action="append", required=True, metavar="APP=FILE"
    )
    parser.add_argument("--dependency-digests", required=True, type=Path)
    parser.add_argument("--sbom", action="append", required=True, metavar="APP=FILE")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    images: list[ImageArtifact] = []
    for spec in args.app_digests:
        service, _, file_name = spec.partition("=")
        images.append(_load_image(service, Path(file_name)))
    deps = json.loads(args.dependency_digests.read_text(encoding="utf-8"))
    for record in deps:
        images.append(
            _load_image(str(record["service"]), Path(str(record["file"])))
            if "file" in record
            else ImageArtifact(
                service=str(record["service"]),
                reference=str(record["reference"]),
                platforms=tuple(
                    PlatformArtifact(
                        platform=row["platform"],
                        manifest_digest=str(row["manifest_digest"]),
                        config_digest=str(row["config_digest"]),
                    )
                    for row in record["platforms"]
                ),
            )
        )

    sboms: dict[str, str] = {}
    for spec in args.sbom:
        app, _, file_name = spec.partition("=")
        sboms[app] = hash_file(Path(file_name))

    source_context_path = args.out_dir / SOURCE_CONTEXT_NAME
    context_digests = build_source_context(
        REPO, source_context_path, source_sha=args.source_sha
    )
    bundle_path = args.out_dir / BUNDLE_NAME
    bundle_digests = build_bundle(REPO, source_context_path, bundle_path)
    (args.out_dir / f"{BUNDLE_NAME}.sha256").write_text(
        f"{bundle_digests.archive_sha256}  {BUNDLE_NAME}\n", encoding="utf-8"
    )

    manifest = SelfHostManifest(
        schema_version=1,
        release_version=args.version,
        source_sha=args.source_sha,
        built_at=args.built_at,
        bundle_archive_sha256=bundle_digests.archive_sha256,
        bundle_tree_sha256=bundle_digests.tree_sha256,
        source_context_archive_sha256=context_digests.archive_sha256,
        source_context_tree_sha256=context_digests.tree_sha256,
        images=tuple(images),
        sboms=sboms,
        qualification="candidate",
    )
    write_candidate_manifest(manifest=manifest, output=args.out_dir / MANIFEST_NAME)
    print(f"candidate manifest: {hash_file(args.out_dir / MANIFEST_NAME)}")
    print(f"bundle archive:     {bundle_digests.archive_sha256}")
    print(f"bundle tree:        {bundle_digests.tree_sha256}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
