"""Original sculpt, facial organs and pose application for the LIA thought spirit."""

from math import cos, pi, sin

import bpy

from .geometry import body, mesh, petal, sphere, stroke
from .materials import palette
from .ribbon import hair_ribbon


def empty(name):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    return obj


def eyebrow(side, male, ink):
    sign = -1 if side == "left" else 1
    points = [
        (sign * 0.53, -0.56, 1.48),
        (sign * 0.33, -0.65, 1.57),
        (sign * 0.12, -0.59, 1.48),
    ]
    return stroke(side + " expressive brow", points, 0.032 if male else 0.02, ink)


def lid_surface(side, upper, height, material):
    columns, rows = 24, 7
    vertices = [(0, 0, 0)] * ((columns + 1) * (rows + 1))
    faces = []
    for row in range(rows):
        for column in range(columns):
            a = row * (columns + 1) + column
            face = (a, a + 1, a + columns + 2, a + columns + 1)
            faces.append(face if upper else tuple(reversed(face)))
    obj = mesh(
        side + (" curved upper lid" if upper else " curved lower lid"),
        vertices,
        faces,
        material,
    )
    return {
        "object": obj,
        "upper": upper,
        "height": height,
        "columns": columns,
        "rows": rows,
    }


def move_lid(lid, opening):
    """Skin slides over a whole 3D eyeball; neither iris nor glint is squashed."""
    height, columns, rows = lid["height"], lid["columns"], lid["rows"]
    sign = 1 if lid["upper"] else -1
    for row in range(rows + 1):
        blend = row / rows
        for column in range(columns + 1):
            u = 2 * column / columns - 1
            arch = max(0, 1 - u * u) ** 0.5
            edge = height * arch * opening
            clearance = 0.09 if lid["upper"] else 0.03
            z = sign * (edge + ((height + clearance) * arch - edge) * blend)
            y = -0.192 * arch * (1 - blend) - 0.012
            lid["object"].data.vertices[row * (columns + 1) + column].co = (
                0.264 * u,
                y,
                z,
            )


def eye(side, male, materials):
    sign = -1 if side == "left" else 1
    root = empty(side + " eye socket")
    root.location = (sign * 0.32, -0.50, 1.16)
    height = 0.21 if male else 0.27
    white = sphere(
        side + " porcelain eyeball",
        (0, 0, 0),
        (0.255, 0.11, height),
        materials["white"],
    )
    white.parent = root
    iris = empty(side + " pupil aim")
    iris.parent, iris.location = root, (0, -0.107, 0.025)
    for name, location, scale, material in [
        ("iris", (0, -0.015, 0), (0.178, 0.03, height * 0.89), "iris"),
        ("pupil", (0, -0.043, 0), (0.12, 0.014, height * 0.67), "pupil"),
        ("key glint", (-0.051, -0.058, 0.066), (0.024, 0.008, 0.03), "white"),
        ("soft glint", (0.058, -0.048, -0.045), (0.009, 0.006, 0.011), "white"),
    ]:
        obj = sphere(side + " " + name, location, scale, materials[material])
        obj.parent = iris
    lid = stroke(
        side + " upper eyelid",
        [(-0.245, -0.08, 0.055), (0, -0.215, height), (0.245, -0.08, 0.055)],
        0.009 if male else 0.012,
        materials["ink"],
    )
    lid.parent = root
    lids = [
        lid_surface(side, upper, height, materials.get("lid", materials["body"]))
        for upper in [True, False]
    ]
    for item in lids:
        item["object"].parent = root
    lashes = []
    if not male:
        for index in range(2):
            obj = stroke(
                side + " sculpted lash " + str(index),
                [
                    (sign * 0.215, -0.049, height * 0.45),
                    (
                        sign * (0.255 + index * 0.028),
                        -0.056,
                        height * (0.65 + index * 0.11),
                    ),
                ],
                0.007,
                materials["ink"],
            )
            obj.parent = root
            lashes.append(obj)
    return {
        "root": root,
        "white": white,
        "height": height,
        "iris": iris,
        "lid": lid,
        "lids": lids,
        "lashes": lashes,
    }


def crest(male, material):
    if male:
        return [
            petal(
                "single swept masculine quiff",
                [
                    (0, 0, 1.66),
                    (0.04, 0, 1.86),
                    (0.19, -0.01, 2.0),
                    (0.36, -0.02, 2.0),
                    (0.48, -0.02, 1.94),
                    (0.54, 0, 1.95),
                ],
                [0.25, 0.27, 0.23, 0.18, 0.08, 0.006],
                [0.22, 0.21, 0.18, 0.14, 0.07, 0.006],
                material,
            )
        ]
    return [
        petal(
            "tall folded feminine petal",
            [
                (-0.15, 0.0, 1.64),
                (-0.18, 0, 1.9),
                (-0.19, 0, 2.13),
                (-0.12, -0.01, 2.31),
                (-0.03, -0.02, 2.34),
            ],
            [0.12, 0.17, 0.17, 0.13, 0.007],
            [0.14, 0.14, 0.12, 0.07, 0.005],
            material,
        ),
        petal(
            "curled feminine second petal",
            [
                (0.02, 0, 1.67),
                (0.11, -0.01, 1.91),
                (0.23, -0.01, 2.10),
                (0.38, -0.02, 2.11),
                (0.48, -0.02, 2.04),
            ],
            [0.16, 0.2, 0.2, 0.12, 0.006],
            [0.14, 0.15, 0.12, 0.07, 0.005],
            material,
        ),
    ]


