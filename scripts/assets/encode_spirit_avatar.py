#!/usr/bin/env python3
"""Package real offline Blender frames into bounded, transparent WebP portraits.

Usage:
    python scripts/assets/encode_spirit_avatar.py \
        --input .tmp/spirit-avatar/frames --output apps/web/public/avatars/spirit/v1

Blender is only a build tool. Neither it nor the source/intermediate frames are
loaded by the application. Changing the shipped artwork requires a new asset
version directory and catalogue URL, rather than mutating an immutable version.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spirit.animation import BLINK_PHASES, EXPRESSIONS, LOOP_SECONDS

CLIP_BUDGET = 250 * 1024
COMPACT_CLIP_BUDGET = 80 * 1024
BODY_BUDGET = 32 * 1024
PACK_BUDGET = 3 * 1024 * 1024
SIZE = 192
COMPACT_SIZE = 96


def encode_static(source: Path, destination: Path, name: str, size: int) -> dict:
    """Preserve an original sculpted layer for continuous motion in the native rig."""
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"{name}.webp"
    pending = target.with_suffix(".pending.webp")
    with Image.open(source) as image:
        if image.size != (size, size):
            raise ValueError(f"Unexpected layer resolution: {source}: {image.size}")
        with image.convert("RGBA") as body:
            if body.getextrema()[3] != (0, 255):
                raise ValueError(f"Body needs real transparency: {source}")
            body.save(pending, "WEBP", quality=92, method=6)
    if pending.stat().st_size > BODY_BUDGET:
        pending.unlink()
        raise ValueError(f"Body exceeds {BODY_BUDGET} bytes: {source}")
    pending.replace(target)
    return {
        "size": size,
        "bytes": target.stat().st_size,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


def encode_body(source: Path, destination: Path) -> dict:
    """Keep the sculpt fixed; the companion's existing rig owns facial motion."""
    return encode_static(source, destination, "body", SIZE)


def frame_schedule(count: int, frame_ms: int, size: int) -> tuple[list[int], list[int]]:
    """Thin slow compact motion, retaining fast blinks and the full loop timing."""
    compact = size == COMPACT_SIZE and count >= 20
    indices = set(range(0, count, 2) if compact else range(count))
    if compact:
        for phase in BLINK_PHASES:
            center = round(phase * count)
            indices.update(
                index for index in (center - 1, center, center + 1) if 0 <= index < count
            )
    ordered = sorted(indices)
    ends = ordered[1:] + [count]
    return ordered, [(end - start) * frame_ms for start, end in zip(ordered, ends, strict=True)]


def encode_clip(
    source: Path,
    destination: Path,
    expression: str,
    duration_ms: int,
    *,
    size: int = SIZE,
) -> dict:
    """Preserve rendered motion and loop timing, with alpha and a fixed budget."""
    paths = sorted(source.glob("[0-9][0-9][0-9].png"))
    if len(paths) < 2:
        raise ValueError(f"Animation needs at least two rendered frames: {source}")
    frames = []
    for path in paths:
        with Image.open(path) as image:
            if image.size != (SIZE, SIZE):
                raise ValueError(f"Unexpected render resolution: {path}: {image.size}")
            frame = image.convert("RGBA")
            if frame.getextrema()[3] != (0, 255):
                raise ValueError(
                    f"Render must contain the character and a transparent background: {path}"
                )
            if size != SIZE:
                frame = frame.resize((size, size), Image.Resampling.LANCZOS)
            frames.append(frame)
    destination.mkdir(parents=True, exist_ok=True)
    still_path = destination / f"{expression}-still.webp"
    clip_path = destination / f"{expression}.webp"
    still_temp = still_path.with_suffix(".pending.webp")
    clip_temp = clip_path.with_suffix(".pending.webp")
    frames[0].save(still_temp, "WEBP", quality=92, method=6)
    indices, durations = frame_schedule(len(frames), duration_ms, size)
    selected = [frames[index] for index in indices]
    selected[0].save(
        clip_temp,
        "WEBP",
        save_all=True,
        append_images=selected[1:],
        duration=durations,
        loop=0,
        quality=65 if size == COMPACT_SIZE else 72,
        method=4,
        background=(0, 0, 0, 0),
    )
    budget = COMPACT_CLIP_BUDGET if size == COMPACT_SIZE else CLIP_BUDGET
    if clip_temp.stat().st_size > budget:
        clip_temp.unlink()
        still_temp.unlink()
        raise ValueError(f"Clip exceeds {budget} bytes: {source}")
    clip_temp.replace(clip_path)
    still_temp.replace(still_path)
    result = {
        "size": size,
        "frames": len(selected),
        "duration_ms": sum(durations),
        "clip_bytes": clip_path.stat().st_size,
        "still_bytes": still_path.stat().st_size,
        "sha256": hashlib.sha256(clip_path.read_bytes()).hexdigest(),
        "still_sha256": hashlib.sha256(still_path.read_bytes()).hexdigest(),
    }
    for frame in frames:
        frame.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--frame-ms", type=int, help="Override the choreography-derived frame timing"
    )
    args = parser.parse_args()
    records = {}
    bodies = {}
    organs = {}
    for variant in ("female", "male"):
        bodies[variant] = encode_body(args.input / variant / "body.png", args.output / variant)
        organs[variant] = {
            name: encode_static(
                args.input / variant / f"{name}.png", args.output / variant, name, 128
            )
            for name in ("eye", "eye-right", "iris", "sclera-mask", "sclera-mask-right")
        }
        for expression in EXPRESSIONS:
            key = f"compact/{variant}/{expression}"
            frame_count = len(list((args.input / variant / expression).glob("[0-9][0-9][0-9].png")))
            if frame_count < 2:
                raise ValueError(f"Missing rendered animation: {key}")
            timing = args.frame_ms or round(LOOP_SECONDS * 1000 / frame_count)
            records[key] = encode_clip(
                args.input / variant / expression,
                args.output / "compact" / variant,
                expression,
                timing,
                size=COMPACT_SIZE,
            )
            print(f"SPIRIT_ENCODE {key}: {records[key]['clip_bytes']} bytes", flush=True)
    total = sum(item["clip_bytes"] + item["still_bytes"] for item in records.values())
    total += sum(item["bytes"] for item in bodies.values())
    total += sum(item["bytes"] for layers in organs.values() for item in layers.values())
    if total > PACK_BUDGET:
        raise ValueError(f"Pack exceeds {PACK_BUDGET} bytes: {total}")
    manifest = {
        "version": 1,
        "size": COMPACT_SIZE,
        "total_bytes": total,
        "source": "Original offline Blender meshes/materials in scripts/assets/spirit",
        "portraits": records,
        "bodies": bodies,
        "organs": organs,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"SPIRIT_PACK: {len(records)} clips + stills, {total} bytes", flush=True)


if __name__ == "__main__":
    main()
