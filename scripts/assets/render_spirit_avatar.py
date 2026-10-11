#!/usr/bin/env python3
"""Render the original LIA spirit with portable Blender, offline and single-process.

Example:
    blender --background --factory-startup --threads 2 --python \
        scripts/assets/render_spirit_avatar.py -- --output .tmp/spirit-avatar/frames

Only final WebP assets ship to LIA. Blender, intermediate PNGs and source scenes
never run in the API/web containers. The geometry and materials are original;
the approved AI-generated character sheet is an art reference, not a mesh.
"""

import argparse
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spirit.animation import EXPRESSIONS, LOOP_SECONDS, pose_at
from spirit.character import apply_pose, build
from spirit.organ_staging import render_eye_layers
from spirit.staging import studio


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=("female", "male", "both"), default="both")
    parser.add_argument("--expressions", nargs="+", choices=EXPRESSIONS, default=list(EXPRESSIONS))
    parser.add_argument("--frames", type=int, default=40)
    parser.add_argument("--size", type=int, default=192)
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--engine", choices=("CYCLES", "BLENDER_EEVEE_NEXT"), default="CYCLES")
    parser.add_argument("--save-scene", action="store_true")
    parser.add_argument(
        "--body-only",
        action="store_true",
        help="Clean static sculpt for the live companion rig",
    )
    parser.add_argument(
        "--organs-only",
        action="store_true",
        help="Original ocular layers for the live rig",
    )
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def main():
    args = arguments()
    if args.frames < 1 or args.frames > 80 or args.size < 64 or args.size > 1024:
        raise ValueError("Frames must be 1–80 and size must be 64–1024")
    variants = ("female", "male") if args.variant == "both" else (args.variant,)
    if args.organs_only:
        for variant in variants:
            render_eye_layers(variant, args.output, args.samples, engine=args.engine)
            render_eye_layers(
                variant,
                args.output,
                args.samples,
                engine=args.engine,
                side="right",
                include_iris=False,
            )
        return
    for variant in variants:
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        scene = studio(args.size, args.samples)
        scene.render.engine = args.engine
        character = build(variant, body_only=args.body_only)
        if args.body_only:
            target = args.output.resolve() / variant
            target.mkdir(parents=True, exist_ok=True)
            scene.render.filepath = str(target / "body.png")
            bpy.ops.render.render(write_still=True)
            print(f"SPIRIT_BODY {variant}: {args.size}px", flush=True)
            continue
        for expression in args.expressions:
            target = args.output.resolve() / variant / expression
            target.mkdir(parents=True, exist_ok=True)
            for frame in range(args.frames):
                apply_pose(character, pose_at(expression, LOOP_SECONDS * frame / args.frames))
                scene.render.filepath = str(target / f"{frame:03d}.png")
                bpy.ops.render.render(write_still=True)
            print(
                f"SPIRIT_RENDER {variant}/{expression}: {args.frames} frames, {args.size}px",
                flush=True,
            )
        if args.save_scene:
            bpy.ops.wm.save_as_mainfile(
                filepath=str(args.output.resolve() / f"lia-spirit-{variant}.blend")
            )


if __name__ == "__main__":
    main()
