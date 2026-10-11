"""Bounded, deterministic choreography for the offline spirit portrait loops."""

from dataclasses import dataclass, replace
from math import cos, exp, pi, sin

LOOP_SECONDS = 3.2
BLINK_PHASES = (0.29, 0.79)
EXPRESSIONS = (
    "neutral",
    "joy",
    "excited",
    "tender",
    "surprise",
    "fear",
    "anger",
    "sad",
    "worried",
    "question",
    "thinking",
    "searching",
    "focused",
    "attentive",
    "speaking",
    "bored",
    "tired",
    "sleepy",
    "sleep",
    "wink",
)


@dataclass(frozen=True)
class FacePose:
    mass: float = 1.0
    bob: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    gaze_x: float = 0.0
    gaze_z: float = 0.0
    eye_left: float = 1.0
    eye_right: float = 1.0
    brow_left: float = 0.0
    brow_right: float = 0.0
    brow_slant: float = 0.0
    smile: float = 0.07
    mouth_open: float = 0.012
    mouth_width: float = 0.18
    hand_lift: float = 0.0


POSES = {
    "neutral": FacePose(),
    "joy": FacePose(eye_left=0.85, eye_right=0.85, smile=0.13, mouth_open=0.07),
    "excited": FacePose(brow_left=0.06, brow_right=0.06, smile=0.15, mouth_open=0.12),
    "tender": FacePose(eye_left=0.88, eye_right=0.88, roll=0.09, smile=0.11),
    "surprise": FacePose(brow_left=0.1, brow_right=0.1, mouth_width=0.08, mouth_open=0.14),
    "fear": FacePose(brow_slant=-0.12, mouth_width=0.11, mouth_open=0.08, smile=-0.01),
    "anger": FacePose(eye_left=0.8, eye_right=0.8, brow_slant=0.19, smile=-0.07),
    "sad": FacePose(eye_left=0.7, eye_right=0.7, brow_slant=-0.13, smile=-0.05),
    "worried": FacePose(brow_left=0.035, brow_slant=-0.13, smile=-0.025),
    "question": FacePose(brow_left=0.1, roll=-0.07, mouth_open=0.035, hand_lift=0.1),
    "thinking": FacePose(gaze_x=-0.05, gaze_z=0.055, brow_right=0.07, hand_lift=0.23),
    "searching": FacePose(brow_left=0.04, brow_right=0.04, smile=0.03),
    "focused": FacePose(eye_left=0.72, eye_right=0.72, brow_slant=0.09, smile=0.01),
    "attentive": FacePose(brow_left=0.035, brow_right=0.035, smile=0.06),
    "speaking": FacePose(smile=0.09, mouth_open=0.025),
    "bored": FacePose(eye_left=0.55, eye_right=0.55, smile=-0.015),
    "tired": FacePose(eye_left=0.45, eye_right=0.45, roll=0.025, smile=0.015),
    "sleepy": FacePose(eye_left=0.28, eye_right=0.28, roll=0.07),
    "sleep": FacePose(eye_left=0.02, eye_right=0.02, smile=0.04, mouth_open=0.005),
    "wink": FacePose(eye_left=0.02, eye_right=0.95, roll=-0.07, smile=0.14),
}


def pose_at(expression: str, seconds: float) -> FacePose:
    """A periodic pose: identical endpoint values, with irregularly spaced blinks."""
    base = POSES[expression]
    phase = (seconds % LOOP_SECONDS) / LOOP_SECONDS
    wave = sin(2 * pi * phase)
    blink = max(
        exp(-(((phase - BLINK_PHASES[0]) / 0.022) ** 2)),
        exp(-(((phase - BLINK_PHASES[1]) / 0.019) ** 2)),
    )
    quiet = 0.35 if expression in {"focused", "sleep", "thinking"} else 1.0
    gaze = 0.06 if expression == "searching" else 0.018
    speech = 0.04 * (1 + sin(10 * pi * phase)) if expression == "speaking" else 0.0
    return replace(
        base,
        mass=1 + 0.012 * quiet * wave,
        bob=0.017 * quiet * wave,
        roll=base.roll + 0.018 * quiet * wave,
        yaw=0.035 * quiet * sin(2 * pi * phase + 0.3),
        gaze_x=base.gaze_x + gaze * wave,
        gaze_z=base.gaze_z + 0.009 * quiet * (cos(2 * pi * phase) - 1),
        eye_left=max(0.02, base.eye_left * (1 - blink)),
        eye_right=max(0.02, base.eye_right * (1 - blink)),
        brow_left=base.brow_left + 0.008 * quiet * wave,
        brow_right=base.brow_right + 0.008 * quiet * wave,
        mouth_open=base.mouth_open + speech,
    )
