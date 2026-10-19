"""Create one original Atlas score; a durable checkpoint forbids another paid attempt.

Commands: preflight (read-only API), generate (one paid attempt), edit (local only).
Existing credentials are read, never written. No earlier media is opened.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from dotenv import dotenv_values

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
DESTINATION = PROJECT / "public/audio/atlas-proof"
ORIGIN = "https://generativelanguage.googleapis.com"
MODEL = "lyria-3.5"
GUIDE = "https://ai.google.dev/gemini-api/docs/music-generation"
PRICING = "https://ai.google.dev/gemini-api/docs/pricing"
TERMS = "https://ai.google.dev/gemini-api/terms"
PROMPT = """Compose a new original 80-second instrumental electro-pop score for LIA,
an intelligent assistant that connects documents and makes uncertainty clear.
120 BPM, 4/4. Immediate, charismatic hook from the first beat. Precise punchy
syncopated electronic drums, dry tight clap, lively shuffling closed hats,
rounded elastic bass with short springy notes and carefully placed low rests.
Bright compact THREE-NOTE synth identity, luminous and warm, memorable without
constant repetition. Small glassy accents and clipped electronic chords create
depth. Contemporary premium product launch, confident, playful, lucid, human.
Clear polished stereo production with generous space around each transient.
Instrumental only: absolutely no singing, vocals, speech, choirs or vocal chops.
Entirely original melody and production; no quotation, no artist imitation.

