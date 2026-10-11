"""Smooth original meshes and swept forms, built entirely from geometry."""

from math import cos, exp, pi, sin

import bpy
from mathutils import Vector


def mesh(name, vertices, faces, material):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    for polygon in data.polygons:
        polygon.use_smooth = True
    return obj


def sphere(name, location, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32, location=location)
    obj = bpy.context.object
    obj.name, obj.scale = name, scale
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def stroke(name, points, radius, material):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions, data.resolution_u = "3D", 20
    data.bevel_depth, data.bevel_resolution = radius, 4
    spline = data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for item, position in zip(spline.bezier_points, points, strict=True):
        item.co = position
        item.handle_left_type = item.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def body(variant, material):
    male = variant == "male"
    vertices, faces = [], []
    rings, sectors = 48, 64
    for i in range(rings + 1):
        theta = pi * i / rings
        z = 0.92 + 0.88 * cos(theta)
        width = (0.83 + 0.13 * (1 - cos(theta))) if male else (0.57 + 0.18 * (1 - cos(theta)))
        radius = sin(theta) ** (0.68 if male else 0.9)
        for j in range(sectors):
            angle = 2 * pi * j / sectors
            x = width * radius * cos(angle)
            y = 0.63 * radius * sin(angle)
            if y < 0:
                # Sculpted cheek volume: integrated surface, not attached balls.
                cheeks = exp(-(((abs(x) - 0.43) / 0.22) ** 2) - ((z - 0.84) / 0.23) ** 2)
                y -= 0.055 * cheeks
            vertices.append((x, y, z))
    for i in range(rings):
        for j in range(sectors):
            a, b = i * sectors + j, i * sectors + (j + 1) % sectors
            # Latitude advances north -> south; this winding faces OUTSIDE.
            faces.append((a + sectors, b + sectors, b, a))
    return mesh(
        "original masculine rounded pebble" if male else "original feminine pear",
        vertices,
        faces,
        material,
    )


def petal(name, centers, widths, depths, material):
    """A closed swept petal with a tapered end, never a texture masquerading as volume."""
    vertices, faces = [], []
    sectors = 32
    for center, width, depth in zip(centers, widths, depths, strict=True):
        for j in range(sectors):
            angle = 2 * pi * j / sectors
            vertices.append(
                (
                    center[0] + width * cos(angle),
                    center[1] + depth * sin(angle),
                    center[2],
                )
            )
    for i in range(len(centers) - 1):
        for j in range(sectors):
            a, b = i * sectors + j, i * sectors + (j + 1) % sectors
            faces.append((a, b, b + sectors, a + sectors))
    faces.extend(
        (
            tuple(reversed(range(sectors))),
            tuple(range(len(vertices) - sectors, len(vertices))),
        )
    )
    obj = mesh(name, vertices, faces, material)
    modifier = obj.modifiers.new("silky smooth petal", "SUBSURF")
    modifier.levels = modifier.render_levels = 2
    return obj


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
