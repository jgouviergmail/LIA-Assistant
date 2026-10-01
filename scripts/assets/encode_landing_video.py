#!/usr/bin/env python3
"""Encode the landing video, its poster, its beat map and its manifest (ADR-330).

One-shot developer utility, not part of the runtime. From ONE master file it
writes the directory the web server reads through ``LANDING_MEDIA_BASE_URL``:

- four renditions, two sizes × two codecs — AV1 for every browser that decodes
  it, H.264 for the rest (Safari before the A17/M3 hardware, older phones) —
  each named after the master's content hash, so a replaced video is a new
  URL and a year-long immutable cache is safe;
- the poster, the first frame as WebP;
- the beat map: ``[ms, weight, bar]`` triples from an offline analysis of the
  soundtrack (spectral-flux onsets, a tempo per window, dynamic-programming
  beat tracking, each beat snapped to its onset and corrected for the
  analysis window's lead, the bar phase voted locally), read by the page when
  the sound is switched on and driven from the presented frame's clock;
- ``manifest.json``, the file the page actually reads (``apps/web/src/lib/
  landing/media.ts`` is its schema), and ``PROVENANCE.json`` — source hash,
  encoder lines, sizes, credit, date.

The CRF values were chosen on the first video shipped (dithered, high-
frequency content: VMAF 83 at 3.9 Mbit/s for AV1 1080p against the master,
85 at 5.8 Mbit/s for H.264; 720p loses the dither whatever the bitrate, so
it is offered to phones only, under ``minWidth``). Re-measure before changing
them for another video.

Usage (from the repository root, ffmpeg and ffprobe on PATH, numpy in the API
venv):

    apps/api/.venv/Scripts/python scripts/assets/encode_landing_video.py \\
        --source exports/Underclass.mp4 --out exports/landing-media \\
        --name underclass --credit-label @anabology \\
        --credit-url https://x.com/anabology --ai-generated

``--skip-renditions`` writes everything but the four videos (to iterate on the
beat map); an existing rendition of the same hash is kept unless ``--force``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

AUDIO_RATE = 22_050
AUDIO_ARGS = ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
# The spectral flux of a transient peaks while it ENTERS the analysis window, so
# an onset is reported early by a fixed amount for a given window and hop.
# Calibrated 2026-10-01 on a synthetic click track (a 60 Hz thump plus a hat at
# 132 BPM, an odd start) through these very functions: detected − true =
# −72.9 ms, standard deviation 0.5 ms over 86 beats. Added back here, so a
# title pulses WITH the drum, not three frames before it.
ONSET_LEAD_MS = 72.9
# The beat map is named after the master's hash AND this number, because the
# map changes when the ANALYSIS changes, master untouched — and every file under
# the media directory is served immutable for a year. Bump it with any change
# to the functions below; the schema version inside the file is another thing
# (``apps/web/src/lib/landing/beats-schema.ts``). History: 1 — first analysis;
# 2 — ``ONSET_LEAD_MS`` and a sharper tracker (``alpha`` 8), 2026-10-01.
BEAT_ANALYSIS_VERSION = 2
# The bar phase is voted LOCALLY, over this many beats on each side (8 bars).
# A global `i % 4` was measured wrong on the shipped video (2026-10-01): the
# tracker inserts or drops a beat in a breakdown, so the count from the start
# accented phase 0 for 55 s, then phase 3 to 253 s, then phase 0 again — a real
# accent (margins up to 64 % on the low band), moved by the tracker's own
# seams. Three refusals keep the vote honest: under the margin the low band
# says nothing (a four-on-the-floor kick is even); under the floor — a share
# of the track's median low strength — nobody is playing the bar (a sparse
# breakdown made the argmax wander, 15 pairs of bars one beat apart); and two
# bars never open within a gap no music writes.
BAR_VOTE_RADIUS_BEATS = 16
BAR_VOTE_MIN_MARGIN = 0.10
BAR_VOTE_FLOOR_SHARE = 0.25
BAR_MIN_GAP_BEATS = 3
POSTER_WIDTH = 1600
POSTER_QUALITY = 78
DESKTOP_MIN_WIDTH = 900


@dataclass(frozen=True)
class Rendition:
    """One encoded variant of the master."""

    label: str
    codec: str
    height: int
    min_width: int | None
    video_args: tuple[str, ...]

    def file_name(self, name: str, digest: str) -> str:
        return f"{name}-{digest}-{self.label}.{self.codec}.mp4"


RENDITIONS: tuple[Rendition, ...] = (
    Rendition(
        "1080p",
        "av1",
        1080,
        DESKTOP_MIN_WIDTH,
        ("-c:v", "libsvtav1", "-preset", "6", "-crf", "48", "-g", "240", "-pix_fmt", "yuv420p10le"),
    ),
    Rendition(
        "1080p",
        "h264",
        1080,
        DESKTOP_MIN_WIDTH,
        ("-c:v", "libx264", "-preset", "slow", "-crf", "29", "-profile:v", "high", "-g", "240", "-pix_fmt", "yuv420p"),
    ),
    Rendition(
        "720p",
        "av1",
        720,
        None,
        ("-c:v", "libsvtav1", "-preset", "6", "-crf", "42", "-g", "240", "-pix_fmt", "yuv420p10le"),
    ),
    Rendition(
        "720p",
        "h264",
        720,
        None,
        ("-c:v", "libx264", "-preset", "slow", "-crf", "27", "-profile:v", "high", "-g", "240", "-pix_fmt", "yuv420p"),
    ),
)

H264_PROFILE_IDC = {"Baseline": 0x42, "Constrained Baseline": 0x42, "Main": 0x4D, "High": 0x64, "High 10": 0x6E}


def run(args: list[str], *, capture: bool = False) -> str:
    """Run a command, failing loudly; return its stdout when captured."""
    result = subprocess.run(args, check=True, capture_output=capture, text=True)
    return result.stdout if capture else ""


def ffprobe(path: Path, *entries: str) -> dict:
    """``entries`` are ffprobe sections (``stream=…``, ``format=…``), joined with ``:``."""
    out = run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", ":".join(entries), "-of", "json", str(path)],
        capture=True,
    )
    return json.loads(out)


def source_facts(path: Path) -> dict:
    data = ffprobe(path, "stream=width,height,r_frame_rate,codec_name", "format=duration,size")
    stream = data["streams"][0]
    num, den = stream["r_frame_rate"].split("/")
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": int(num) / int(den),
        "codec": stream["codec_name"],
        "duration": float(data["format"]["duration"]),
        "size": int(data["format"]["size"]),
    }


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def av1_level(width: int, height: int, fps: float) -> int:
    """seq_level_idx for a stream, when ffprobe does not report it."""
    pixels = width * height
    rate = pixels * fps
    for idx, max_pixels, max_rate in ((5, 983_040, 29_491_200), (8, 2_228_224, 66_846_720), (9, 2_228_224, 133_693_440), (12, 8_912_896, 267_386_880)):
        if pixels <= max_pixels and rate <= max_rate:
            return idx
    return 13


def codecs_string(path: Path, codec: str) -> str:
    """The RFC 6381 ``codecs`` value browsers negotiate on, read from the file."""
    data = ffprobe(path, "stream=codec_name,profile,level,pix_fmt,width,height,r_frame_rate")
    stream = data["streams"][0]
    if codec == "h264":
        profile_idc = H264_PROFILE_IDC[stream["profile"]]
        return f'video/mp4; codecs="avc1.{profile_idc:02X}00{int(stream["level"]):02X}"'
    level = int(stream.get("level", -99))
    if level < 0:
        num, den = stream["r_frame_rate"].split("/")
        level = av1_level(int(stream["width"]), int(stream["height"]), int(num) / int(den))
    depth = 10 if "10" in stream["pix_fmt"] else 8
    return f'video/mp4; codecs="av01.0.{level:02d}M.{depth:02d}"'


def encode_rendition(source: Path, out: Path, rendition: Rendition) -> None:
    run(
        [
            "ffmpeg", "-v", "error", "-y", "-i", str(source),
            "-vf", f"scale=-2:{rendition.height}",
            *rendition.video_args,
            *AUDIO_ARGS,
            "-movflags", "+faststart",
            str(out),
        ]
    )


def write_poster(source: Path, out: Path) -> None:
    run(
        [
            "ffmpeg", "-v", "error", "-y", "-i", str(source), "-frames:v", "1",
            "-vf", f"scale={POSTER_WIDTH}:-2", "-c:v", "libwebp", "-quality", str(POSTER_QUALITY), str(out),
        ]
    )


# ---------------------------------------------------------------------------
# Beat map
# ---------------------------------------------------------------------------


def decode_audio(source: Path):
    """The soundtrack as mono float32 at AUDIO_RATE."""
    import numpy as np

    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", str(AUDIO_RATE), "-f", "f32le", "-"],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32)


def onset_envelope(samples, n_fft: int = 2048, hop: int = 256):
    """Spectral flux over 40 log-spaced bands (half-wave rectified, lightly smoothed)."""
    import numpy as np

    window = np.hanning(n_fft).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(samples, n_fft)[::hop] * window
    magnitude = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(n_fft, 1 / AUDIO_RATE)
    edges = np.geomspace(60, 8000, 41)
    bands = np.stack([magnitude[:, (freqs >= lo) & (freqs < hi)].sum(axis=1) for lo, hi in zip(edges[:-1], edges[1:], strict=True)], axis=1)
    log_bands = np.log1p(bands * 10)
    flux = np.maximum(np.diff(log_bands, axis=0, prepend=log_bands[:1]), 0).sum(axis=1)
    low_flux = np.maximum(np.diff(log_bands[:, :8], axis=0, prepend=log_bands[:1, :8]), 0).sum(axis=1)
    kernel = np.array([0.25, 0.5, 0.25])
    flux = np.convolve(flux, kernel, mode="same")
    scale = np.percentile(flux, 95) or 1.0
    return flux / scale, low_flux, AUDIO_RATE / hop


def tempo_by_window(env, fps: float, window_s: float = 10.0, hop_s: float = 5.0, lo_bpm: int = 60, hi_bpm: int = 180):
    """A tempo estimate per window (autocorrelation peak), as (start_frame, bpm)."""
    import numpy as np

    out = []
    w = int(window_s * fps)
    h = int(hop_s * fps)
    min_lag = int(fps * 60 / hi_bpm)
    max_lag = int(fps * 60 / lo_bpm)
    for start in range(0, max(1, len(env) - w // 2), h):
        seg = env[start : start + w]
        if len(seg) < w // 2:
            break
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, "full")[len(seg) - 1 :]
        lag = min_lag + int(np.argmax(ac[min_lag : max_lag + 1]))
        out.append((start, 60 * fps / lag))
    # A tempo prior: a quiet window (an intro, a breakdown) answers an octave
    # of the piece's tempo, or noise. Fold octaves onto the median tempo and
    # fall back to it when a window is more than 8 % away — the tracker keeps
    # the freedom to drift beat by beat, the windows only set its period.
    median = float(np.median([bpm for _, bpm in out]))
    folded = []
    for start, bpm in out:
        while bpm < 0.75 * median:
            bpm *= 2
        while bpm > 1.5 * median:
            bpm /= 2
        folded.append((start, bpm if abs(bpm / median - 1) <= 0.08 else median))
    return folded


def track_beats(env, fps: float, tempos, alpha: float = 8.0):
    """Dynamic-programming beat tracking (Ellis 2007) with a per-window period.

    ``alpha`` weighs the cost of straying from the period against an onset's
    strength: at 4, a loud off-beat hat between two beats was taken twice in
    40 s of a synthetic track; at 8, never (calibration 2026-10-01).
    """
    import numpy as np

    n = len(env)
    period = np.empty(n)
    for i, (start, bpm) in enumerate(tempos):
        end = tempos[i + 1][0] if i + 1 < len(tempos) else n
        period[start:end] = 60 * fps / bpm
    period[: tempos[0][0]] = period[tempos[0][0]]
    score = np.full(n, -np.inf)
    back = np.full(n, -1, dtype=np.int64)
    for t in range(n):
        p = period[t]
        lo = max(0, int(round(t - 2 * p)))
        hi = int(round(t - p / 2))
        best = env[t]
        best_prev = -1
        if hi >= 0:
            candidates = np.arange(lo, hi + 1)
            if len(candidates):
                penalty = alpha * (np.log((t - candidates) / p)) ** 2
                values = score[candidates] - penalty
                k = int(np.argmax(values))
                if values[k] > -np.inf:
                    best = env[t] + values[k]
                    best_prev = int(candidates[k])
        score[t] = best
        back[t] = best_prev
    last = int(np.argmax(score[int(n - period[-1]) :]) + int(n - period[-1]))
    beats = []
    t = last
    while t >= 0:
        beats.append(t)
        t = back[t]
    return beats[::-1]


def bar_flags(
    lows: list[float],
    radius: int = BAR_VOTE_RADIUS_BEATS,
    min_margin: float = BAR_VOTE_MIN_MARGIN,
    floor_share: float = BAR_VOTE_FLOOR_SHARE,
    min_gap: int = BAR_MIN_GAP_BEATS,
) -> list[bool]:
    """Which beats open a bar, each decided by the beats around it.

    For beat ``i``, the low-band onset strengths of the beats within ``radius``
    are averaged by their distance to ``i`` modulo 4 (averaged, not summed: at
    the ends of the piece the four classes hold unequal counts); ``i`` opens a
    bar when its own class leads the runner-up by at least ``min_margin``, its
    mean reaches ``floor_share`` of the median strength of the whole piece,
    and the previous bar is at least ``min_gap`` beats back. The vote follows
    the music through a beat the tracker inserted or dropped, where a count
    from the start would accent the wrong beat for the rest of the piece, and
    it carries the grid a few bars into a breakdown by inertia; an even pulse,
    a tie or a passage where nobody plays the bar opens no bar at all.

    Args:
        lows: One low-band onset strength per beat, in order.
        radius: Beats taken on each side of the one decided.
        min_margin: The winner's lead over the runner-up, as a fraction, below
            which no bar is marked.
        floor_share: The share of the piece's median strength a winning class
            must reach.
        min_gap: The fewest beats between two bars.

    Returns:
        One flag per beat.
    """
    n = len(lows)
    if n == 0:
        return []
    floor = floor_share * sorted(lows)[n // 2]
    flags = [False] * n
    last = -min_gap
    for i in range(n):
        totals = [0.0] * 4
        counts = [0] * 4
        for j in range(max(0, i - radius), min(n, i + radius + 1)):
            klass = (j - i) % 4
            totals[klass] += lows[j]
            counts[klass] += 1
        means = [total / count if count else 0.0 for total, count in zip(totals, counts, strict=True)]
        own, runner_up = means[0], max(means[1:])
        if own < floor or own <= runner_up or i - last < min_gap:
            continue
        if runner_up > 0 and own / runner_up - 1 < min_margin:
            continue
        flags[i] = True
        last = i
    return flags


def snap_and_weight(beats, env, low_env, fps: float, radius_ms: float = 30.0):
    """Snap each beat to the strongest onset nearby (parabolic refinement), weight it, mark bars."""
    import numpy as np

    radius = max(1, int(round(radius_ms * fps / 1000)))
    snapped = []
    for b in beats:
        lo, hi = max(0, b - radius), min(len(env) - 1, b + radius)
        k = lo + int(np.argmax(env[lo : hi + 1]))
        offset = 0.0
        if 0 < k < len(env) - 1:
            y0, y1, y2 = env[k - 1], env[k], env[k + 1]
            denom = y0 - 2 * y1 + y2
            if denom < 0:
                offset = 0.5 * (y0 - y2) / denom
        snapped.append((k + offset, float(env[k]), float(low_env[k])))
    strengths = np.array([s for _, s, _ in snapped])
    scale = np.percentile(strengths, 95) or 1.0
    weights = np.clip(strengths / scale, 0, 1)
    bars = bar_flags([low for _, _, low in snapped])
    result = []
    for (frame, _, _), weight, bar in zip(snapped, weights, bars, strict=True):
        ms = int(round(frame * 1000 / fps + ONSET_LEAD_MS))
        if result and ms <= result[-1][0]:
            continue
        result.append([ms, round(float(weight), 2), bar])
    return result


def beat_map(source: Path) -> tuple[list, dict]:
    env, low_env, fps = onset_envelope(decode_audio(source))
    tempos = tempo_by_window(env, fps)
    beats = track_beats(env, fps, tempos)
    entries = snap_and_weight(beats, env, low_env, fps)
    import numpy as np

    intervals = np.diff([e[0] for e in entries]) if len(entries) > 1 else np.array([0])
    # How many beats sit on an onset stronger than the envelope around them
    # (±1 s): a tracker that drifts off the drums scores low here. Read in the
    # ANALYSIS domain — the published instant carries ONSET_LEAD_MS, the
    # envelope does not (read on the published instant it answered 9 % for a
    # map that was right).
    radius = int(fps)
    hits = 0
    for ms, _, _ in entries:
        k = min(len(env) - 1, max(0, int(round((ms - ONSET_LEAD_MS) * fps / 1000))))
        local = env[max(0, k - radius) : k + radius + 1]
        hits += env[k] > np.median(local)
    summary = {
        "beats": len(entries),
        "bars": sum(1 for _, _, bar in entries if bar),
        "tempo_windows": [{"from_s": round(start / fps, 1), "bpm": round(bpm, 1)} for start, bpm in tempos],
        "median_interval_ms": float(np.median(intervals)),
        "interval_mad_ms": float(np.median(np.abs(intervals - np.median(intervals)))),
        "mean_weight": round(float(np.mean([e[1] for e in entries])), 3),
        "onset_hit_rate": round(hits / max(1, len(entries)), 3),
    }
    return entries, summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def aspect_ratio(width: int, height: int) -> list[int]:
    g = math.gcd(width, height)
    return [width // g, height // g]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--name", required=True, help="file name stem, e.g. underclass")
    parser.add_argument("--credit-label", help="the author as shown, e.g. @handle")
    parser.add_argument("--credit-url", help="https link to the author")
    parser.add_argument("--ai-generated", action="store_true")
    parser.add_argument("--skip-renditions", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if bool(args.credit_label) != bool(args.credit_url):
        parser.error("--credit-label and --credit-url go together")
    if args.credit_url and not args.credit_url.startswith("https://"):
        parser.error("--credit-url must be https")

    source: Path = args.source
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    facts = source_facts(source)
    digest = sha256_of(source)
    short = digest[:12]
    print(f"source {source.name}: {facts['width']}x{facts['height']} {facts['fps']:.3g} fps, {facts['duration']:.1f} s, sha256 {short}...")

    provenance_renditions = []
    manifest_renditions = []
    for rendition in RENDITIONS:
        file_name = rendition.file_name(args.name, short)
        target = out / file_name
        if not args.skip_renditions:
            if target.exists() and target.stat().st_size > 0 and not args.force:
                print(f"keep   {file_name}")
            else:
                print(f"encode {file_name} …", flush=True)
                encode_rendition(source, target, rendition)
        if target.exists():
            codecs = codecs_string(target, rendition.codec)
            size = target.stat().st_size
            print(f"       {file_name}: {size / 1_048_576:.1f} MB, {size * 8 / facts['duration'] / 1e6:.2f} Mbit/s, {codecs}")
            entry = {"src": file_name, "type": codecs}
            if rendition.min_width:
                entry["minWidth"] = rendition.min_width
            manifest_renditions.append(entry)
            provenance_renditions.append({
                "file": file_name, "bytes": size, "mbit_s": round(size * 8 / facts["duration"] / 1e6, 2),
                "ffmpeg_video_args": list(rendition.video_args), "codecs": codecs,
            })

    poster_name = f"{args.name}-{short}-poster.webp"
    write_poster(source, out / poster_name)
    print(f"poster {poster_name}: {(out / poster_name).stat().st_size / 1024:.0f} KB")

    beats_name = f"{args.name}-{short}-beats-v{BEAT_ANALYSIS_VERSION}.json"
    entries, summary = beat_map(source)
    (out / beats_name).write_text(json.dumps({"version": 1, "beats": entries}, separators=(",", ":")) + "\n", encoding="utf-8")
    print(
        f"beats  {beats_name}: {summary['beats']} beats, {summary['bars']} bars, median interval "
        f"{summary['median_interval_ms']:.0f} ms (MAD {summary['interval_mad_ms']:.0f}), onset hit rate "
        f"{summary['onset_hit_rate']:.0%}, tempo windows {sorted({w['bpm'] for w in summary['tempo_windows']})}"
    )

    manifest = {
        "version": 1,
        "poster": poster_name,
        "renditions": manifest_renditions,
        "aspectRatio": aspect_ratio(facts["width"], facts["height"]),
        "durationSeconds": round(facts["duration"], 3),
        "beats": beats_name,
        "credit": {"label": args.credit_label, "url": args.credit_url} if args.credit_label else None,
        "aiGenerated": bool(args.ai_generated),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    ffmpeg_version = run(["ffmpeg", "-version"], capture=True).splitlines()[0]
    provenance = {
        "generator": "scripts/assets/encode_landing_video.py",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ffmpeg": ffmpeg_version,
        "source": {"file": source.name, "sha256": digest, "bytes": facts["size"], **{k: facts[k] for k in ("width", "height", "fps", "codec", "duration")}},
        "renditions": provenance_renditions,
        "poster": poster_name,
        "beats": {"file": beats_name, "analysis_version": BEAT_ANALYSIS_VERSION, "onset_lead_ms": ONSET_LEAD_MS, **summary},
        "credit": manifest["credit"],
        "ai_generated": manifest["aiGenerated"],
    }
    (out / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out / 'manifest.json'} and PROVENANCE.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
