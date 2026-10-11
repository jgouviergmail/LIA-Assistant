#!/usr/bin/env python3
"""Build the original static 3D monitor body; the browser supplies its live face.

Blender owns all geometry, material, lighting and WebP encoding here. The
application loads one 192 px RGBA still and runs its existing eye rig only.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spirit.geometry import aim
from spirit.monitor import CAMERA_SCALE, CAMERA_TARGET_Z, build_monitor, screen_layout
from spirit.staging import studio

SIZE = 192
ASSET_BUDGET = 32 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=48)
    parser.add_argument("--version", type=int, default=2)
    parser.add_argument("--supersampling", type=int, choices=(1, 2), default=2)
    parser.add_argument(
        "--engine",
        choices=("CYCLES", "BLENDER_EEVEE_NEXT"),
        default="BLENDER_EEVEE_NEXT",
    )
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    if not 1 <= args.samples <= 128:
        raise ValueError("The offline sample budget must be 1–128")
    if args.version < 1:
        raise ValueError("The published version must be positive")
    target = args.output.resolve()
    target.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = studio(SIZE * args.supersampling, args.samples)
    scene.render.engine = args.engine
    scene.camera.location = (0, -7, CAMERA_TARGET_Z)
    scene.camera.data.ortho_scale = CAMERA_SCALE
    aim(scene.camera, (0, 0, CAMERA_TARGET_Z))
    build_monitor()
    scene.render.filepath = str(target / "body.png")
    bpy.ops.render.render(write_still=True)
    # Render Result exposes render tiles, not a resizable image buffer. Reload
    # the authored RGBA still to package its bounded delivery resolution.
    delivery_image = bpy.data.images.load(
        str(target / "body.png"), check_existing=False
    )
    delivery_image.scale(SIZE, SIZE)
    # The PNG already contains the studio's AgX look. A second AgX transform
    # would flatten the pearl/metal highlights while packaging that artwork.
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.image_settings.file_format = "WEBP"
    scene.render.image_settings.quality = 92
    pending = target / "body.pending.webp"
    delivery_image.save_render(filepath=str(pending), scene=scene)
    if pending.stat().st_size > ASSET_BUDGET:
        pending.unlink()
        raise ValueError(f"The monitor body exceeds {ASSET_BUDGET} bytes")
    path = target / "body.webp"
    pending.replace(path)
    manifest = {
        "version": args.version,
        "size": SIZE,
        "bytes": path.stat().st_size,
        "quality": 92,
        "render": {
            "engine": args.engine,
            "samples": args.samples,
            "threads": 2,
            "supersampling": args.supersampling,
        },
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "screen": screen_layout(),
        "source": "Original procedural Blender monitor in scripts/assets/spirit/monitor.py",
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"MONITOR_RENDER {manifest['bytes']} bytes, RGBA {SIZE}px", flush=True)


if __name__ == "__main__":
    main()
