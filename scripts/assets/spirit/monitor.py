"""Original rounded studio monitor, leaving its display empty for the eye rig."""

from math import cos, pi, sin

import bpy

from .geometry import mesh, sphere
from .materials import solid

SCREEN_WIDTH = 1.94
SCREEN_HEIGHT = 1.10
SCREEN_RADIUS = 0.09
SCREEN_CENTER_Z = 1.44
SCREEN_FRONT_Y = -0.10
CAMERA_TARGET_Z = 1.20
CAMERA_SCALE = 2.85


def rounded_box(name, location, dimensions, radius, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name, obj.dimensions = name, dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    bevel = obj.modifiers.new("soft toy silhouette", "BEVEL")
    bevel.width, bevel.segments = radius, 8
    bevel.affect, bevel.harden_normals = "EDGES", True
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    normals = obj.modifiers.new("flat panels and soft edge normals", "WEIGHTED_NORMAL")
    normals.keep_sharp = True
    return obj


def rounded_panel(name, width, height, radius, front, center_z, material):
    """An exact rounded XZ rectangle, with a flat front and a thin real edge."""
    outline = []
    for x, z, start in [
        (width / 2 - radius, height / 2 - radius, 0),
        (-width / 2 + radius, height / 2 - radius, pi / 2),
        (-width / 2 + radius, -height / 2 + radius, pi),
        (width / 2 - radius, -height / 2 + radius, 3 * pi / 2),
    ]:
        for index in range(9):
            angle = start + pi / 2 * index / 8
            outline.append((x + radius * cos(angle), z + radius * sin(angle)))
    vertices = [
        (x, y, z + center_z) for y in [front, front + 0.018] for x, z in outline
    ]
    count = len(outline)
    faces = [tuple(range(count)), tuple(reversed(range(count, 2 * count)))]
    for index in range(count):
        following = (index + 1) % count
        faces.append((index + count, following + count, following, index))
    obj = mesh(name, vertices, faces, material)
    obj.data.polygons[0].use_smooth = False
    obj.data.polygons[1].use_smooth = False
    return obj


def build_monitor():
    warm = solid("monitor pearl porcelain enamel", (0.74, 0.71, 0.66), 0.20, 0.04)
    warm_shader = warm.node_tree.nodes.get("Principled BSDF")
    warm_shader.inputs["Coat Weight"].default_value = 0.28
    warm_shader.inputs["Coat Roughness"].default_value = 0.20
    dark = solid("monitor satin indigo metal", (0.10, 0.15, 0.23), 0.26, 0.32)
    seal = solid("monitor recessed graphite bezel", (0.035, 0.047, 0.075), 0.26, 0.20)
    stand = solid("monitor brushed silver pedestal", (0.37, 0.43, 0.50), 0.27, 0.65)
    screen = solid("monitor midnight glass display", (0.013, 0.022, 0.041), 0.5)
    shader = screen.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Coat Weight"].default_value = 0.06
    shader.inputs["Emission Color"].default_value = (0.013, 0.022, 0.041, 1)
    shader.inputs["Emission Strength"].default_value = 0.15
    led = solid("monitor quiet cyan power light", (0.1, 0.72, 0.77), 0.3)
    led_shader = led.node_tree.nodes.get("Principled BSDF")
    led_shader.inputs["Emission Color"].default_value = (0.1, 0.72, 0.77, 1)
    led_shader.inputs["Emission Strength"].default_value = 0.4

    rounded_box(
        "monitor rear housing", (0.05, 0.13, 1.485), (2.42, 0.42, 1.52), 0.13, dark
    )
    frame = rounded_box(
        "monitor rounded front bezel", (0, -0.02, 1.43), (2.42, 0.36, 1.54), 0.14, warm
    )
    cutter = rounded_box(
        "temporary display recess",
        (0, -0.24, SCREEN_CENTER_Z),
        (2.11, 0.42, 1.25),
        0.09,
        seal,
    )
    bpy.context.view_layer.objects.active = frame
    recess = frame.modifiers.new("actual recessed display", "BOOLEAN")
    recess.operation, recess.solver, recess.object = "DIFFERENCE", "EXACT", cutter
    bpy.ops.object.modifier_move_up(modifier=recess.name)
    bpy.ops.object.modifier_apply(modifier=recess.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    rounded_panel(
        "monitor display seal", 2.06, 1.21, 0.13, -0.09, SCREEN_CENTER_Z, seal
    )
    rounded_panel(
        "monitor empty display",
        SCREEN_WIDTH,
        SCREEN_HEIGHT,
        SCREEN_RADIUS,
        SCREEN_FRONT_Y,
        SCREEN_CENTER_Z,
        screen,
    )
    rounded_box(
        "monitor short pedestal", (0, 0.10, 0.4), (0.36, 0.34, 0.58), 0.10, stand
    )
    rounded_box("monitor rounded foot", (0, 0.09, 0.11), (1.20, 0.70, 0.20), 0.09, warm)
    sphere("monitor status light", (0.97, -0.208, 0.79), (0.018, 0.007, 0.018), led)


def screen_layout():
    """Top-left canvas fractions for the front-facing orthographic display."""
    return {
        "x": 0.5 - SCREEN_WIDTH / (2 * CAMERA_SCALE),
        "y": 0.5
        - (SCREEN_CENTER_Z + SCREEN_HEIGHT / 2 - CAMERA_TARGET_Z) / CAMERA_SCALE,
        "width": SCREEN_WIDTH / CAMERA_SCALE,
        "height": SCREEN_HEIGHT / CAMERA_SCALE,
        "radius": SCREEN_RADIUS / CAMERA_SCALE,
    }
