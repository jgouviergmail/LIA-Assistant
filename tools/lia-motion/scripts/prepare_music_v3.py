"""Prepare licensed, separate warm v3 candidates; no canonical edit is changed."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
sys.path.insert(0, str(ROOT))
from scripts.assets.encode_landing_video import (  # noqa: E402
    BEAT_ANALYSIS_VERSION,
    ONSET_LEAD_MS,
    beat_map,
)

SELECTED_SECONDS = 30
AUDITION_SECONDS = 20
HEADROOM_DB = 6
CANDIDATES = [
    {
        "id": "sunsetter",
        "title": "Sunsetter",
        "artist": "Shane Ivers",
        "source": "https://www.silvermansound.com/free-music/sunsetter",
        "sourceAudio": "https://www.silvermansound.com/wp-content/uploads/sunsetter.mp3",
        "sourceSha256": "0de0349ce104e1c6f397b06830c408517359964de98b9c121faf2b04fee90fd1",
        "publishedTempoBpm": 117,
        "isrc": "UKEZT2300012",
        "attribution": "Sunsetter — Shane Ivers · silvermansound.com · CC BY 4.0 · montage LIA",
        "styleSource": "Summer dance; acoustic guitar, ukulele, bass and drums",
        "trimFrom": 0,
    },
    {
        "id": "tidie-fridie",
        "title": "Tidie Fridie",
        "artist": "Shane Ivers",
        "source": "https://www.silvermansound.com/free-music/tidie-fridie",
        "sourceAudio": "https://www.silvermansound.com/wp-content/uploads/tidie-fridie.mp3",
        "sourceSha256": "ea732d99beb1a1819b6bd1f5da5e9bd50c8ec24cd3a0faea776ee2379d446941",
        "publishedTempoBpm": 105,
        "isrc": "UKEZT2300002",
        "attribution": "Tidie Fridie — Shane Ivers · silvermansound.com · CC BY 4.0 · montage LIA",
        "styleSource": "Funky bass; electric piano, vintage drums and bass guitars",
        "trimFrom": 0,
    },
    {
        "id": "transition",
        "title": "Transition",
        "artist": "Jason Shaw",
        "source": "https://audionautix.com/free-music/pop-funk",
        "sourceAudio": "https://audionautix.com/Music/Transition.mp3",
        "sourceSha256": "2a095f4ed86dbc807319f1c96296f8b1fd66551d195995add0a4dbbd2d2e19a4",
        "attribution": "Transition — Jason Shaw · audionautix.com · CC BY 4.0 · montage LIA",
        "styleSource": "Pop/funk; published mood: bouncy, uplifting, bright",
        "trimFrom": 4.051,
    },
]

audio = PROJECT / "public/audio/v3"
audio.mkdir(parents=True, exist_ok=True)
records = []
selected_only = "--selected-only" in sys.argv
for candidate in CANDIDATES[:1] if selected_only else CANDIDATES:
    name = candidate["id"]
    target_seconds = SELECTED_SECONDS if name == "sunsetter" else AUDITION_SECONDS
    original = audio / f"{name}-original.mp3"
    target = audio / f"{name}-{target_seconds}s.wav"
    if not original.exists():
        urllib.request.urlretrieve(candidate["sourceAudio"], original)
    if hashlib.sha256(original.read_bytes()).hexdigest() != candidate["sourceSha256"]:
        raise ValueError(f"The official recording fingerprint changed: {name}")
    start = candidate["trimFrom"]
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(original),
            "-af",
            f"atrim=start={start}:end={start + target_seconds},"
            f"asetpts=PTS-STARTPTS,volume=-{HEADROOM_DB}dB",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s24le",
            str(target),
        ],
        check=True,
    )
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_name,sample_rate,channels,bits_per_raw_sample",
                "-of",
                "json",
                str(target),
            ],
            text=True,
        )
    )
    duration = float(probe["format"]["duration"])
    if abs(duration - target_seconds) > 0.001:
        raise ValueError(f"Wrong excerpt duration: {name} {duration}")
    beats, summary = beat_map(target)
    if not beats or summary["onset_hit_rate"] < 0.9:
        raise ValueError(f"No reliable measured onsets in {name}")
    record = {
        **candidate,
        "license": "CC-BY-4.0",
        "licenseUrl": "https://creativecommons.org/licenses/by/4.0/",
        "audio": f"audio/v3/{target.name}",
        "durationSeconds": duration,
        "audioSha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "sourceFormat": "Official MP3 decoded with headroom to working PCM; not lossless",
        "edit": {
            "trimFrom": start,
            "trimTo": start + target_seconds,
            "repetitions": 0,
            "decodeHeadroomDb": HEADROOM_DB,
        },
        "beats": [round(ms / 1000, 3) for ms, _, _ in beats],
        "beatEntries": beats,
        "analysisVersion": BEAT_ANALYSIS_VERSION,
        "onsetLeadMs": ONSET_LEAD_MS,
        "analysis": summary,
        "review": {
            "licenceAndRecordingVerified": True,
            "humanListening": False,
            "styleJudgement": "Composer's instrumentation/mood and measured rhythm; listening required",
        },
    }
    records.append(record)
    print(
        f"{name}: {duration:.3f}s, {len(beats)} measured pulses, "
        f"median period {summary['median_interval_ms']:.0f}ms, "
        f"onset alignment {summary['onset_hit_rate']:.1%}"
    )

selected = records[0]
if abs(selected["analysis"]["median_interval_ms"] - 60000 / 117) > 15:
    raise ValueError("The Sunsetter edit no longer agrees with its published tempo")
(PROJECT / "src/music-v3.json").write_text(
    json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
if not selected_only:
    (audio / "candidates.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
