"""Author the original golden sphere fallback and ocular layers offline."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spirit.geometry import aim, sphere, stroke
from spirit.materials import solid
from spirit.ribbon import hair_ribbon
from spirit.staging import light, studio

PACK_BUDGET = 128 * 1024
LAYER_BUDGET = 32 * 1024


def golden_material():
    material = solid("original golden ceramic smiley", (1, 0.65, 0.005), 0.24)
    nodes, links = material.node_tree.nodes, material.node_tree.links
    surface = nodes.new("ShaderNodeNewGeometry")
    axes = nodes.new("ShaderNodeSeparateXYZ")
    links.new(surface.outputs["Normal"], axes.inputs["Vector"])
    front = nodes.new("ShaderNodeMath")
    front.operation = "MULTIPLY"
    front.inputs[1].default_value = -1
    links.new(axes.outputs["Y"], front.inputs[0])
    pigment = nodes.new("ShaderNodeValToRGB")
    pigment.color_ramp.elements[0].color = (0.85, 0.17, 0.001, 1)
    pigment.color_ramp.elements[1].color = (1, 0.65, 0.005, 1)
    links.new(front.outputs["Value"], pigment.inputs["Fac"])
    shader = material.node_tree.nodes.get("Principled BSDF")
    links.new(pigment.outputs["Color"], shader.inputs["Base Color"])
    shader.inputs["Coat Weight"].default_value = 0.55
    shader.inputs["Coat Roughness"].default_value = 0.14
    shader.inputs["Subsurface Weight"].default_value = 0.055
    shader.inputs["Subsurface Radius"].default_value = (0.3, 0.16, 0.06)
    return material


def scene_for(size, samples, scale):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = studio(size, samples)
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.camera.location = (0, -7, 1)
    scene.camera.data.ortho_scale = scale
    aim(scene.camera, (0, 0, 1))
    for name, color in [
        ("blue opal rim", (1, 0.83, 0.42)),
        ("soft rosy rim", (1, 0.63, 0.16)),
    ]:
        bpy.data.objects[name].data.color = color
    for name, power in [
        ("warm porcelain studio key", 160),
        ("cool softbox fill", 45),
        ("blue opal rim", 180),
        ("soft rosy rim", 140),
        ("eye catchlight softbox", 0),
    ]:
        bpy.data.objects[name].data.energy = power
    light("warm lower bounce", (0, -3, -1), 55, (1, 0.68, 0.25), 3)
    bpy.data.objects["warm lower bounce"].data.specular_factor = 0
    return scene


def save_layer(scene, output, name, manifest):
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    scene.render.image_settings.file_format = "WEBP"
    scene.render.image_settings.quality = 92
    path = output / f"{name}.webp"
    bpy.data.images["Render Result"].save_render(filepath=str(path), scene=scene)
    if path.stat().st_size > LAYER_BUDGET:
        raise ValueError(f"{name} exceeds the static layer budget")
    manifest[name] = {
        "size": scene.render.resolution_x,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    print(f"SMILEY_LAYER {name}: {manifest[name]['bytes']} bytes", flush=True)


def render_body(output, samples, manifest):
    scene = scene_for(192, samples, 2.04)
    # Keep the studio's upper reflections, without a bright spot at the jaw.
    bpy.data.objects["warm lower bounce"].data.energy = 0
    ambient = scene.world.node_tree.nodes["Background"]
    ambient.inputs["Color"].default_value = (1, 0.82, 0.46, 1)
    ambient.inputs["Strength"].default_value = 0.7
    sphere("smooth golden body", (0, 0, 1), (1, 1, 1), golden_material())
    save_layer(scene, output, "body", manifest)


def render_eye(output, samples, manifest):
    scene = scene_for(128, samples, 1.18)
    socket = sphere(
        "fine recessed ocular rim",
        (0, 0.025, 1),
        (0.422, 0.12, 0.448),
        golden_material(),
    )
    white = sphere(
        "domed ivory sclera",
        (0, -0.055, 1),
        (0.405, 0.18, 0.43),
        solid("warm white eye enamel", (0.96, 0.945, 0.90), 0.16),
    )
    lid = stroke(
        "sculpted upper eyelid",
        [(-0.397, -0.10, 1.08), (0, -0.245, 1.424), (0.397, -0.10, 1.08)],
        0.012,
        solid("soft brown ocular ink", (0.095, 0.049, 0.019), 0.24),
    )
    iris_material = solid("warm hazel glass iris", (0.075, 0.038, 0.012), 0.12)
    iris_material.node_tree.nodes.get("Principled BSDF").inputs[
        "Coat Weight"
    ].default_value = 1
    iris = sphere(
        "rounded hazel iris", (0, -0.238, 1), (0.255, 0.028, 0.244), iris_material
    )
    pupil = sphere(
        "deep glass pupil",
        (0, -0.265, 1),
        (0.183, 0.012, 0.174),
        solid("dark glass pupil", (0.001, 0.002, 0.004), 0.075),
    )
    glint_material = solid("ocular catchlights", (1, 0.99, 0.96), 0.16)
    glints = [
        sphere(
            "broad corneal reflection",
            (-0.055, -0.28, 1.083),
            (0.037, 0.006, 0.042),
            glint_material,
        ),
        sphere(
            "deep corneal reflection",
            (0.065, -0.28, 0.929),
            (0.015, 0.004, 0.017),
            glint_material,
        ),
    ]
    for obj in [iris, pupil, *glints]:
        obj.hide_render = True
    save_layer(scene, output, "eye", manifest)
    for obj in [socket, white, lid]:
        obj.hide_render = True
    for obj in [iris, pupil, *glints]:
        obj.hide_render = False
    save_layer(scene, output, "iris", manifest)
    for obj in [iris, pupil, *glints]:
        obj.hide_render = True
    white.hide_render = False
    lid.hide_render = False
    holdout = bpy.data.materials.new("upper lid occlusion")
    holdout.use_nodes = True
    nodes = holdout.node_tree.nodes
    nodes.clear()
    shader = nodes.new("ShaderNodeHoldout")
    result = nodes.new("ShaderNodeOutputMaterial")
    holdout.node_tree.links.new(shader.outputs[0], result.inputs["Surface"])
    lid.data.materials.clear()
    lid.data.materials.append(holdout)
    save_layer(scene, output, "sclera-mask", manifest)


def render_bow(output, samples, manifest):
    scene = scene_for(128, samples, 0.52)
    hair_ribbon()
    scene.camera.location = (0.16, -7, 1.935)
    aim(scene.camera, (0.16, 0, 1.935))
    save_layer(scene, output, "bow", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=64)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--body-only", action="store_true", help="Preserve the approved ocular layers"
    )
    selection.add_argument(
        "--bow-only", action="store_true", help="Add only the original satin bow"
    )
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    if not 1 <= args.samples <= 128:
        raise ValueError("The offline sample budget must be 1–128")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    assets = (
        json.loads((output / "manifest.json").read_text(encoding="utf-8"))["assets"]
        if args.body_only or args.bow_only
        else {}
    )
    if not args.bow_only:
        render_body(output, args.samples, assets)
    if not args.body_only and not args.bow_only:
        render_eye(output, args.samples, assets)
    if not args.body_only:
        render_bow(output, args.samples, assets)
    total = sum(layer["bytes"] for layer in assets.values())
    if total > PACK_BUDGET:
        raise ValueError("The smiley pack exceeds its static delivery budget")
    manifest = {
        "version": 1,
        "total_bytes": total,
        "render": {"engine": "CYCLES", "samples": args.samples, "threads": 2},
        "source": "Original procedural Blender sculpt in scripts/assets/render_smiley_avatar.py",
        "assets": assets,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
