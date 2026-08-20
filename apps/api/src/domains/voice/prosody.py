"""PAD → voice_settings prosody modulation (Lot 4-D4, ADR-237).

Pure math, ElevenLabs-oriented: arousal drives expressiveness — style up,
stability down — inside hard [0, 1] bounds, with a neutral dead-band so a
flat mood never jitters the voice. The admin-configured settings stay the
BASE: the mood bends them, it never replaces them. Other TTS providers
ignore the resulting block gracefully (protocol kwargs), a documented
asymmetry: no equivalent parametric surface exists there.
"""

from __future__ import annotations

from typing import Any

from src.core.constants import (
    VOICE_PROSODY_AROUSAL_DEADBAND,
    VOICE_PROSODY_DEFAULT_STABILITY,
    VOICE_PROSODY_DEFAULT_STYLE,
    VOICE_PROSODY_STABILITY_GAIN,
    VOICE_PROSODY_STYLE_GAIN,
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def modulate_voice_settings(
    base: dict[str, Any],
    *,
    pleasure: float,
    arousal: float,
) -> dict[str, Any]:
    """Bend the base voice_settings by the current mood (new dict).

    Args:
        base: Admin-configured ElevenLabs settings (may be empty).
        pleasure: PAD pleasure in [-1, 1] (reserved for future warmth cues).
        arousal: PAD arousal in [-1, 1] — the expressiveness driver.

    Returns:
        A NEW settings dict; the base is returned as-is (same object)
        inside the neutral dead-band so a flat mood costs nothing.
    """
    del pleasure  # Reserved: warmth cues need per-voice calibration first.
    if abs(arousal) < VOICE_PROSODY_AROUSAL_DEADBAND:
        return base

    stability = float(base.get("stability", VOICE_PROSODY_DEFAULT_STABILITY))
    style = float(base.get("style", VOICE_PROSODY_DEFAULT_STYLE))
    return {
        **base,
        "stability": _clamp01(stability - arousal * VOICE_PROSODY_STABILITY_GAIN),
        "style": _clamp01(style + arousal * VOICE_PROSODY_STYLE_GAIN),
    }
