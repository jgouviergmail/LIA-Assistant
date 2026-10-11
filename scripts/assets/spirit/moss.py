"""Mousse: an original jade seed spirit with a broad asymmetric folded leaf."""

from .companion_materials import character_palette
from .companion_ribbon import companion_ribbon
from .companion_sculpt import bean, finish, limbs
from .geometry import petal, stroke


def build_moss(variant, *, portrait=False):
    male = variant == "male"
    materials = character_palette("moss", male)
    parts = [
        bean("Mousse original soft bean", male, materials["body"]),
        *limbs(male, materials["body"]),
    ]
    lift = -0.20 if male else 0
    parts.append(
        petal(
            "Mousse broad spoon leaf",
            [
                (-0.20, 0.03, 1.68),
                (-0.28, 0.015, 1.85 + lift),
                (-0.30, 0, 2.04 + lift),
                (-0.19, -0.025, 2.20 + lift),
                (-0.01, -0.04, 2.27 + lift),
                (0.12, -0.05, 2.21 + lift),
            ],
            [0.04, 0.27, 0.43 if male else 0.35, 0.32 if male else 0.24, 0.18, 0.006],
            [0.08, 0.095, 0.075, 0.048, 0.024, 0.004],
            materials["leaf"],
        )
    )
    parts.append(
        petal(
            "Mousse little counter leaf",
            [
                (0.20, 0.10, 1.68),
                (0.34, 0.07, 1.85),
                (0.46, 0.045, 1.96),
                (0.58, 0.02, 1.91),
            ],
            [0.055, 0.13, 0.10, 0.006],
            [0.075, 0.055, 0.026, 0.004],
            materials["leaf"],
        )
    )
    parts.append(
        stroke(
            "Mousse quiet raised vein",
            [
                (-0.28, -0.085, 1.86 + lift),
                (-0.30, -0.08, 2.035 + lift),
                (-0.19, -0.065, 2.16 + lift),
                (0.015, -0.055, 2.22 + lift),
            ],
            0.006,
            materials["vein"],
        )
    )
    if not male:
        parts.append(companion_ribbon((-0.17, -0.135, 2.04)))
    return finish(parts, materials, male, portrait=portrait)
