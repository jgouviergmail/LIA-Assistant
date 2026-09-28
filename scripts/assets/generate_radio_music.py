"""Generate LIA Radio's music library with Lyria — once, reviewably (ADR-324).

The station's music is not fetched at run time and costs nothing per listener: a
library of instrumental tracks, a dozen per mood, is generated ONCE by this script
and committed beside the web player, with its provenance (prompt, model, date,
hashes, loudness). The player plays it continuously under the whole session and
lowers it under the voices; a mood follows the programme (the news) and the
listener's hour. Re-running it generates only what is missing; the diff of
``PROVENANCE.json`` is the review.

Why generated rather than downloaded: a catalogue track picked by its title cannot
be checked for vocals, rights or fit without listening, and a third-party stream
grants a listener no rights at all (onlyai.fm, read 2026-09-26: no licence to
listeners, ``/media/audio`` disallowed by its robots.txt). A prompt states what a
bed must be; the output belongs to the project and carries Lyria's SynthID mark.

Measured before it was trusted (2026-09-26, one song): ``lyria-3.5`` on the
Interactions API answers an MP3 (44.1 kHz stereo, 192 kbps) of about two minutes
in about 26 s, and a text part holding only section markers (``[[A0]]``) when it
sings nothing — so a text part with WORDS is a song with vocals, refused here.

Every kept track is cut of its leading and trailing silence, loudness-normalised
in two passes (linear, so its dynamics survive) and faded out, so no track jumps
out of another and every one ends cleanly into the next.

Run inside the API container, where the provider key and ffmpeg live:

    MSYS_NO_PATHCONV=1 docker cp scripts/assets/generate_radio_music.py lia-api-dev:/tmp/
    MSYS_NO_PATHCONV=1 docker exec -w /app -e PYTHONPATH=/app lia-api-dev \\
        python /tmp/generate_radio_music.py /tmp/radio_music
    MSYS_NO_PATHCONV=1 docker cp lia-api-dev:/tmp/radio_music/audio/. apps/web/public/radio/music/
    MSYS_NO_PATHCONV=1 docker cp lia-api-dev:/tmp/radio_music/music-library.json apps/web/src/data/radio/
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import get_db_context

MODEL = "lyria-3.5"
BASE = "https://generativelanguage.googleapis.com/v1beta"
#: The published price of one song (Gemini API pricing, read 2026-09-26).
PRICE_USD = 0.08
#: Generations allowed in one run, refusals included: the budget the owner granted
#: (5 EUR) at the published price, one measurement song already spent.
MAX_GENERATIONS = 62
CONCURRENCY = 3
MIN_SECONDS = 90.0
LOUDNESS = "I=-18:TP=-1.5:LRA=11"
FADE_OUT_SECONDS = 3.0
BITRATE = "128k"

_SUFFIX = (
    " About two minutes long. Structure: a short intro, a long steady body with subtle"
    " variations, a gentle outro that resolves. Understated melody that leaves room for a"
    " speaking voice; broadcast-quality, balanced mix. Instrumental only, no vocals, no"
    " choir, no humming, no spoken words."
)

#: A dozen distinct beds per mood — the keys must match ``MusicMood`` (backend).
MOODS: dict[str, tuple[str, ...]] = {
    "morning": (
        "Bright acoustic pop radio bed: strummed acoustic guitar, handclaps, glockenspiel accents, warm bass, 112 BPM, G major, sunny and optimistic.",
        "Light funk morning groove: clean muted electric guitar, round bass, crisp hi-hats, Rhodes chords, 108 BPM, E major, upbeat and friendly.",
        "Uplifting indie folk: fingerpicked guitar, ukulele, soft kick and shaker, light piano, 116 BPM, D major, fresh morning energy.",
        "Feel-good electronic pop: plucky synths, soft four-on-the-floor kick, airy pads, 120 BPM, A major, bright and positive.",
        "Sunny bossa-pop: nylon guitar, light brushes, round bass, soft flute-like pads, 104 BPM, F major, relaxed but cheerful.",
        "Piano pop morning: bouncy piano chords, claps, soft synth bass, tambourine, 110 BPM, C major, hopeful and clean.",
        "Light tropical house: marimba-like plucks, soft kick, warm bass, airy chords, 112 BPM, B-flat major, breezy.",
        "Light orchestral morning: pizzicato strings, soft woodwinds, light percussion, 100 BPM, D major, a gentle awakening that builds a little.",
        "Retro soul morning: warm organ, clean guitar licks, laid-back drums, round bass, 98 BPM, E-flat major, feel-good.",
        "Acoustic chill-hop brunch: mellow guitar loop, soft drums, warm bass, light keys, 92 BPM, A major, easygoing.",
        "Warm acoustic anthem, restrained: strummed guitars, piano, light drums, 118 BPM, G major, confident and warm, never cheesy.",
        "Light nu-disco: filtered guitar, smooth bass line, soft disco hi-hats, string pads, 114 BPM, A major, danceable but restrained.",
    ),
    "news": (
        "Modern radio news underscore: pulsing muted synth arpeggio, warm sub bass, crisp light percussion, 104 BPM, D minor, neutral and focused.",
        "Newsroom bed: ticking hi-hat pattern, deep synth pulses, sparse piano notes, 110 BPM, A minor, serious but calm.",
        "Documentary news bed: staccato strings, soft low drum hits, steady pulse, 96 BPM, E minor, measured and authoritative.",
        "Technology news underscore: glassy synth plucks, minimal electronic beat, soft bass, 118 BPM, C minor, forward-moving and clean.",
        "Minimal electronic news bed: quiet steady kick, sidechained pads, subtle arpeggio, 122 BPM, F minor, alert and neutral.",
        "World news bed: piano ostinato, cello drone, light percussion, 100 BPM, G minor, global and sober.",
        "Business news underscore: muted guitar ostinato, electronic percussion, warm synth chords, 112 BPM, B minor, confident and neutral.",
        "Investigative news bed: dark ambient pads, heartbeat-like soft kick, sparse metallic textures, 90 BPM, C-sharp minor, suspense without drama.",
        "Restrained headline bed: driving eighth-note synth bass, crisp rim clicks, 124 BPM, D minor, urgent but never alarming.",
        "Analytical news bed: soft Rhodes chords, gentle electronic beat, subtle arpeggios, 98 BPM, E-flat minor, thoughtful.",
        "Hybrid orchestral news bed: pizzicato and synth pulses, soft brass pads, 108 BPM, A minor, steady and informative.",
        "Clean modern news bed: light percussion, bell-like plucks, warm pads, 116 BPM, F major, neutral and contemporary.",
    ),
    "evening": (
        "Smooth evening jazz: brushed drums, gently walking upright bass, warm Rhodes, soft muted-brass pads without a lead solo, 84 BPM, B-flat major.",
        "Neo-soul evening groove: laid-back drums, warm bass, electric piano chords, subtle guitar, 78 BPM, D-flat major, intimate.",
        "Downtempo lounge: deep bass, soft kick, airy pads, gentle guitar textures, 92 BPM, F minor, relaxed and elegant.",
        "Late-night lo-fi: dusty drums, mellow piano chords, warm bass, soft vinyl ambience, 80 BPM, E-flat major, cosy.",
        "Cinematic evening: soft strings, felt piano, gentle pulse, 72 BPM, A-flat major, reflective and warm.",
        "Evening bossa nova: nylon guitar, soft brushes, round bass, light flute-like pad, 88 BPM, D major, calm and sophisticated.",
        "Chill house evening: soft four-on-the-floor, warm chords, deep bass, 100 BPM, G minor, smooth city night.",
        "Acoustic evening: warm fingerpicked guitar, cello, soft percussion, 76 BPM, C major, homely and gentle.",
        "Light trip-hop: slow breakbeat, warm bass, dusty keys, subtle strings, 86 BPM, A minor, mellow and moody.",
        "Soul-jazz lounge: organ pads, soft drums, round bass, clean guitar, 90 BPM, F major, warm.",
        "Ambient electronic sunset: evolving pads, soft arpeggio, gentle beat, 94 BPM, E major, dreamy.",
        "Evening piano trio: piano, brushed drums, upright bass, 82 BPM, G major, relaxed and elegant, no virtuoso solos.",
    ),
    "calm": (
        "Ambient piano: soft felt piano, warm pads, gentle reverb, 66 BPM, C major, peaceful.",
        "Calm lo-fi: soft drums, mellow guitar, warm keys, 72 BPM, A minor, soothing.",
        "Ambient textures: slowly evolving synth pads, soft bells, no drums, 60 BPM, D major, serene.",
        "Acoustic calm: fingerpicked guitar, soft strings, 70 BPM, E major, gentle.",
        "Chill electronic: soft plucks, airy pads, light beat, 80 BPM, F major, relaxed focus.",
        "Minimal piano and cello: sparse piano, sustained cello, 64 BPM, B minor, contemplative.",
        "Soft jazz ballad: brushed drums, bass, piano, 68 BPM, D-flat major, tender.",
        "Restful ambient: soft pads, gentle marimba, subtle rain texture, 74 BPM, G major, restful.",
        "Downtempo chillout: warm bass, soft percussion, electric piano, 84 BPM, C minor, smooth.",
        "Harp and pads: soft harp arpeggios, warm synth pads, 62 BPM, A major, calm and luminous.",
        "Lo-fi study beat: dusty drums, soft piano, warm bass, 76 BPM, F minor, focused calm.",
        "Light post-rock: clean reverberant guitars, soft pads, gentle drums, 82 BPM, E major, spacious.",
    ),
}

#: Lyria's section markers (``[[A0]]``) — what its text part holds when nothing is sung.
_SECTION_MARKER = re.compile(r"\[\[[^\]]*\]\]")


@dataclass
class Budget:
    """Generations spent in this run, refusals included."""

    spent: int = 0

    def take(self) -> bool:
        if self.spent >= MAX_GENERATIONS:
            return False
        self.spent += 1
        return True


def sings(texts: list[str]) -> bool:
    """Whether Lyria's text part carries words — lyrics, so a song with vocals."""
    return any(re.search(r"[^\W\d_]", _SECTION_MARKER.sub("", text)) for text in texts)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _duration(path: Path) -> float:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return round(float(probe.stdout.strip()), 3)


