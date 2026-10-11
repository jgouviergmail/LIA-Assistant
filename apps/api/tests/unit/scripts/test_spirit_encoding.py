"""The offline encode preserves real animation timing and alpha, under a budget."""

import importlib.util
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

SOURCE = Path(__file__).resolve().parents[5] / "scripts/assets/encode_spirit_avatar.py"


@pytest.mark.parametrize("size", [192, 96])
def test_spirit_encode_preserves_frames_alpha_and_loop_timing(tmp_path, size):
    assert SOURCE.is_file(), "The offline WebP encoder has not been implemented"
    spec = importlib.util.spec_from_file_location("spirit_encoding_test", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "frames"
    source.mkdir()
    for index in range(4):
        image = Image.new("RGBA", (192, 192))
        draw = ImageDraw.Draw(image)
        draw.ellipse((40 + index * 3, 30, 145 + index * 3, 170), fill=(190, 215, 250, 255))
        image.save(source / f"{index:03d}.png")
    destination = tmp_path / "out"
    result = module.encode_clip(source, destination, "neutral", 80, size=size)
    assert result["frames"] == 4
    assert result["duration_ms"] == 320
    assert result["clip_bytes"] <= module.CLIP_BUDGET
    with Image.open(destination / "neutral.webp") as clip:
        assert clip.is_animated
        assert clip.n_frames == 4
        assert clip.info["loop"] == 0
        timestamps = []
        for index in range(clip.n_frames):
            clip.seek(index)
            clip.load()
            timestamps.append(clip.info["duration"])
            assert clip.convert("RGBA").getextrema()[3] == (0, 255)
        assert timestamps == [80] * 4
    with Image.open(destination / "neutral-still.webp") as still:
        assert not getattr(still, "is_animated", False)
        assert still.size == (size, size)
        assert still.convert("RGBA").getextrema()[3] == (0, 255)


def test_compact_schedule_retains_blink_frames_and_the_full_loop_duration():
    spec = importlib.util.spec_from_file_location("spirit_schedule_test", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    indices, durations = module.frame_schedule(40, 80, 96)
    assert {11, 12, 13, 31, 32, 33}.issubset(indices)
    assert indices[0] == 0
    assert len(indices) < 40
    assert sum(durations) == 3200
    assert set(durations) == {80, 160}
    full_indices, full_durations = module.frame_schedule(40, 80, 192)
    assert full_indices == list(range(40))
    assert full_durations == [80] * 40


def test_live_companion_body_is_a_single_transparent_frame_under_the_pack_budget(
    tmp_path,
):
    spec = importlib.util.spec_from_file_location("spirit_body_encoding_test", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "body.png"
    image = Image.new("RGBA", (192, 192))
    ImageDraw.Draw(image).ellipse((35, 12, 158, 176), fill=(224, 233, 245, 255))
    image.save(source)
    result = module.encode_body(source, tmp_path / "out")
    with Image.open(tmp_path / "out" / "body.webp") as body:
        assert not getattr(body, "is_animated", False)
        assert body.size == (192, 192)
        assert body.convert("RGBA").getextrema()[3] == (0, 255)
    assert result["bytes"] <= module.BODY_BUDGET
