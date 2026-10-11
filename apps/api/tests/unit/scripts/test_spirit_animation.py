"""Offline avatar choreography: bounded expressions and seamless loop endpoints."""

import importlib.util
import math
import sys
from dataclasses import astuple
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[5] / "scripts/assets/spirit/animation.py"


def test_spirit_loops_are_seamless_bounded_and_cover_the_companion_vocabulary():
    assert SOURCE.is_file(), "The offline spirit choreography has not been implemented"
    spec = importlib.util.spec_from_file_location("spirit_animation_test", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert set(module.EXPRESSIONS) == {
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
    }
    for expression in module.EXPRESSIONS:
        first = module.pose_at(expression, 0.0)
        last = module.pose_at(expression, module.LOOP_SECONDS)
        for start, end in zip(astuple(first), astuple(last), strict=True):
            assert math.isclose(start, end, abs_tol=1e-9), expression
        for index in range(73):
            pose = module.pose_at(expression, index * module.LOOP_SECONDS / 72)
            assert all(math.isfinite(value) for value in astuple(pose)), expression
            assert 0.02 <= pose.eye_left <= 1.2
            assert 0.02 <= pose.eye_right <= 1.2
            assert 0.0 <= pose.mouth_open <= 0.2
            assert abs(pose.gaze_x) <= 0.12
            assert abs(pose.gaze_z) <= 0.12
            assert 0.94 <= pose.mass <= 1.06
    sleeping = module.pose_at("sleep", 0.7)
    assert sleeping.eye_left == sleeping.eye_right == 0.02
