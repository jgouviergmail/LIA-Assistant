"""Preserve the editable production and its licensed resources, without caches."""

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
OUTPUT = ROOT / "exports/lia-motion"
OUTPUT.mkdir(parents=True, exist_ok=True)


def inside_root(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(ROOT.resolve()):
        raise ValueError(f"Archive member outside the production workspace: {path}")
    return resolved


def production_files() -> set[Path]:
    files = {
        inside_root(path)
        for folder in ("src", "scripts", "tests", "licenses")
        for path in (PROJECT / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    files.update(
        inside_root(path)
        for path in PROJECT.iterdir()
        if path.is_file() and path.suffix in (".json", ".ts", ".md")
    )
    files.add(inside_root(PROJECT / ".gitignore"))
    for filename in (
        "LICENSE.md",
        "HTML-EVIDENCE.md",
        "html-evidence-provenance.json",
        "license-evidence.html",
        "sunlit-groove.flac",
        "music.wav",
        "pulsar-original.mp3",
        "music-v2.wav",
        "PULSAR-LICENSE.md",
        "pulsar-license-evidence.html",
        "pulsar-usage-evidence.html",
    ):
        files.add(inside_root(PROJECT / "public/audio" / filename))
    files.update(
        inside_root(path)
        for path in (PROJECT / "public/capture-v2").rglob("*")
        if path.is_file()
    )
    for folder in ("mascot-film", "audio/v3", "audio/v4", "audio/v5", "capture-v4"):
        files.update(
            inside_root(path)
            for path in (PROJECT / "public" / folder).rglob("*")
            if path.is_file()
        )
    for folder in ("avatars", "fonts", "screenshots/proof"):
        files.update(
            inside_root(path)
            for path in (ROOT / "apps/web/public" / folder).rglob("*")
            if path.is_file()
        )
    # Native expression recipes remain at their repository paths in the archive.
    for folder in ("rig", "smiley"):
        files.update(
            inside_root(path)
            for path in (ROOT / "apps/web/src/components/eyes" / folder).rglob("*")
            if path.is_file() and "__tests__" not in path.parts
        )
    for filename in (
        "apps/web/public/icon.svg",
        "apps/web/src/components/eyes/eye-styles.ts",
        "apps/web/src/components/eyes/expression-engine.ts",
        "apps/web/src/components/eyes/monitor-geometry.ts",
        "apps/web/src/components/landing/editorial/chapters-data.ts",
        "apps/web/src/lib/landing/beat-sync.ts",
        "apps/web/src/lib/landing/beats-schema.ts",
        "apps/web/src/lib/landing/media.ts",
        "apps/web/src/lib/zod.ts",
        "apps/web/src/lib/api-client.ts",
        "apps/web/src/components/landing/video/PresentationButton.tsx",
        "apps/web/src/components/landing/video/PresentationDialog.tsx",
        "apps/web/src/components/landing/video/use-landing-presentation.ts",
        "docs/technical/MOTION_DESIGN.md",
        "docs/architecture/ADR-341-Editable-Motion-Production-And-Exclusive-Presentation.md",
        "apps/web/src/lib/landing/attention-background.ts",
        "apps/web/src/components/landing/CosmicBackdrop.tsx",
        "apps/web/src/components/landing/AttentionBackdrop.tsx",
        "apps/web/src/styles/globals.css",
        "scripts/assets/encode_landing_video.py",
        "apps/api/tests/unit/scripts/test_encode_landing_video_beats.py",
        "apps/api/tests/unit/scripts/test_encode_landing_video_playlist.py",
        "package.json",
        "Taskfile.yml",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "apps/web/package.json",
        "LICENSE",
    ):
        path = ROOT / filename
        if path.is_file():
            files.add(inside_root(path))
    for filename in (
        "feature-coverage.json",
        "screenplay.json",
        "storyboard.md",
        "compositions.json",
        "native-shot-plan.json",
        "main-delivery.json",
        "focus-delivery.json",
        "master25-audio-measurement.json",
        "quality-report.json",
        "all-qualification.json",
        "main-qualification.json",
        "focus-qualification.json",
        "master-qualification.json",
        "story24-qualification.json",
        "native-xl-reference.json",
        "presentation-coverage.json",
        "screenplay-v4.json",
        "presentation-delivery-review.json",
        "presentation-browser-review.json",
        "presentation-geometry-review.json",
        "review-v6/review-all.json",
        "review-v5/review-all.json",
        "review-v5/product-review.json",
        "patch-native-labels-full.json",
        "patch-native-labels-landing.json",
        "patch-native-labels-master25.json",
        "revision/v5-before-native-labels/patch-native-labels-before-probe-budget.mjs",
    ):
        if (OUTPUT / filename).is_file():
            files.add(inside_root(OUTPUT / filename))
    return files


files = sorted(production_files())
revision = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
).strip()
date = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
generation_match = re.search(
    r"PRESENTATION_REVISION\s*=\s*['\"]([^'\"]+)",
    (PROJECT / "src/presentation-plan.ts").read_text(encoding="utf-8"),
)
if generation_match is None:
    raise ValueError("Active presentation revision is not declared")
generation = generation_match.group(1)
snapshot = {
    "createdAt": date,
    "baseRevision": revision,
    "scope": "Editable production overlay for the LIA repository at baseRevision",
    "currentComposition": "LIA-Full",
    "generation": generation,
    "editorialStatus": "Authored film and standalone focuses; technical and editorial qualifications remain distinct",
    "rebuild": "Restore onto that checkout; install locked web and motion dependencies.",
    "files": {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    },
}
target = OUTPUT / f"lia-motion-sources-{date}.zip"
with ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
    for path in files:
        archive.write(path, path.relative_to(ROOT).as_posix())
    archive.writestr(
        "PRODUCTION-SNAPSHOT.json",
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
    )
    archive.writestr(
        "REBUILD.md",
        "# Rebuild this production\n\n"
        f"Repository base: `{revision}`. Active generation: `{generation}`.\n\n"
        "This archive is an editable overlay for that LIA checkout. "
        "Extract at the repository root, retaining paths.\n\n"
        "1. Install locked frontend dependencies with `pnpm install --frozen-lockfile`.\n"
        "2. In `tools/lia-motion`, run `npm ci`, then `npm run assets`.\n"
        "3. Run `npm run check`, then `npm run studio` to edit.\n"
        "4. With Python/NumPy and FFmpeg available, run "
        "`python scripts/prepare_music_film.py` from `tools/lia-motion` to rebuild audio.\n"
        "5. Run `node --experimental-strip-types scripts/presentation-report.mjs` "
        "for editorial source/timing reports, and `node --experimental-strip-types "
        "scripts/verify-presentation-geometry.mjs all` for rendered DOM measurements.\n"
        "6. Run `node scripts/render.mjs all`, `node scripts/render.mjs focus` "
        "and `node scripts/render.mjs master25` for complete exports.\n"
        "7. Run `node scripts/package-media.mjs main`, "
        "`node scripts/package-media.mjs focus`, then "
        "`node --experimental-strip-types scripts/verify-delivery.mjs all` "
        "to package and measure delivered media.\n"
        "8. Run `node scripts/preview-presentation.mjs` and serve the export "
        "directory over HTTP for continuous editorial/audio review.\n\n"
        "Historical LIA-Legacy*, LIA-Proof30 and LIA-Story24 remain named separately. "
        "Local technical reports do not certify broadcaster acceptance.\n\n"
        "See `docs/technical/MOTION_DESIGN.md` for updates and publication. "
        "Caches, installed dependencies, accounts and secrets are excluded. "
        "Original recordings, licenses/provenance, native resources, "
        "editable sources and their hashes are retained.\n",
    )
with ZipFile(target) as archive:
    bad = archive.testzip()
    if bad:
        raise ValueError(f"Archive checksum failed: {bad}")
    for name, expected_hash in snapshot["files"].items():
        if hashlib.sha256(archive.read(name)).hexdigest() != expected_hash:
            raise ValueError(f"Archived production fingerprint differs: {name}")
print(f"Production archive verified: {target} ({len(files)} files)")
