"""Generate eight World decor cues once, then normalize offline; key arrives on stdin.

Never stores or logs credentials. Successful generation receipts are reused to avoid
charging twice after a later encoding failure. Runtime playback uses only local assets.

The provenance records this script's digest as a fresh clone checks it out (LF, the
repository's eol for it), so anyone can reproduce it; the manifest's revision moves on
from its own value, and only when a public file's bytes changed.
"""

from __future__ import annotations
import argparse
import getpass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RATE = 32000
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "apps/web/public/world/audio/v1"
MODEL = "eleven_text_to_sound_v2"
# The one sentence of the manifest-wide licence note this script vouches for. The note
# covers every asset family of the manifest, so it is never rewritten here: the
# sentence is appended only when the note lacks it.
RECEIPTS_NOTE = "Per-asset receipts record actual one-time provider charges."
CUES = {
    "leaves": (
        1.2,
        "One close gentle hand brushing a leafy indoor plant: a rich natural dry leaf rustle and soft foliage swish, quick clear attack followed by a short organic settling tail. Intimate cozy game perspective, not a wind ambience. Isolated single sound effect, no speech, music or other events.",
    ),
    "billiards": (
        1.0,
        "Three clean realistic billiard balls collide: a crisp rounded ivory clack followed by two softer separated pool-ball ticks and a tiny felt-table roll. Close indoor perspective, precise short physical impacts, no metallic ringing, voices, music or room ambience.",
    ),
    "splash": (
        1.1,
        "One small coin drops into a fountain pool: a clear soft plip impact immediately at the start, followed by a tiny natural water splash, delicate droplets and short rippling-water decay. Close gentle physical sound, not a large splash or continuous running water, no voices or music.",
    ),
    "machine-start": (
        2.2,
        "One compact workshop machine starts: a quiet mechanical relay click, a smooth electric motor winding up with subtle gears and rollers engaging, then a short soft whir tapering cleanly away. Detailed satisfying friendly machinery, controlled volume, no alarm, harsh drill, speech or music.",
    ),
    "machine-gantry": (
        2.2,
        "One compact workshop gantry starts and performs a short cycle: two substantial rounded pneumatic piston chuffs, a smooth sliding carriage servo moving sideways, then a soft mechanical stop. Clearly rhythmic air pressure and metal carriage rather than a continuous electric motor. Satisfying detailed close physical machinery at restrained volume. No harsh drill, alarm, speech, music or ambience.",
    ),
    "machine-printer": (
        2.2,
        "One small paper-processing machine starts: a delicate relay click, quick rubber rollers grip a sheet, a distinct fluttering paper feed with little stepper-motor chirrs and a final clean soft paper shuffle. Precise cozy workshop perspective, recognizably paper and rollers, no pneumatic chuff, continuous heavy motor, alarm, voices or music.",
    ),
    "cat-meow": (
        1.0,
        "One natural friendly domestic cat meow, clear recognizable mid-pitched meow with a soft breathy ending. A single short vocalization, close and relaxed, no purr bed, distress, human voice, other animal, background ambience or music.",
    ),
    "workout-effort": (
        0.65,
        "One very short intense deep human exertion grunt from an adult bodybuilder pushing a heavy bar upward: a powerful chesty hnnngh with a sharp effort onset and short breath release. Athletic effort, not pain or a scream. Single isolated nonverbal grunt, no words, counting, panting loop, music or background sound.",
    ),
}


