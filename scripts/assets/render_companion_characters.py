"""Author Mousse/Lumo offline. Only their fixed transparent bodies ship.

Render draft references first; output contains intermediate PNGs alongside
the bounded WebPs/manifest. Publish only body.webp and manifest.json after review.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spirit.lumen import build_lumen
from spirit.moss import build_moss
from spirit.companion_staging import character_studio

BODY_BUDGET = 32 * 1024
PACK_BUDGET = 80 * 1024
BUILDERS = {"moss": build_moss, "lumen": build_lumen}


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--character", choices=(*BUILDERS, "both"), default="both")
    parser.add_argument("--variant", choices=("female", "male", "both"), default="both")
    parser.add_argument("--samples", type=int, default=48)
    parser.add_argument(
        "--engine",
        choices=("CYCLES", "BLENDER_EEVEE_NEXT"),
        default="BLENDER_EEVEE_NEXT",
    )
    parser.add_argument(
        "--portraits",
        action="store_true",
        help="Also render neutral PNG art references, never delivered",
    )
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    if not 1 <= args.samples <= 128:
        raise ValueError("The offline sample budget must be 1–128")
    return args


def prepare(character, variant, args, *, portrait=False):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = character_studio(192, args.samples)
    scene.render.engine = args.engine
    BUILDERS[character](variant, portrait=portrait)
    return scene


def projection(scene):
    def point(x, y, z):
        projected = world_to_camera_view(scene, scene.camera, Vector((x, y, z)))
        return [round(projected.x, 6), round(1 - projected.y, 6)]

    return {
        "eye_centers": [point(-0.32, -0.50, 1.16), point(0.32, -0.50, 1.16)],
        "mouth_center": point(0, -0.671, 0.83),
        "ortho_scale": scene.camera.data.ortho_scale,
    }


def body_asset(scene, target):
    scene.render.filepath = str(target / "body.png")
    bpy.ops.render.render(write_still=True)
    scene.render.image_settings.file_format = "WEBP"
    scene.render.image_settings.quality = 92
    path = target / "body.webp"
    bpy.data.images["Render Result"].save_render(filepath=str(path), scene=scene)
    data = path.read_bytes()
    if len(data) > BODY_BUDGET:
        raise ValueError("The fixed body exceeds its delivery budget")
    return {"size": 192, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    args = arguments()
    characters = tuple(BUILDERS) if args.character == "both" else (args.character,)
    variants = ("female", "male") if args.variant == "both" else (args.variant,)
    for character in characters:
        directory = args.output.resolve() / character / "v1"
        assets = {}
        for variant in variants:
            target = directory / variant
            target.mkdir(parents=True, exist_ok=True)
            scene = prepare(character, variant, args)
            assets[f"{variant}/body"] = body_asset(scene, target)
            face = projection(scene)
            print(
                f"COMPANION_BODY {character}/{variant}: {assets[f'{variant}/body']['bytes']} bytes",
                flush=True,
            )
            if args.portraits:
                scene = prepare(character, variant, args, portrait=True)
                scene.render.filepath = str(target / "neutral.png")
                bpy.ops.render.render(write_still=True)
                print(f"COMPANION_PORTRAIT {character}/{variant}", flush=True)
        total = sum(value["bytes"] for value in assets.values())
        manifest = {
            "version": 1,
            "character": character,
            "total_bytes": total,
            "source": "Original procedural sculpture in scripts/assets/render_companion_characters.py",
            "render": {"engine": args.engine, "samples": args.samples, "threads": 2},
            "projection": face,
            "assets": assets,
        }
        encoded = json.dumps(manifest, indent=2) + "\n"
        if total + len(encoded.encode("utf-8")) > PACK_BUDGET:
            raise ValueError("The companion pack exceeds its delivery budget")
        (directory / "manifest.json").write_text(encoded, encoding="utf-8")


if __name__ == "__main__":
    main()
