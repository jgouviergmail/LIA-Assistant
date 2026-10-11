"""Render the original sculpted ocular layers for continuous native facial motion."""

import bpy
from mathutils import Vector

from .character import eye, move_lid
from .geometry import aim
from .materials import palette
from .staging import studio


def render_eye_layers(
    variant,
    output,
    samples,
    *,
    engine="BLENDER_EEVEE_NEXT",
    side="left",
    include_iris=True,
):
    """Both layers share one camera/canvas; never redraw the approved iris in CSS."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = studio(128, samples)
    scene.render.engine = engine
    ocular = eye(side, variant == "male", palette())
    for lid in ocular["lids"]:
        move_lid(lid, 1.0)
    camera = scene.camera
    camera.location += ocular["root"].location - Vector((0, 0, 1.14))
    camera.data.ortho_scale = 0.62
    aim(camera, ocular["root"].location)
    target = output.resolve() / variant
    target.mkdir(parents=True, exist_ok=True)
    layers = {
        "eye" if side == "left" else "eye-right": {
            ocular["white"],
            ocular["lid"],
            *ocular["lashes"],
        },
    }
    if include_iris:
        layers["iris"] = set(ocular["iris"].children_recursive)
    mask_name = "sclera-mask" if side == "left" else "sclera-mask-right"
    layers[mask_name] = {ocular["white"], ocular["lid"], *ocular["lashes"]}
    for name, visible in layers.items():
        if name == mask_name:
            # The lid and lashes OCCLUDE the white sphere in this alpha mask.
            # Simply hiding them would allow the moving iris to paint over ink.
            holdout = bpy.data.materials.new("original ink occlusion holdout")
            holdout.use_nodes = True
            nodes = holdout.node_tree.nodes
            nodes.clear()
            shader = nodes.new("ShaderNodeHoldout")
            result = nodes.new("ShaderNodeOutputMaterial")
            holdout.node_tree.links.new(shader.outputs[0], result.inputs["Surface"])
            for part in [ocular["lid"], *ocular["lashes"]]:
                part.data.materials.clear()
                part.data.materials.append(holdout)
        for obj in ocular["root"].children_recursive:
            obj.hide_render = obj not in visible
        scene.render.filepath = str(target / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        print(f"SPIRIT_ORGAN {variant}/{name}: 128px", flush=True)
