"""Original jade and apricot ceramic finishes for the new companion sculpts."""

from .materials import palette, solid


def porcelain(name, color, pale, *, leaf=False):
    material = solid(name, color, 0.34 if leaf else 0.29, 0.01)
    nodes, links = material.node_tree.nodes, material.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Coat Weight"].default_value = 0.23 if leaf else 0.34
    shader.inputs["Coat Roughness"].default_value = 0.18
    shader.inputs["Subsurface Weight"].default_value = 0.035
    shader.inputs["Subsurface Radius"].default_value = (0.18, 0.12, 0.08)
    shader.inputs["Thin Film Thickness"].default_value = 0
    shader.inputs["Thin Film IOR"].default_value = 1.38
    coordinates = nodes.new("ShaderNodeTexCoord")
    height = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coordinates.outputs["Generated"], height.inputs["Vector"])
    tint = nodes.new("ShaderNodeValToRGB")
    tint.color_ramp.elements[0].position = 0.12
    tint.color_ramp.elements[0].color = (*pale, 1)
    tint.color_ramp.elements[1].position = 0.7
    tint.color_ramp.elements[1].color = (*color, 1)
    links.new(height.outputs["Z"], tint.inputs["Fac"])
    links.new(tint.outputs["Color"], shader.inputs["Base Color"])
    return material


def character_palette(character, male):
    materials = palette()
    if character == "moss":
        body = (0.055, 0.29, 0.12) if male else (0.085, 0.38, 0.19)
        pale = (0.23, 0.52, 0.30)
        accent = (0.035, 0.24, 0.075)
        tip = (0.14, 0.40, 0.09)
    else:
        body = (0.62, 0.16, 0.04) if male else (0.70, 0.20, 0.075)
        pale = (0.84, 0.46, 0.18)
        accent = (0.84, 0.39, 0.10)
        tip = (0.98, 0.61, 0.20)
    materials["body"] = porcelain(character + " original pearl ceramic", body, pale)
    materials["leaf"] = porcelain(character + " folded crest glaze", accent, tip, leaf=True)
    materials["ivory"] = solid(character + " quiet ivory inset", (0.91, 0.85, 0.68), 0.3)
    materials["honey"] = porcelain(
        character + " honey flame", (0.93, 0.52, 0.10), (0.99, 0.74, 0.29), leaf=True
    )
    materials["vein"] = solid(character + " subtle crease", tip, 0.38)
    materials["lid"] = materials["body"].copy()
    materials["lid"].name = character + " soft sculpted lids"
    materials["lid"].node_tree.nodes.get("Principled BSDF").inputs[
        "Coat Weight"
    ].default_value = 0.12
    return materials
