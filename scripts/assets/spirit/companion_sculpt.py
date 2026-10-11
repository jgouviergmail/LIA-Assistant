"""Shared anatomy and smooth surfaces; no borrowed character mesh or textures."""

from math import cos, exp, pi, sin

import bpy

from .character import empty, eye, eyebrow, move_lid
from .geometry import mesh, sphere, stroke

# Height, latitude power, depth, upper width, lower-hip growth, shoulder bulge.
# Female pears have a slender upper body; male pebbles carry a broader chest.
BEAN_PROFILES = {
    (False, False): (0.91, 0.98, 0.56, 0.58, 0.22, 0),
    (False, True): (0.87, 0.94, 0.56, 0.60, 0.22, 0),
    (True, False): (0.83, 0.65, 0.64, 0.89, 0.08, 0.04),
    (True, True): (0.80, 0.62, 0.64, 0.89, 0.08, 0.04),
}


def bean(name, male, material, *, lantern=False):
    vertices, faces = [], []
    rings, sectors = 56, 64
    height, power, depth, upper_width, hip_growth, shoulders = BEAN_PROFILES[(male, lantern)]
    for ring in range(rings + 1):
        theta = pi * ring / rings
        z = 0.94 + height * cos(theta)
        width = (
            upper_width
            + hip_growth * (1 - cos(theta))
            + shoulders * exp(-(((z - 1.29) / 0.30) ** 2))
        )
        radius = sin(theta) ** power
        for sector in range(sectors):
            angle = 2 * pi * sector / sectors
            x = width * radius * cos(angle)
            y = depth * radius * sin(angle)
            if y < 0:
                cheek = exp(-(((abs(x) - 0.42) / 0.23) ** 2) - ((z - 0.85) / 0.27) ** 2)
                y -= 0.032 * cheek
            vertices.append((x, y, z))
    for ring in range(rings):
        for sector in range(sectors):
            a, b = ring * sectors + sector, ring * sectors + (sector + 1) % sectors
            faces.append((a + sectors, b + sectors, b, a))
    return mesh(name, vertices, faces, material)


def limbs(male, material):
    parts = []
    for sign in [-1, 1]:
        parts.append(
            sphere(
                "little cupped hand",
                (sign * (0.99 if male else 0.80), -0.025, 0.69),
                (0.15, 0.17, 0.19) if male else (0.115, 0.145, 0.17),
                material,
            )
        )
        parts.append(
            sphere(
                "rounded little foot",
                (sign * (0.39 if male else 0.30), -0.17, 0.13),
                (0.20, 0.25, 0.135) if male else (0.17, 0.22, 0.115),
                material,
            )
        )
    return parts


def finish(parts, materials, male, *, portrait):
    root = empty("original companion sculpt")
    if portrait:
        eyes = [eye("left", male, materials), eye("right", male, materials)]
        for item in eyes:
            cutter = sphere(
                "temporary ocular carving tool",
                item["root"].location,
                (0.264, 0.16, item["height"] + 0.02),
                materials["body"],
            )
            bpy.context.view_layer.objects.active = parts[0]
            modifier = parts[0].modifiers.new("real sculpted eye recess", "BOOLEAN")
            modifier.operation, modifier.solver, modifier.object = (
                "DIFFERENCE",
                "EXACT",
                cutter,
            )
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            bpy.data.objects.remove(cutter, do_unlink=True)
            for lid in item["lids"]:
                move_lid(lid, 1)
        parts.extend(item["root"] for item in eyes)
        parts.extend(eyebrow(side, male, materials["ink"]) for side in ["left", "right"])
        parts.append(
            stroke(
                "small quiet sculpted smile",
                [(-0.11, -0.654, 0.842), (0, -0.674, 0.812), (0.11, -0.654, 0.842)],
                0.012,
                materials["ink"],
            )
        )
    for part in parts:
        part.parent = root
    return root