def generate(kind: str, key: str, work: Path) -> tuple[Path, dict]:
    seconds, prompt = CUES[kind]
    body = {
        "text": prompt,
        "duration_seconds": seconds,
        "loop": False,
        "prompt_influence": 0.5,
        "model_id": MODEL,
    }
    source, receipt = work / (kind + "-source.mp3"), work / (kind + "-receipt.json")
    if source.exists() and receipt.exists():
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        if (
            saved["request"] == body
            and saved["source_sha256"] == sha256(source.read_bytes()).hexdigest()
        ):
            return source, saved
        raise SystemExit(
            "Existing receipt differs; inspect before another paid request: " + kind
        )
    request = Request(
        "https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128",
        data=json.dumps(body).encode(),
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            content = response.read(10 * 1024 * 1024 + 1)
            if len(content) > 10 * 1024 * 1024 or not response.headers.get(
                "Content-Type", ""
            ).startswith("audio/"):
                raise SystemExit("Unexpected bounded audio response: " + kind)
            charged = response.headers.get("character-cost")
            saved = {
                "request": body,
                "status": response.status,
                "billed_credits": (
                    int(charged) if charged and charged.isdigit() else None
                ),
                "source_sha256": sha256(content).hexdigest(),
            }
    except HTTPError as error:
        raise SystemExit(
            "ElevenLabs HTTP "
            + str(error.code)
            + " for "
            + kind
            + "; no automatic paid retry"
        ) from None
    except URLError:
        raise SystemExit(
            "ElevenLabs transport unavailable for " + kind + "; inspect before retry"
        ) from None
    source.write_bytes(content)
    receipt.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    return source, saved


def encode(source: Path, destination: Path) -> None:
    command = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", str(source), "-vn"]
    first = subprocess.run(
        command
        + ["-af", "loudnorm=I=-24:TP=-7:LRA=7:print_format=json", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    stats, _ = json.JSONDecoder().raw_decode(first.stderr[first.stderr.rfind("{") :])
    filter_ = (
        "loudnorm=I=-24:TP=-7:LRA=7:linear=true:measured_I="
        + stats["input_i"]
        + ":measured_TP="
        + stats["input_tp"]
        + ":measured_LRA="
        + stats["input_lra"]
        + ":measured_thresh="
        + stats["input_thresh"]
        + ":offset="
        + stats["target_offset"]
    )
    subprocess.run(
        command
        + [
            "-af",
            filter_
            + ",afade=t=in:d=0.008,afade=t=out:st="
            + str(max(0, duration(source) - 0.04))
            + ":d=0.04",
            "-ac",
            "1",
            "-ar",
            str(RATE),
            "-c:a",
            "libmp3lame",
            "-b:a",
            "64k",
            str(destination),
        ],
        capture_output=True,
        check=True,
    )


def duration(path: Path) -> float:
    value = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    )
    return float(value.strip())


def composition_digest(path: Path) -> str:
    """SHA-256 of a source as a fresh clone checks it out (LF, its eol attribute).

    A Windows working copy may carry CRLF: hashing those bytes recorded a digest
    nobody could reproduce from the repository.
    """
    return sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def merge_manifest(manifest: dict, assets: list[dict]) -> dict:
    """Install the generated cues in the manifest and keep everything else as it is.

    The revision moves on from the manifest's own value, and only when a public
    file's bytes changed: it is the cache key of every sound URL, so a change of
    metadata alone must not make clients fetch identical audio again. A cue whose
    provider source changed keeps its former entry, under the revision that
    replaced it. The licence note covers every asset family of the manifest: it is
    never rewritten, only completed with this script's sentence when it lacks it.
    """
    prior = [asset for asset in manifest["assets"] if asset["id"] in CUES]
    revision = manifest["asset_revision"]
    if {asset["id"]: asset["sha256"] for asset in prior} != {
        asset["id"]: asset["sha256"] for asset in assets
    }:
        revision += 1
    replaced = []
    for asset in prior:
        replacement = next(
            (value for value in assets if value["id"] == asset["id"]), None
        )
        if replacement and replacement["source_sha256"] != asset["source_sha256"]:
            replaced.append({**asset, "replaced_in_revision": revision})
    merged = {**manifest}
    if replaced:
        merged["superseded_assets"] = [
            *manifest.get("superseded_assets", []),
            *replaced,
        ]
    merged["assets"] = [
        asset for asset in manifest["assets"] if asset["id"] not in CUES
    ] + assets
    merged["asset_revision"] = revision
    note = manifest.get("license_note", "")
    if RECEIPTS_NOTE not in note:
        merged["license_note"] = f"{note} {RECEIPTS_NOTE}".strip()
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    print("Ready for one-time credential on stdin", flush=True)
    key = (
        getpass.getpass("One-time credential (not echoed): ")
        if sys.stdin.isatty()
        else sys.stdin.readline().strip()
    )
    if not key.startswith("sk_") or len(key) > 256:
        raise SystemExit("Missing one-time credential")
    composition = composition_digest(Path(__file__))
    assets = []
    for kind in CUES:
        source, receipt = generate(kind, key, args.work)
        destination = args.work / (kind + ".mp3")
        encode(source, destination)
        assets.append(
            {
                "id": kind,
                "file": destination.name,
                "text": CUES[kind][1],
                "duration_seconds": duration(destination),
                "loop": False,
                "provider": "elevenlabs",
                "model": MODEL,
                "state": "generated",
                "status": receipt["status"],
                "billed_credits": receipt["billed_credits"],
                "bytes": destination.stat().st_size,
                "sha256": sha256(destination.read_bytes()).hexdigest(),
                "source_sha256": receipt["source_sha256"],
                "composition_source": "scripts/world-decor-audio.py",
                "composition_source_sha256": composition,
                "encoding": "MP3 mono 32000 Hz 64 kbit/s",
                "normalization": "Two-pass -24 LUFS / -7 dBTP target; short fades",
            }
        )
        print(
            kind
            + ": generated and normalized; credits="
            + str(receipt["billed_credits"]),
            flush=True,
        )
    key = ""
    manifest_path = TARGET / "provenance.json"
    manifest = merge_manifest(
        json.loads(manifest_path.read_text(encoding="utf-8")), assets
    )
    for asset in assets:
        shutil.copyfile(args.work / asset["file"], TARGET / asset["file"])
    # The manifest's eol is LF; Windows text mode would write CRLF.
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("All eight cues installed; credential discarded", flush=True)


if __name__ == "__main__":
    main()
