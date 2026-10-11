"""Controlled ceramic lighting while preserving the shared face projection."""

import bpy

from .staging import studio


def character_studio(size, samples):
    scene = studio(size, samples)
    scene.view_settings.exposure = -0.35
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.055
    lights = {
        "warm porcelain studio key": (215, (1, 0.96, 0.90)),
        "cool softbox fill": (42, (0.86, 0.93, 1)),
        "blue opal rim": (110, (0.75, 0.92, 1)),
        "soft rosy rim": (85, (1, 0.82, 0.65)),
        "eye catchlight softbox": (25, (1, 0.98, 0.94)),
    }
    for name, (energy, color) in lights.items():
        bpy.data.objects[name].data.energy = energy
        bpy.data.objects[name].data.color = color
    return scene
