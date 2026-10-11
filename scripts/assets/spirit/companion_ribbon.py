"""Place the existing original satin bow without changing Spirit's source bow."""

from mathutils import Vector

from .character import empty
from .ribbon import hair_ribbon


def companion_ribbon(anchor, *, scale=0.78):
    root = empty("small tied pink companion ribbon")
    original_anchor = Vector((0.16, -0.20, 1.98))
    for part in hair_ribbon():
        part.parent = root
        part.location -= original_anchor
        # This fresh material belongs only to the newly authored bow. The
        # original Spirit function and its default output remain untouched.
        shader = part.data.materials[0].node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (0.78, 0.075, 0.29, 1)
    root.location = anchor
    root.scale = (scale, scale, scale)
    root.rotation_euler.y = -0.14
    return root
