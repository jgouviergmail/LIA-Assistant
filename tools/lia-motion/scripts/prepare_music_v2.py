"""Prepare the second licensed soundtrack without replacing the first edit."""

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

SOURCE_URL = "https://www.silvermansound.com/wp-content/uploads/pulsar.mp3"
SOURCE_SHA256 = "8dbfb43494f0d7114d145b8bff9dd47704830e0dfb96c329c0e3f36b142e1b54"
SOURCE_PAGE = "https://www.silvermansound.com/free-music/pulsar"
TARGET_SECONDS = 160
DECODE_HEADROOM_DB = 6
audio = PROJECT / "public/audio"
original = audio / "pulsar-original.mp3"
target = audio / "music-v2.wav"
audio.mkdir(parents=True, exist_ok=True)
if not original.exists():
    urllib.request.urlretrieve(SOURCE_URL, original)
if hashlib.sha256(original.read_bytes()).hexdigest() != SOURCE_SHA256:
    raise ValueError("Pulsar differs from the reviewed official CC BY recording")

# The source runs for over three minutes. This edit keeps its existing intro,
# build, breakdown and return rather than inventing or looping a musical part.
# Per-composition fades and EBU loudness processing remain the renderer's job.
# Decoding a hot MP3 produces floating samples above full scale. Attenuate
# before integer PCM conversion so this working file adds no clipped samples.
# PCM is a working format: it does not restore information lost in the MP3.
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
        f"atrim=start=0:end={TARGET_SECONDS},asetpts=PTS-STARTPTS,"
        f"volume=-{DECODE_HEADROOM_DB}dB",
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
if abs(duration - TARGET_SECONDS) > 0.001:
    raise ValueError(f"Wrong music-v2 duration: {duration}")
beats, summary = beat_map(target)
if not beats or summary["onset_hit_rate"] < 0.9:
    raise ValueError("The new soundtrack has no reliable measured beat map")
data = {
    "title": "Pulsar",
    "artist": "Shane Ivers",
    "license": "CC-BY-4.0",
    "licenseUrl": "https://creativecommons.org/licenses/by/4.0/",
    "source": SOURCE_PAGE,
    "audio": "audio/music-v2.wav",
    "durationSeconds": duration,
    "sourceAudio": SOURCE_URL,
    "sourceSha256": SOURCE_SHA256,
    "sourceFormat": "Official MP3, 320 kbps, 44.1 kHz stereo; decoded to working PCM",
    "publishedTempoBpm": 124,
    "isrc": "UKEZT1700013",
    "attribution": "Pulsar — Shane Ivers · silvermansound.com · CC BY 4.0 · montage LIA",
    "edit": {
        "trimFrom": 0,
        "trimTo": TARGET_SECONDS,
        "repetitions": 0,
        "decodeHeadroomDb": DECODE_HEADROOM_DB,
    },
    "beats": [round(ms / 1000, 3) for ms, _, _ in beats],
    "beatEntries": beats,
    "analysisVersion": BEAT_ANALYSIS_VERSION,
    "onsetLeadMs": ONSET_LEAD_MS,
    "analysis": summary,
    "review": {
        "kind": "Source licence, file and measured rhythmic structure inspected",
        "humanListening": False,
    },
}
(PROJECT / "src/music-v2.json").write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
(PROJECT / "src/music.json").write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(
    f"Pulsar prepared: {duration:.3f}s, {len(beats)} measured beats, "
    f"median period {summary['median_interval_ms']:.0f}ms, "
    f"onset alignment {summary['onset_hit_rate']:.1%}"
)
