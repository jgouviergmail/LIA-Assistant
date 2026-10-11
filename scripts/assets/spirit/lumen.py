"""Lumo: an original apricot lantern spirit with tucked moon folds and flame."""

from .companion_materials import character_palette
from .companion_ribbon import companion_ribbon
from .companion_sculpt import bean, finish, limbs
from .geometry import petal, sphere


def build_lumen(variant, *, portrait=False):
    male = variant == "male"
    materials = character_palette("lumen", male)
    parts = [
        bean("Lumo compact original lantern", male, materials["body"], lantern=True),
        *limbs(male, materials["body"]),
    ]
    lift = -0.17 if male else 0
    for sign in [-1, 1]:
        parts.append(
            petal(
                "Lumo tucked moon fold",
                [
                    (sign * 0.36, 0.10, 1.54),
                    (sign * 0.42, 0.065, 1.76),
                    (sign * 0.38, 0.04, 1.94 + lift),
                    (sign * 0.22, 0.015, 2.01 + lift),
                    (sign * 0.12, 0.015, 1.94 + lift),
                ],
                [0.055, 0.20 if male else 0.16, 0.18 if male else 0.15, 0.085, 0.006],
                [0.09, 0.10, 0.065, 0.035, 0.004],
                materials["leaf"],
            )
        )
    parts.append(
        petal(
            "Lumo bent honey flame",
            [
                (-0.04, -0.015, 1.65),
                (-0.08, -0.03, 1.91),
                (-0.01, -0.045, 2.12 + lift),
                (0.11, -0.05, 2.25 + lift),
                (0.20, -0.05, 2.20 + lift),
            ],
            [0.085, 0.15 if male else 0.12, 0.10, 0.055, 0.006],
            [0.08, 0.06, 0.035, 0.02, 0.004],
            materials["honey"],
        )
    )
    parts.append(
        sphere(
            "Lumo quiet ivory seed inset",
            (0, -0.55 if male else -0.49, 0.40),
            (0.065, 0.045, 0.085),
            materials["ivory"],
        )
    )
    if not male:
        parts.append(companion_ribbon((0.31, -0.135, 1.94), scale=0.74))
    return finish(parts, materials, male, portrait=portrait)
