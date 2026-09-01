"""The animation's tone vocabulary — closed, small, and its own.

Three rules shaped this list, and each of them is a constraint the animation
imposes on the language rather than the other way round:

1. **Every register must earn a DIFFERENT face.** Two registers the avatar would
   play identically are one register with two names, and they only dilute the
   model's choice. Twelve is what the expression set can actually distinguish.
2. **A register describes how the SENTENCE was said**, never how LIA feels. The
   psyche owns the second and keeps it; conflating them is what made every turn
   land on the same expression (see the package docstring).
3. **The vocabulary is closed and validated here.** A model that invents a
   register gets a normalized fallback, never a silent pass-through: an unknown
   value reaching the frontend would be a face nobody designed.

`intensity` is the dial the animation OVERPLAYS. It is deliberately not a
probability or a confidence — it is stage direction, and the renderer is
expected to exaggerate it rather than reproduce it.
"""

from __future__ import annotations

from typing import Final

# =============================================================================
# Registers
# =============================================================================

#: What kind of speech act the answer was. Ordered from brightest to flattest
#: so a reader of the prompt sees the range at a glance; the order carries no
#: other meaning and nothing may depend on it.
TONE_REGISTERS: Final[tuple[str, ...]] = (
    "celebratory",  # something worked, and it is worth a small party
    "playful",  # teasing, light, a joke landed
    "warm",  # affectionate, reassuring, personal
    "curious",  # genuinely interested, leaning in
    "assured",  # confident, this is settled, no hedging
    "factual",  # plain delivery: here is the information
    "careful",  # nuanced, hedged, weighing something
    "questioning",  # the answer ends by asking something back
    "surprised",  # an unexpected finding is being reported
    "concerned",  # something is wrong and it matters
    "apologetic",  # a failure or a limit is being owned
    "weary",  # long, heavy, or repeatedly-attempted work
)

#: The register used when the model says nothing usable. NOT a neutral default
#: the model may lean on — it is the value that says "no annotation", and the
#: frontend treats it as the absence of a signal rather than as a flat delivery.
TONE_REGISTER_FALLBACK: Final[str] = "factual"

# =============================================================================
# Accents
# =============================================================================

#: A one-shot punctuation beat on top of the register. Rarity is the whole
#: point: an accent on every turn is a tic, and the prompt says so.
TONE_ACCENTS: Final[tuple[str, ...]] = (
    "none",
    "wink",  # complicity — a shared joke, a small liberty taken
    "nod",  # acknowledgement — understood, agreed, done
    "tilt",  # puzzlement — a question the answer itself raises
    "sparkle",  # delight — a genuinely good outcome
    "sigh",  # resignation — the work was long or the news is dull
)

TONE_ACCENT_NONE: Final[str] = "none"

# =============================================================================
# Normalization (the ONLY door into the vocabulary)
# =============================================================================

#: Intensity bounds. Zero is allowed and means "say it, but do not play it".
TONE_INTENSITY_MIN: Final[float] = 0.0
TONE_INTENSITY_MAX: Final[float] = 1.0


def normalize_register(raw: str | None) -> str | None:
    """Return the canonical register, or None when the value is not one.

    None is returned rather than the fallback so a caller can tell "the model
    invented a register" from "the model chose the plainest one" — the first is
    a prompt problem worth counting, the second is an ordinary answer.
    """
    if not raw:
        return None
    candidate = raw.strip().lower()
    return candidate if candidate in TONE_REGISTERS else None


def normalize_accent(raw: str | None) -> str:
    """Return the canonical accent, defaulting to ``none``.

    An unknown accent degrades to no accent instead of failing the whole
    annotation: the register is the signal that matters, and losing a wink is
    not worth losing the tone with it.
    """
    if not raw:
        return TONE_ACCENT_NONE
    candidate = raw.strip().lower()
    return candidate if candidate in TONE_ACCENTS else TONE_ACCENT_NONE


def normalize_intensity(raw: str | float | None) -> float | None:
    """Clamp an intensity into [0, 1]; None when it is not a number at all.

    A value out of bounds is REPAIRED rather than rejected — it is mechanically
    repairable, and the codebase's doctrine is to clamp those and keep only the
    unrepairable as errors. A non-numeric one is not repairable without
    inventing intent.
    """
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except TypeError, ValueError:
        return None
    if value != value:  # NaN: float("nan") != itself
        return None
    return max(TONE_INTENSITY_MIN, min(TONE_INTENSITY_MAX, value))
