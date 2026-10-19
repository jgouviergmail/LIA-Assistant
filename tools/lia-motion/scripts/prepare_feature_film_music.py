"""Create the complete 80-second score edit from the new original take, offline."""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "public/audio/atlas-proof/atlas-original-48k.wav"
OUTPUT = PROJECT / "public/audio/feature-film"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "lia-feature-film-80s.wav"
    filters = (
        "atrim=start=1.95,asetpts=PTS-STARTPTS,atempo=0.96,atrim=0:80,"
        "afade=t=in:st=0:d=0.008,afade=t=out:st=78.4:d=1.6,"
        "loudnorm=I=-16:TP=-1.5:LRA=8"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(SOURCE),
            "-af",
            filters,
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            str(target),
        ],
        check=True,
    )
    spec = importlib.util.spec_from_file_location(
        "score_analysis", PROJECT / "scripts/generate_atlas_proof_music.py"
    )
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    transients = analyzer.transients(target)
    onsets = transients["onsetTimesSeconds"]
    targets = [0, 4, 12, 20, 28, 36, 44, 52, 60, 68, 76, 80]
    cues = []
    for seconds in targets:
        measured = (
            min(onsets, key=lambda value: abs(value - seconds))
            if seconds not in (0, 80)
            else seconds
        )
        frame = round(measured * 60)
        cues.append({"targetSeconds": seconds, "measuredOnsetSeconds": measured, "frame": frame})
    metadata = {
        "title": "LIA — Le fil de ta journée",
        "durationSeconds": 80,
        "fps": 60,
        "sampleRate": 48000,
        "originalMusicSource": "audio/atlas-proof/atlas-original.mp3",
        "sourceSha256": "3684f1c85cc9868860baf43180f256e4b7300fe348a3520145b6a2e460a79201",
        "workingAudio": "audio/feature-film/lia-feature-film-80s.wav",
        "workingSha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "editFilter": filters,
        "newPaidCalls": 0,
        "provenance": "New original AI score created for this task, full edit from the source take; no soundtrack from the old landing film.",
        "cues": cues,
        "transients": transients,
        "humanListeningCheckPerformed": False,
    }
    (OUTPUT / "score.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"audio": str(target), "cues": cues}))


if __name__ == "__main__":
    main()
