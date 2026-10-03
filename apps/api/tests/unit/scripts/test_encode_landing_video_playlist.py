"""The landing videos' encoder (ADR-330): which renditions a master feeds, and the playlist.

A master is never upscaled — a 720p one feeds the 720p pair alone, offered to
every viewport; a web H.264 master may stand for its own rendition, remuxed,
because re-encoding it only lost quality at the same rate (measured 2026-10-03:
VMAF 93.2 at 1.00 Mbit/s against a 1.04 Mbit/s master). And a second video is
APPENDED to the manifest the landing already reads, never written over it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

# The encoder lives at the REPOSITORY root (``scripts/assets``), not under
# ``apps/api/scripts``, which is what ``scripts.…`` resolves to from here.
_SCRIPT = Path(__file__).resolve().parents[5] / "scripts" / "assets" / "encode_landing_video.py"


def _load_encoder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("encode_landing_video", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE it runs: the script's frozen dataclass resolves its
    # string annotations through `sys.modules[cls.__module__]`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


encoder = _load_encoder()


def _labels(renditions: list) -> list[tuple[str, str, int | None]]:
    return [(r.label, r.codec, r.min_width) for r in renditions]


class TestRenditionsFor:
    def test_a_1080p_master_feeds_the_four_renditions_unchanged(self) -> None:
        assert encoder.renditions_for(1080) == list(encoder.RENDITIONS)

    def test_a_720p_master_feeds_the_720p_pair_alone_offered_to_every_viewport(self) -> None:
        assert _labels(encoder.renditions_for(720)) == [
            ("720p", "av1", None),
            ("720p", "h264", None),
        ]

    def test_a_master_between_two_sizes_is_never_upscaled(self) -> None:
        assert {r.height for r in encoder.renditions_for(900)} == {720}

    def test_a_master_smaller_than_every_rendition_is_refused(self) -> None:
        with pytest.raises(ValueError, match="smaller than every rendition"):
            encoder.renditions_for(480)


class TestCopiedRendition:
    def test_the_h264_rendition_of_the_masters_own_height(self) -> None:
        copied = encoder.copied_rendition(encoder.renditions_for(720), "h264", 720)
        assert (copied.label, copied.codec) == ("720p", "h264")

    def test_refused_for_a_master_that_is_not_h264(self) -> None:
        with pytest.raises(ValueError, match="needs an H.264 master"):
            encoder.copied_rendition(encoder.renditions_for(720), "hevc", 720)

    def test_refused_when_no_h264_rendition_has_the_masters_height(self) -> None:
        with pytest.raises(ValueError, match="no H.264 rendition is 900p"):
            encoder.copied_rendition(encoder.renditions_for(900), "h264", 900)


FIRST = {"poster": "underclass-aaa-poster.webp", "beats": "underclass-aaa-beats-v2.json"}
SECOND = {"poster": "stopshipping-bbb-poster.webp", "beats": "stopshipping-bbb-beats-v2.json"}
SECOND_AGAIN = {"poster": "stopshipping-ccc-poster.webp", "beats": "stopshipping-ccc-beats-v2.json"}
THIRD = {"poster": "third-ddd-poster.webp"}


class TestMergePlaylist:
    def test_a_first_encoding_writes_the_video_alone(self) -> None:
        assert encoder.merge_playlist(None, FIRST, "underclass", append=False) == FIRST

    def test_append_puts_the_video_after_the_ones_already_named(self) -> None:
        merged = encoder.merge_playlist(FIRST, SECOND, "stopshipping", append=True)
        assert merged == {**FIRST, "next": [SECOND]}
        merged = encoder.merge_playlist(merged, THIRD, "third", append=True)
        assert merged["next"] == [SECOND, THIRD]

    def test_append_replaces_an_earlier_encoding_of_the_same_name_and_keeps_its_place_last(
        self,
    ) -> None:
        playlist = {**FIRST, "next": [SECOND, THIRD]}
        merged = encoder.merge_playlist(playlist, SECOND_AGAIN, "stopshipping", append=True)
        assert merged["next"] == [THIRD, SECOND_AGAIN]

    def test_re_encoding_the_first_video_keeps_the_ones_that_follow(self) -> None:
        playlist = {**FIRST, "next": [SECOND]}
        renewed = {"poster": "underclass-eee-poster.webp"}
        assert encoder.merge_playlist(playlist, renewed, "underclass", append=False) == {
            **renewed,
            "next": [SECOND],
        }

    def test_append_needs_a_manifest_and_never_appends_the_first_video_to_itself(self) -> None:
        with pytest.raises(ValueError, match="needs a manifest"):
            encoder.merge_playlist(None, SECOND, "stopshipping", append=True)
        with pytest.raises(ValueError, match="is the first video"):
            encoder.merge_playlist(FIRST, FIRST, "underclass", append=True)

    def test_a_name_owns_its_own_files_only(self) -> None:
        assert encoder.owns(SECOND, "stopshipping")
        assert not encoder.owns(SECOND, "stop")
        assert not encoder.owns({"poster": "stopshipping2-x-poster.webp"}, "stopshipping")