#: Leading and trailing silence off (the trailing one by reversing the signal).
_TRIM = (
    "silenceremove=start_periods=1:start_threshold=-60dB,areverse,"
    "silenceremove=start_periods=1:start_threshold=-60dB,areverse"
)


def _measure(wav: Path) -> dict[str, str]:
    """The first loudnorm pass: what the track measures (the second applies it linearly)."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav),
         "-af", f"loudnorm={LOUDNESS}:print_format=json", "-f", "null", "-"],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    start = result.stderr.rindex("{")
    measured = json.loads(result.stderr[start : result.stderr.index("}", start) + 1])
    return {key: str(value) for key, value in measured.items()}


def _finish(raw: Path, out: Path) -> dict[str, object]:
    """Trim the silences (lossless), normalise in two passes, fade, encode ONCE."""
    raw_duration = _duration(raw)
    wav = out.with_suffix(".trimmed.wav")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", _TRIM, "-ar", "44100", "-ac", "2", str(wav)],
        check=True,
    )  # fmt: skip
    measured = _measure(wav)
    fade_start = max(0.0, _duration(wav) - FADE_OUT_SECONDS)
    chain = (
        f"loudnorm={LOUDNESS}:linear=true"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']},"
        f"afade=t=in:d=0.3,afade=t=out:st={fade_start}:d={FADE_OUT_SECONDS}"
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-af", chain,
         "-ar", "44100", "-ac", "2", "-codec:a", "libmp3lame", "-b:a", BITRATE, str(out)],
        check=True,
    )  # fmt: skip
    wav.unlink()
    return {"raw_duration_seconds": raw_duration, "input_lufs": float(measured["input_i"])}


async def _generate(client: httpx.AsyncClient, prompt: str) -> tuple[bytes, list[str]] | None:
    response = await client.post(f"{BASE}/interactions", json={"model": MODEL, "input": prompt})
    if response.status_code >= 400:
        print("refused:", response.status_code, (response.json().get("error") or {}).get("code"))
        return None
    audio, texts = b"", []
    for step in response.json().get("steps") or []:
        for part in step.get("content") or []:
            if part.get("type") == "audio" and not audio:
                audio = base64.b64decode(part.get("data", ""))
            elif part.get("type") == "text":
                texts.append(str(part.get("text", "")))
    return (audio, texts) if audio else None


async def _one(
    client: httpx.AsyncClient,
    gate: asyncio.Semaphore,
    budget: Budget,
    out_dir: Path,
    mood: str,
    index: int,
    prompt: str,
) -> dict[str, object] | None:
    name = f"{mood}-{index:02d}.mp3"
    final = out_dir / "audio" / mood / name
    full_prompt = prompt + _SUFFIX
    for attempt in (1, 2):
        async with gate:
            if not budget.take():
                print(name, "budget spent")
                return None
            generated = await _generate(client, full_prompt)
        if generated is None:
            continue
        audio, texts = generated
        raw = final.with_suffix(".raw.mp3")
        raw.write_bytes(audio)
        reason = "sings" if sings(texts) else "too short" if _duration(raw) < MIN_SECONDS else None
        if reason is not None:
            print(name, "refused on attempt", attempt, f"({reason})")
            raw.unlink()
            continue
        facts = await asyncio.to_thread(_finish, raw, final)
        record = {
            "file": f"{mood}/{name}",
            "mood": mood,
            "prompt": full_prompt,
            "sections": texts,
            "raw_sha256": _sha256(audio),
            "sha256": _sha256(final.read_bytes()),
            "duration_seconds": _duration(final),
            **facts,
        }
        raw.unlink()
        print(name, record["duration_seconds"], "s", record["input_lufs"], "LUFS in")
        return record
    return None


async def main(out_dir: Path) -> None:
    import_all_models()
    async with get_db_context() as db:
        await LLMConfigOverrideCache.load_from_db(db)
    key = LLMConfigOverrideCache.get_api_key("gemini")
    if not key:
        sys.exit("no gemini key configured")
    for mood in MOODS:
        (out_dir / "audio" / mood).mkdir(parents=True, exist_ok=True)
    previous = out_dir / "audio" / "PROVENANCE.json"
    tracks: dict[str, dict[str, object]] = (
        json.loads(previous.read_text(encoding="utf-8")).get("tracks", {}) if previous.exists() else {}
    )
    budget, gate = Budget(), asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=600, headers={"x-goog-api-key": key}) as client:
        jobs = [
            _one(client, gate, budget, out_dir, mood, index, prompt)
            for mood, prompts in MOODS.items()
            for index, prompt in enumerate(prompts, start=1)
            if f"{mood}/{mood}-{index:02d}.mp3" not in tracks
            or not (out_dir / "audio" / mood / f"{mood}-{index:02d}.mp3").exists()
        ]
        for record in await asyncio.gather(*jobs):
            if record is not None:
                tracks[str(record["file"])] = record
    provenance = {
        "generator": "scripts/assets/generate_radio_music.py",
        "model": MODEL,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "processing": f"silence trimmed, two-pass linear loudnorm {LOUDNESS}, fade-out {FADE_OUT_SECONDS}s, stereo 44.1 kHz MP3 {BITRATE}",
        "rights": "Generated for LIA by the project with Lyria (SynthID watermark); no third-party work is included.",
        "spent_this_run_usd": round(budget.spent * PRICE_USD, 2),
        "tracks": dict(sorted(tracks.items())),
    }
    previous.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    library = {
        mood: [
            {"file": f"/radio/music/{record['file']}", "duration_s": record["duration_seconds"]}
            for _file, record in sorted(tracks.items())
            if record["mood"] == mood
        ]
        for mood in MOODS
    }
    (out_dir / "music-library.json").write_text(
        json.dumps({"moods": library}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("kept:", {mood: len(entries) for mood, entries in library.items()}, "spent:", budget.spent)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/radio_music")))