The first sixteen seconds form a complete miniature with these intended cues:
[0:00 - 0:04] Strong clean opening downbeat, bass and drums already present.
Short separated synth notes gather into the bright three-note identity, a clear
little accent at 0:04. No slow introduction, no ambient prelude.
[0:04 - 0:10] Lock into a precise elastic groove. Two complementary short motifs
answer each other across the stereo field, becoming a single musical sentence.
Interesting syncopation, quick uncluttered fills, bright forward motion.
[0:10 - 0:13] A crisp accent at 0:10, then a deliberate small break and suspended
chord. The bass holds the pulse while the high notes briefly ask a question.
The mood is thoughtful curiosity, never alarm or dramatic suspense.
[0:13 - 0:16] Positive rhythmic re-entry at 0:13, the three-note identity returns
in a concise resolving cadence around 0:15.0. Give its final chord a beautiful
short natural decay through 0:16, with a clean musical edit point at 0:16.
[0:16 - 0:32] Resume a fresh lean groove after that miniature, develop the bass
and introduce a new melodic answer, preserving the same sound palette.
[0:32 - 0:48] Richer uplifting chords and tightly controlled rhythmic variation.
[0:48 - 1:04] A lighter bass-and-percussion bridge then a bright melodic lift.
[1:04 - 1:16] Confident final development with a fresh answer to the identity.
[1:16 - 1:20] Compact satisfying composed ending, natural tail, finish at 1:20.
Keep the whole composition to eighty seconds. No endless loop, no huge EDM
drop, no trailer swell, no harsh distortion, no corporate piano or acoustic bed.
"""


def write_json(path: Path, document: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", "utf-8")
    # Windows can briefly deny replacement of a closed, writable file (observed
    # both inside and outside the sandbox). Retry this LOCAL atomic operation
    # for at most 620ms; never unlink the checkpoint or repeat a provider call.
    for index in range(6):
        try:
            temporary.replace(path)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) not in {5, 32} or index == 5:
                raise
            time.sleep(0.02 * 2**index)


def key_from_existing_configuration() -> str:
    values = dotenv_values(ROOT / ".env")
    for name in ("GOOGLE_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = values.get(name)
        if value:
            return value
    raise RuntimeError("Existing Google credential unavailable")


def request(endpoint: str, key: str, payload: bytes | None = None) -> tuple[dict, dict]:
    outgoing = urllib.request.Request(
        ORIGIN + endpoint,
        data=payload,
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(outgoing, timeout=600 if payload else 30) as response:
        document = json.load(response)
        headers = {
            name: response.headers[name]
            for name in ("date", "x-request-id", "x-goog-request-id")
            if response.headers.get(name)
        }
    return document, headers


def preflight() -> None:
    document, _ = request("/v1beta/models?pageSize=1000", key_from_existing_configuration())
    listed = [m["name"] for m in document.get("models", []) if "lyria" in m.get("name", "")]
    evidence = {
        "checkedAt": datetime.now(UTC).isoformat(),
        "credentialPresent": True,
        "musicModelsListed": listed,
        "requestedModelAvailable": f"models/{MODEL}" in listed,
        "paidGenerationAttempts": 0,
        "publicDocumentation": {"guide": GUIDE, "pricing": PRICING, "terms": TERMS},
        "publishedPriceUsdPerSong": 0.08,
        "actualInvoiceCostUsd": None,
        "durationIsPromptTarget": True,
        "requestedDurationSeconds": 80,
        "manualDocsVerificationDate": "2026-10-17",
    }
    DESTINATION.mkdir(parents=True, exist_ok=True)
    write_json(DESTINATION / "provider-preflight.json", evidence)
    print(json.dumps(evidence), flush=True)


def generate() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    attempt = DESTINATION / "generation-attempt.json"
    if attempt.exists():
        print(json.dumps({"status": "existing_attempt_not_repeated"}), flush=True)
        return
    preflight_record = json.loads((DESTINATION / "provider-preflight.json").read_text("utf-8"))
    if not preflight_record.get("requestedModelAvailable"):
        raise RuntimeError("Live model preflight required")
    key = key_from_existing_configuration()
    payload = json.dumps(
        {
            "model": MODEL,
            "input": PROMPT,
            "response_format": {"type": "audio"},
            "store": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    checkpoint = {
        "status": "dispatched",
        "startedAt": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "paidGenerationAttempts": 1,
        "automaticRetries": 0,
        "publishedPriceUsdPerSong": 0.08,
        "actualInvoiceCostUsd": None,
        "requestSha256": hashlib.sha256(payload).hexdigest(),
        "credentialPersisted": False,
    }
    # Exclusive creation plus fsync precedes every external paid effect.
    with attempt.open("x", encoding="utf-8") as handle:
        json.dump(checkpoint, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    (DESTINATION / "composition-request.json").write_bytes(payload)
    print(json.dumps({"status": "generating", "paidAttempts": 1}), flush=True)
    started = time.monotonic()
    try:
        response, headers = request("/v1beta/interactions", key, payload)
    except Exception as error:
        checkpoint.update(
            status=("rejected" if isinstance(error, urllib.error.HTTPError) else "outcome_unknown"),
            errorType=type(error).__name__,
            httpStatus=getattr(error, "code", None),
        )
        write_json(attempt, checkpoint)
        print(json.dumps(checkpoint), flush=True)
        return
    checkpoint.update(status="received", elapsedSeconds=round(time.monotonic() - started, 3))
    write_json(attempt, checkpoint)
    blocks = [
        block
        for step in response.get("steps", [])
        if step.get("type") == "model_output"
        for block in step.get("content", [])
        if block.get("type") == "audio" and block.get("data")
    ]
    if len(blocks) != 1:
        checkpoint.update(status="response_without_single_audio", audioBlockCount=len(blocks))
        write_json(attempt, checkpoint)
        raise RuntimeError("Provider response did not contain exactly one audio block")
    audio = base64.b64decode(blocks[0]["data"], validate=True)
    suffix = ".wav" if audio[:4] == b"RIFF" else ".mp3"
    original = DESTINATION / ("atlas-original" + suffix)
    original.write_bytes(audio)
    source_hash = hashlib.sha256(audio).hexdigest()
    # Keep a reviewable provider receipt without duplicating large base64 audio.
    for step in response.get("steps", []):
        for block in step.get("content", []):
            if block.get("type") == "audio" and block.get("data"):
                block["data"] = f"preserved as {original.name}; sha256:{source_hash}"
    write_json(
        DESTINATION / "provider-response-receipt.json",
        {"response": response, "headers": headers},
    )
    checkpoint.update(
        status="generated",
        finishedAt=datetime.now(UTC).isoformat(),
        interactionId=response.get("id"),
        usage=response.get("usage"),
        sourceFile=original.name,
        sourceBytes=len(audio),
        sourceSha256=source_hash,
        reportedMimeType=blocks[0].get("mime_type"),
    )
    write_json(attempt, checkpoint)
    print(json.dumps(checkpoint), flush=True)


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, capture_output=True)


def probe(path: Path) -> dict:
    return json.loads(
        run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ]
        ).stdout
    )


def transients(path: Path) -> dict:
    """Measure spectral-flux onsets; tempo/grid are estimates, never exact beat claims."""
    raw = run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            "12000",
            "-f",
            "f32le",
            "-",
        ]
    ).stdout
    audio = np.frombuffer(raw, dtype="<f4")
    window, hop = 512, 120
    frames = np.lib.stride_tricks.sliding_window_view(audio, window)[::hop]
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(window), axis=1))
    flux = np.maximum(np.diff(np.log1p(spectrum), axis=0), 0).sum(axis=1)
    flux = np.concatenate(([0.0], flux))
    threshold = float(np.percentile(flux, 60))
    candidates = [
        i
        for i in range(1, len(flux) - 1)
        if flux[i] >= threshold and flux[i] > flux[i - 1] and flux[i] >= flux[i + 1]
    ]
    peaks: list[int] = []
    for index in sorted(candidates, key=lambda i: float(flux[i]), reverse=True):
        if all(abs(index - other) >= 16 for other in peaks):
            peaks.append(index)
    times = sorted(round((i * hop + window / 2) / 12000, 3) for i in peaks)
    envelope = flux - flux.mean()
    lags = range(40, 68)  # 89.6-150 BPM, 10 ms hops.
    lag = max(lags, key=lambda value: float(np.dot(envelope[:-value], envelope[value:])))
    cue_targets = [0.0, 4.0, 10.0, 13.0, 15.0]
    cues = [
        {
            "targetSeconds": target,
            "nearestMeasuredOnsetSeconds": min(times, key=lambda x: abs(x - target)),
        }
        for target in cue_targets
    ]
    return {
        "method": "positive log-spectral-flux local peaks, 12 kHz mono, 512-sample Hann window, 120-sample hop, 160ms separation",
        "onsetTimesSeconds": times,
        "onsetTimesAreMeasuredTransientsNotConfirmedBeats": True,
        "estimatedTempoBpm": round(6000 / lag, 3),
        "tempoIsEstimateNotProviderMetadata": True,
        "promptTargetTempoBpm": 120,
        "promptAccentTargetsSeconds": [0, 4, 10, 13, 16],
        "cueNearestMeasuredTransients": cues,
        "firstAudibleSignalSecondsAtMinus45Dbfs": round(
            int(np.flatnonzero(np.abs(audio) > 10 ** (-45 / 20))[0]) / 12000, 4
        ),
        "final16SecondsIsEditBoundaryNotAnAudibleBeat": True,
    }


def edit() -> None:
    checkpoint = json.loads((DESTINATION / "generation-attempt.json").read_text("utf-8"))
    if checkpoint.get("status") != "generated":
        raise RuntimeError("No successful source to edit; no generation is attempted")
    original = DESTINATION / checkpoint["sourceFile"]
    if hashlib.sha256(original.read_bytes()).hexdigest() != checkpoint["sourceSha256"]:
        raise RuntimeError("Original audio does not match the preserved receipt")
    original_probe = probe(original)
    if float(original_probe["format"]["duration"]) < 16:
        raise RuntimeError("Source shorter than the approved proof")
    decoded = DESTINATION / "atlas-original-48k.wav"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(original),
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            str(decoded),
        ]
    )
    # Measured source: first full drum hit ~1.95s, tempo ~125 BPM. Remove its
    # near-silent prelude and slow by 4% to the requested 120 BPM, without repitching.
    working = DESTINATION / "atlas-proof-16s.wav"
    filters = "atrim=start=1.95:end=19,asetpts=PTS-STARTPTS,atempo=0.96,apad,atrim=0:16,afade=t=in:st=0:d=0.008,afade=t=out:st=15.2:d=0.8,loudnorm=I=-16:TP=-1.5:LRA=8"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(decoded),
            "-af",
            filters,
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            str(working),
        ]
    )
    loudness = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(working),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=8:print_format=json",
            "-f",
            "null",
            "-",
        ]
    ).stderr.decode("utf-8", "replace")
    measured = json.loads(loudness[loudness.rfind("{") : loudness.rfind("}") + 1])
    with wave.open(str(working), "rb") as wav:
        frames = wav.getnframes()
        duration = frames / wav.getframerate()
        if duration != 16 or wav.getframerate() != 48000 or wav.getnchannels() != 2:
            raise RuntimeError("Unexpected proof audio format")
    metadata = {
        "title": "LIA — Atlas / Les liens clairs",
        "provider": "Google Gemini API",
        "model": MODEL,
        "sourceOriginal": original.name,
        "sourceSha256": checkpoint["sourceSha256"],
        "sourceDurationSeconds": float(original_probe["format"]["duration"]),
        "decodedSource": decoded.name,
        "workingAudio": "audio/atlas-proof/atlas-proof-16s.wav",
        "proofDurationSeconds": duration,
        "sampleRateHz": 48000,
        "channels": 2,
        "sampleFormat": "signed 24-bit little-endian PCM WAV",
        "editFilter": filters,
        "sourceTrimStartSeconds": 1.95,
        "tempoFactorWithoutPitchChange": 0.96,
        "requestedSourceDurationSeconds": 80,
        "sourceDurationExceededPromptTarget": True,
        "requestedSourceFormat": "WAV",
        "returnedSourceFormat": "MP3",
        "providerPromptAdherenceIsNotGuaranteed": True,
        "proofSha256": hashlib.sha256(working.read_bytes()).hexdigest(),
        "measuredLoudness": {
            "integratedLufs": float(measured["input_i"]),
            "truePeakDbtp": float(measured["input_tp"]),
            "rangeLu": float(measured["input_lra"]),
            "thresholdLufs": float(measured["input_thresh"]),
        },
        "transients": transients(working),
        "publishedPriceUsd": 0.08,
        "actualInvoiceCostUsd": None,
        "paidGenerationAttempts": 1,
        "automaticRetries": 0,
        "humanAudioAudition": False,
        "instrumentalIsPromptRequirementNotVerifiedByAnAudioClassifier": True,
        "terms": TERMS,
        "termsQualification": "Google does not claim ownership of generated content. API terms apply. No exclusive copyright or Creative Commons licence is asserted.",
        "creativeReferences": "New written brief only; no earlier video or music used as creative reference.",
    }
    write_json(DESTINATION / "atlas-proof-music.json", metadata)
    print(json.dumps(metadata, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        {"preflight": preflight, "generate": generate, "edit": edit}[
            sys.argv[1] if len(sys.argv) > 1 else "preflight"
        ]()
    except Exception as error:
        # Exception text can contain URLs/credentials; print only bounded facts.
        print(
            json.dumps(
                {
                    "status": "stopped",
                    "errorType": type(error).__name__,
                    "httpStatus": getattr(error, "code", None),
                }
            ),
            flush=True,
        )
        sys.exit(1)
