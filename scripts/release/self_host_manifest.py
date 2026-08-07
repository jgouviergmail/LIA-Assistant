"""Candidate-manifest assembly and qualified promotion (ADR-215, B02).

Imports the shared schema from ``scripts.install.manifest`` (single source
of truth — this module never redeclares it). Promotion is the ONLY path from
``candidate`` to ``passed``: it validates hash-bound qualification evidence
covering the exact four architecture/mode rows, then copies every canonical
field and flips nothing but the qualification.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.install.manifest import (  # noqa: E402
    ManifestError,
    SelfHostManifest,
    hash_file,
    load_manifest,
    manifest_to_payload,
    validate_manifest,
)

DEPENDENCY_CATALOGUE = Path(__file__).resolve().parent / "self_host_dependencies.json"

#: The exact disposable qualification matrix (G3) a promotion must prove.
REQUIRED_QUALIFICATION_ROWS = frozenset(
    (platform, mode)
    for platform in ("linux/amd64", "linux/arm64")
    for mode in ("local", "prebuilt")
)


def load_dependency_catalogue() -> list[dict[str, str]]:
    """Read the exact third-party service → upstream-reference catalogue."""
    entries = json.loads(DEPENDENCY_CATALOGUE.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("dependency catalogue must be a JSON list")
    return [
        {str(key): str(value) for key, value in entry.items()} for entry in entries
    ]


def write_candidate_manifest(
    *, manifest: SelfHostManifest, output: Path
) -> SelfHostManifest:
    """Validate and persist a candidate manifest.

    Args:
        manifest: Fully assembled candidate (qualification must be
            ``candidate``).
        output: Destination JSON path.

    Returns:
        The persisted manifest.

    Raises:
        ManifestError: On structural errors or a non-candidate input.
    """
    if manifest.qualification != "candidate":
        raise ManifestError("candidate assembly requires qualification='candidate'")
    errors = validate_manifest(manifest)
    if errors:
        raise ManifestError("; ".join(errors))
    output.write_text(
        json.dumps(manifest_to_payload(manifest), indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def write_passed_manifest(
    *,
    candidate_path: Path,
    qualification_evidence_path: Path,
    output: Path,
) -> SelfHostManifest:
    """Promote a candidate whose qualification evidence fully matches.

    Args:
        candidate_path: The exact candidate file the disposable rows ran.
        qualification_evidence_path: Evidence JSON binding that file's
            SHA-256 to the four passing architecture/mode rows.
        output: Destination for the passed manifest.

    Returns:
        The promoted manifest (identical fields, qualification flipped).

    Raises:
        ManifestError: On any hash, matrix, or result mismatch.
    """
    candidate = load_manifest(candidate_path, required_qualification="candidate")
    try:
        evidence = json.loads(
            qualification_evidence_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"unreadable qualification evidence: {exc}") from exc

    actual_digest = hash_file(candidate_path)
    if evidence.get("candidate_sha256") != actual_digest:
        raise ManifestError(
            "qualification evidence does not bind THIS candidate manifest "
            "(sha256 mismatch)"
        )
    rows = evidence.get("rows", [])
    seen = set()
    for row in rows:
        key = (row.get("platform"), row.get("mode"))
        if row.get("result") != "passed":
            raise ManifestError(f"qualification row {key} did not pass")
        seen.add(key)
    if seen != REQUIRED_QUALIFICATION_ROWS:
        missing = REQUIRED_QUALIFICATION_ROWS - seen
        raise ManifestError(
            f"qualification matrix incomplete; missing rows: {sorted(missing)}"
        )

    promoted = SelfHostManifest(
        **{**candidate.__dict__, "qualification": "passed"}
    )
    output.write_text(
        json.dumps(manifest_to_payload(promoted), indent=2) + "\n",
        encoding="utf-8",
    )
    return promoted


def _main(argv: list[str] | None = None) -> int:
    """CLI: promote a candidate (`--candidate --evidence --output`) or print
    the app image references of a manifest (`--print-images MANIFEST`)."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-images", type=Path)
    args = parser.parse_args(argv)
    if args.print_images:
        manifest = load_manifest(args.print_images)
        for image in manifest.images:
            if image.service in ("api", "web"):
                print(f"{image.service} {image.reference}")
        return 0
    if not (args.candidate and args.evidence and args.output):
        parser.error("--candidate, --evidence and --output are required")
    write_passed_manifest(
        candidate_path=args.candidate,
        qualification_evidence_path=args.evidence,
        output=args.output,
    )
    print(f"passed manifest written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
