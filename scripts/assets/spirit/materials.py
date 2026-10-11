"""Original nacre, enamel and iris materials for the offline Blender source."""

import bpy


def solid(name, color, roughness=0.32, metallic=0.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Coat Weight"].default_value = 0.3
    shader.inputs["Coat Roughness"].default_value = 0.14
    return material


def nacre():
    material = solid("LIA original satin opal", (0.86, 0.89, 0.98), 0.21, 0.02)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["IOR"].default_value = 1.55
    shader.inputs["Specular IOR Level"].default_value = 0.8
    shader.inputs["Subsurface Weight"].default_value = 0.085
    shader.inputs["Subsurface Radius"].default_value = (0.24, 0.14, 0.08)
    shader.inputs["Coat Weight"].default_value = 0.85
    shader.inputs["Coat Roughness"].default_value = 0.055
    shader.inputs["Coat IOR"].default_value = 1.46
    shader.inputs["Thin Film Thickness"].default_value = 520
    shader.inputs["Thin Film IOR"].default_value = 1.4
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.5
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.65
    ramp = nodes.new("ShaderNodeValToRGB")
    stops = [
        (0.15, (0.38, 0.64, 0.96, 1)),
        (0.36, (0.66, 0.49, 0.84, 1)),
        (0.53, (0.92, 0.86, 0.76, 1)),
        (0.7, (0.50, 0.78, 0.94, 1)),
        (0.9, (0.95, 0.82, 0.72, 1)),
    ]
    for element, (position, color) in zip(ramp.color_ramp.elements, stops[:2], strict=True):
        element.position, element.color = position, color
    for position, color in stops[2:]:
        ramp.color_ramp.elements.new(position).color = color
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    # A pearl changes colour across a curve, rather than reading as uniformly
    # dyed plastic. Blend its broad opal inclusions with a soft grazing tint.
    facing = nodes.new("ShaderNodeLayerWeight")
    facing.inputs["Blend"].default_value = 0.32
    rim = nodes.new("ShaderNodeValToRGB")
    rim.color_ramp.elements[0].position = 0.05
    rim.color_ramp.elements[0].color = (0.38, 0.63, 1, 1)
    rim.color_ramp.elements[1].position = 0.85
    rim.color_ramp.elements[1].color = (0.94, 0.89, 0.79, 1)
    rim.color_ramp.elements.new(0.35).color = (0.77, 0.52, 0.83, 1)
    rim.color_ramp.elements.new(0.57).color = (0.72, 0.86, 0.94, 1)
    links.new(facing.outputs["Facing"], rim.inputs["Fac"])
    porcelain = nodes.new("ShaderNodeMixRGB")
    porcelain.inputs["Fac"].default_value = 0.45
    porcelain.inputs[1].default_value = (0.92, 0.91, 0.86, 1)
    links.new(ramp.outputs["Color"], porcelain.inputs[2])
    opal = nodes.new("ShaderNodeMixRGB")
    opal.inputs["Fac"].default_value = 0.18
    links.new(porcelain.outputs["Color"], opal.inputs[1])
    links.new(rim.outputs["Color"], opal.inputs[2])
    # Sparse embedded warm inclusions make the finish opal rather than painted
    # enamel. They live in the 3D shader and follow every turn of the mesh.
    inclusions = nodes.new("ShaderNodeTexVoronoi")
    inclusions.inputs["Scale"].default_value = 38
    sparkle = nodes.new("ShaderNodeValToRGB")
    sparkle.color_ramp.elements[0].position = 0.08
    sparkle.color_ramp.elements[0].color = (1, 1, 1, 1)
    sparkle.color_ramp.elements[1].position = 0.17
    sparkle.color_ramp.elements[1].color = (0, 0, 0, 1)
    links.new(inclusions.outputs["Distance"], sparkle.inputs["Fac"])
    flecks = nodes.new("ShaderNodeMixRGB")
    links.new(sparkle.outputs["Color"], flecks.inputs["Fac"])
    links.new(opal.outputs["Color"], flecks.inputs[1])
    flecks.inputs[2].default_value = (1, 0.74, 0.38, 1)
    links.new(flecks.outputs["Color"], shader.inputs["Base Color"])
    glimmer = nodes.new("ShaderNodeMath")
    glimmer.operation = "MULTIPLY"
    glimmer.inputs[1].default_value = 0.22
    links.new(sparkle.outputs["Color"], glimmer.inputs[0])
    shader.inputs["Emission Color"].default_value = (1, 0.61, 0.25, 1)
    links.new(glimmer.outputs["Value"], shader.inputs["Emission Strength"])
    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 145
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.012
    bump.inputs["Distance"].default_value = 0.004
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return material


def iris_material():
    """A deep limbal rim and radial fibres give the tiny eyes a glass iris."""
    material = solid("indigo glass iris", (0.008, 0.02, 0.07), 0.11, 0.03)
    nodes, links = material.node_tree.nodes, material.node_tree.links
    shader = nodes.get("Principled BSDF")
    coordinates = nodes.new("ShaderNodeTexCoord")
    plane = nodes.new("ShaderNodeVectorMath")
    plane.operation = "MULTIPLY"
    plane.inputs[1].default_value = (1, 0, 1)
    links.new(coordinates.outputs["Generated"], plane.inputs[0])
    centered = nodes.new("ShaderNodeVectorMath")
    centered.operation = "SUBTRACT"
    centered.inputs[1].default_value = (0.5, 0, 0.5)
    links.new(plane.outputs["Vector"], centered.inputs[0])
    radius = nodes.new("ShaderNodeVectorMath")
    radius.operation = "LENGTH"
    links.new(centered.outputs["Vector"], radius.inputs[0])
    ring = nodes.new("ShaderNodeValToRGB")
    ring.color_ramp.elements[0].position = 0.08
    ring.color_ramp.elements[0].color = (0.005, 0.009, 0.025, 1)
    ring.color_ramp.elements[1].position = 0.5
    ring.color_ramp.elements[1].color = (0.002, 0.004, 0.013, 1)
    ring.color_ramp.elements.new(0.28).color = (0.022, 0.063, 0.21, 1)
    ring.color_ramp.elements.new(0.41).color = (0.047, 0.12, 0.38, 1)
    links.new(radius.outputs["Value"], ring.inputs["Fac"])
    axes = nodes.new("ShaderNodeSeparateXYZ")
    links.new(centered.outputs["Vector"], axes.inputs["Vector"])
    angle = nodes.new("ShaderNodeMath")
    angle.operation = "ARCTAN2"
    links.new(axes.outputs["Z"], angle.inputs[0])
    links.new(axes.outputs["X"], angle.inputs[1])
    rays = nodes.new("ShaderNodeMath")
    rays.operation = "MULTIPLY"
    rays.inputs[1].default_value = 96
    links.new(angle.outputs["Value"], rays.inputs[0])
    fibre = nodes.new("ShaderNodeMath")
    fibre.operation = "SINE"
    links.new(rays.outputs["Value"], fibre.inputs[0])
    pigment = nodes.new("ShaderNodeMixRGB")
    pigment.blend_type = "MULTIPLY"
    pigment.inputs[2].default_value = (0.5, 0.6, 0.8, 1)
    links.new(fibre.outputs["Value"], pigment.inputs["Fac"])
    links.new(ring.outputs["Color"], pigment.inputs[1])
    links.new(pigment.outputs["Color"], shader.inputs["Base Color"])
    return material


def palette():
    materials = {
        "body": nacre(),
        "white": solid("warm porcelain sclera", (0.93, 0.91, 0.88), 0.16),
        "iris": iris_material(),
        "pupil": solid("deep glass pupil", (0.0008, 0.001, 0.003), 0.07),
        "ink": solid("eyebrow and soft mouth", (0.025, 0.034, 0.075), 0.42),
        "tongue": solid("mouth interior warmth", (0.34, 0.08, 0.11), 0.37),
    }
    for organ in ["iris", "pupil"]:
        shader = materials[organ].node_tree.nodes.get("Principled BSDF")
        shader.inputs["Coat Weight"].default_value = 1
        shader.inputs["Coat Roughness"].default_value = 0.035
        shader.inputs["Specular IOR Level"].default_value = 0.75
    materials["ink"].node_tree.nodes.get("Principled BSDF").inputs["Coat Weight"].default_value = 0
    materials["lid"] = materials["body"].copy()
    materials["lid"].name = "soft nacre eyelids"
    lid = materials["lid"].node_tree.nodes.get("Principled BSDF")
    lid.inputs["Coat Weight"].default_value = 0.12
    lid.inputs["Roughness"].default_value = 0.32
    return materials
