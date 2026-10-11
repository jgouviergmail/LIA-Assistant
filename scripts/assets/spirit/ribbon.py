"""An original satin hair bow, baked into the feminine spirit's existing assets."""

from math import pi

from .geometry import petal, sphere
from .materials import solid


def hair_ribbon():
    material = solid("raspberry satin hair ribbon", (0.55, 0.035, 0.21), 0.34)
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Sheen Weight"].default_value = 0.25
    shader.inputs["Coat Weight"].default_value = 0.2
    shader.inputs["Coat Roughness"].default_value = 0.24
    x, y, z = 0.16, -0.20, 1.98
    parts = []
    for sign in [-1, 1]:
        loop = petal(
            "folded ribbon loop " + str(sign),
            [
                (0, 0, 0),
                (-0.03, -0.025, sign * 0.07),
                (-0.045, 0.012, sign * 0.17),
                (-0.03, 0.038, sign * 0.205),
                (-0.008, 0.06, sign * 0.16),
                (0.01, 0.045, sign * 0.06),
                (0, 0.025, 0),
            ],
            [0.025, 0.06, 0.095, 0.07, 0.055, 0.034, 0.012],
            [0.018, 0.036, 0.045, 0.025, 0.018, 0.016, 0.008],
            material,
        )
        # The sweep's cross-section is upright across the horizontal fold.
        loop.rotation_euler.y = pi / 2
        loop.location = (x, y, z)
        parts.append(loop)
        parts.append(
            petal(
                "soft ribbon tail " + str(sign),
                [
                    (x + sign * 0.024, y, z - 0.012),
                    (x + sign * 0.062, y + 0.008, z - 0.07),
                    (x + sign * 0.08, y + 0.022, z - 0.15),
                    (x + sign * 0.105, y + 0.025, z - 0.195),
                ],
                [0.026, 0.04, 0.041, 0.027],
                [0.014, 0.018, 0.018, 0.012],
                material,
            )
        )
    parts.append(
        sphere("small satin ribbon knot", (x, y - 0.028, z), (0.05, 0.046, 0.064), material)
    )
    return parts
