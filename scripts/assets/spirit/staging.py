"""Offline transparent PNG studio with sample budgets for Cycles and EEVEE."""

import bpy

from .geometry import aim


def light(name, location, power, color, size):
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.color, data.shape, data.size = power, color, "DISK", size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    aim(obj, (0, 0, 1))


def studio(size, samples):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples, scene.cycles.use_denoising = samples, True
    scene.eevee.taa_render_samples = samples
    scene.cycles.max_bounces = 6
    scene.cycles.transparent_max_bounces = 4
    scene.render.threads_mode, scene.render.threads = "FIXED", 2
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.use_file_extension = True
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.65,
        0.70,
        0.80,
        1,
    )
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12
    light("warm porcelain studio key", (-1.8, -4, 3.4), 480, (1, 0.94, 0.87), 1.9)
    light("cool softbox fill", (3, -3, 3), 150, (0.73, 0.86, 1), 3.5)
    light("blue opal rim", (-2.5, 0, 2.8), 850, (0.35, 0.72, 1), 1.7)
    light("soft rosy rim", (2.7, 0.5, 3.6), 600, (1, 0.42, 0.7), 1.8)
    light("eye catchlight softbox", (-0.8, -4, 3.8), 80, (1, 0.98, 0.95), 0.9)
    bpy.ops.object.camera_add(location=(0, -7.0, 2.35))
    camera = bpy.context.object
    camera.data.type, camera.data.ortho_scale = "ORTHO", 2.72
    aim(camera, (0, 0, 1.14))
    scene.camera = camera
    return scene
