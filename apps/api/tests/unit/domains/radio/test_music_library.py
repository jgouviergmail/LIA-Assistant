"""The player's music library: every mood the station names has its music, shipped as generated.

The backend decides the mood of every programme (``music_mood``); the web player
plays the library's tracks for it. A mood without music would air silence under a
programme, a track shipped without its provenance would be a file nobody can
account for, and a file the library does not list is weight every install carries
for nothing — each is refused here, where both halves of the repository meet.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.domains.radio.formats import MusicMood

pytestmark = pytest.mark.unit

_WEB = Path(__file__).resolve().parents[5] / "web"
_LIBRARY = _WEB / "src" / "data" / "radio" / "music-library.json"
_MUSIC = _WEB / "public" / "radio" / "music"
_URL_PREFIX = "/radio/music/"
#: Enough tracks that a default session of half an hour never repeats one.
_TRACKS_PER_MOOD_MIN = 8


def _library() -> dict[str, list[dict[str, Any]]]:
    moods: dict[str, list[dict[str, Any]]] = json.loads(_LIBRARY.read_text(encoding="utf-8"))[
        "moods"
    ]
    return moods


def _provenance() -> dict[str, Any]:
    provenance: dict[str, Any] = json.loads(
        (_MUSIC / "PROVENANCE.json").read_text(encoding="utf-8")
    )
    return provenance


def test_every_mood_the_station_names_has_its_music() -> None:
    library = _library()
    assert set(library) == {mood.value for mood in MusicMood}
    for mood, tracks in library.items():
        assert len(tracks) >= _TRACKS_PER_MOOD_MIN, mood
        assert len({track["file"] for track in tracks}) == len(tracks), mood


def test_every_listed_track_is_shipped_exactly_as_generated() -> None:
    tracks = _provenance()["tracks"]
    for mood, listed in _library().items():
        for track in listed:
            assert track["file"].startswith(_URL_PREFIX), track["file"]
            relative = track["file"].removeprefix(_URL_PREFIX)
            record = tracks[relative]
            path = _MUSIC / relative
            assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"], relative
            assert record["mood"] == mood
            assert track["duration_s"] == record["duration_seconds"]
            assert "Instrumental only, no vocals" in record["prompt"]


def test_no_music_file_ships_unlisted_or_unaccounted_for() -> None:
    listed = {
        track["file"].removeprefix(_URL_PREFIX)
        for tracks in _library().values()
        for track in tracks
    }
    shipped = {path.relative_to(_MUSIC).as_posix() for path in _MUSIC.rglob("*.mp3")}
    assert shipped == listed
    assert set(_provenance()["tracks"]) == listed
