"""Per-turn expressivity annotation — the animation's OWN tone signal (ADR-253).

The chat avatar needs to know, at the instant an answer lands, in what register
that answer was written. Nothing else in the system carries that:

- The **psyche** models an inner life. It is a TRAIT: it moves slowly and on
  purpose. Measured on 14 consecutive production turns, its dominant emotion was
  ``enthusiasm`` on 13 of them, drifting by 0.02 — an argmax over a near-constant
  vector is a constant, so every answer earned the same face. It was never meant
  to answer for an animation, and it is not asked to any more.
- A **punctuation heuristic** reads the surface of the text. On the same 14
  answers, 9 carried no exclamation, no emoji and no code fence at all: it had
  nothing to say about them.

So the model that wrote the answer declares the register itself, in band, the
same proven way it already declares its psyche self-report: a compact tag after
the response, stripped from the stream before a single token reaches the screen.
It costs no extra LLM call and it arrives exactly when the answer arrives.

The vocabulary here belongs to the ANIMATION and to nothing else. It is not the
psyche's emotion list, and the two must never be folded together: one says how
LIA feels over time, the other how THIS sentence was said.
"""

from src.domains.agents.expressivity.annotation import (
    ToneAnnotation,
    parse_tone_annotation,
    pop_tone_annotation,
    store_tone_annotation,
)
from src.domains.agents.expressivity.vocabulary import (
    TONE_ACCENTS,
    TONE_REGISTERS,
    normalize_accent,
    normalize_intensity,
    normalize_register,
)

__all__ = [
    "TONE_ACCENTS",
    "TONE_REGISTERS",
    "ToneAnnotation",
    "normalize_accent",
    "normalize_intensity",
    "normalize_register",
    "parse_tone_annotation",
    "pop_tone_annotation",
    "store_tone_annotation",
]