def build(variant, *, body_only=False):
    male = variant == "male"
    materials = palette()
    root = empty("LIA spirit original character")
    parts = [body(variant, materials["body"]), *crest(male, materials["body"])]
    if not male:
        parts.extend(hair_ribbon())
    hands = []
    for sign in [-1, 1]:
        hand = sphere(
            "soft side nub",
            (sign * (0.92 if male else 0.77), -0.045, 0.82),
            (0.15, 0.19, 0.23),
            materials["body"],
        )
        parts.append(hand)
        hands.append(hand)
    if body_only:
        # A clean sculpt for the companion's live native facial rig. Skip
        # sockets as well as organs: hiding eyes after carving leaves holes.
        for part in parts:
            part.parent = root
        return {"root": root, "hands": hands, "male": male}
    eyes = [eye("left", male, materials), eye("right", male, materials)]
    # Actual carved sockets embed the eyeballs into the sculpt instead of
    # putting flat stickers in front of the face.
    for item in eyes:
        cutter = sphere(
            "temporary socket tool",
            item["root"].location,
            (0.263, 0.16, item["height"] + 0.02),
            materials["body"],
        )
        bpy.context.view_layer.objects.active = parts[0]
        modifier = parts[0].modifiers.new("carved eye socket", "BOOLEAN")
        modifier.operation, modifier.solver, modifier.object = (
            "DIFFERENCE",
            "EXACT",
            cutter,
        )
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.data.objects.remove(cutter, do_unlink=True)
    brows = [
        eyebrow("left", male, materials["ink"]),
        eyebrow("right", male, materials["ink"]),
    ]
    parts.extend([*brows, *(item["root"] for item in eyes)])
    mouth = mesh(
        "expressive mouth cavity",
        [(0, -0.664, 0.83)] * 65,
        [(0, i, i % 64 + 1) for i in range(1, 65)],
        materials["ink"],
    )
    teeth = sphere(
        "small enamel upper teeth",
        (0, -0.681, 0.87),
        (0.095, 0.014, 0.018),
        materials["white"],
    )
    tongue = sphere(
        "warm smile interior",
        (0, -0.68, 0.8),
        (0.08, 0.011, 0.019),
        materials["tongue"],
    )
    parts.extend([mouth, teeth, tongue])
    for part in parts:
        part.parent = root
    return {
        "root": root,
        "eyes": eyes,
        "brows": brows,
        "hands": hands,
        "mouth": mouth,
        "teeth": teeth,
        "tongue": tongue,
        "male": male,
    }


def apply_pose(character, pose):
    root = character["root"]
    root.scale = (1, 1, pose.mass)
    root.location.z = pose.bob
    root.rotation_euler = (0, pose.roll, pose.yaw)
    for item, opening in zip(character["eyes"], [pose.eye_left, pose.eye_right], strict=True):
        item["iris"].location.x = pose.gaze_x
        item["iris"].location.z = 0.025 + pose.gaze_z
        item["lid"].scale.z = opening
        for lid in item["lids"]:
            move_lid(lid, opening)
        for lash in item["lashes"]:
            lash.scale.z = opening
    for index, (brow, lift) in enumerate(
        zip(character["brows"], [pose.brow_left, pose.brow_right], strict=True)
    ):
        brow.location.z = lift
        sign = -1 if index == 0 else 1
        for point_index, point in enumerate(brow.data.splines[0].bezier_points):
            baseline = 1.57 if point_index == 1 else 1.48
            if character["male"] and point_index == 1:
                baseline = 1.52
            point.co.z = baseline + pose.brow_slant * (point_index - 1)
            point.co.x = sign * [0.53, 0.33, 0.12][point_index]
    mouth = character["mouth"]
    mouth.data.vertices[0].co = (0, -0.671, 0.83)
    for index in range(64):
        angle = 2 * pi * index / 64
        x = pose.mouth_width * cos(angle)
        z = 0.83 + pose.smile * cos(angle) ** 2 + max(0.006, pose.mouth_open) * sin(angle)
        mouth.data.vertices[index + 1].co = (x, -0.671 + 0.06 * abs(cos(angle)), z)
    character["teeth"].hide_render = pose.mouth_open < 0.06
    character["tongue"].hide_render = pose.mouth_open < 0.065
    character["teeth"].location.z = 0.83 + pose.mouth_open * 0.66
    character["tongue"].location.z = 0.83 - pose.mouth_open * 0.6
    hand = character["hands"][0]
    hand.location = (-0.92 if character["male"] else -0.77, -0.045, 0.82)
    hand.location.x += pose.hand_lift * 1.8
    hand.location.y -= pose.hand_lift * 2.0
    hand.location.z += pose.hand_lift * 0.35
