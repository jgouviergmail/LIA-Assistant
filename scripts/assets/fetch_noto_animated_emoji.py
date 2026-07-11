#!/usr/bin/env python3
"""Fetch the Noto Animated Emoji WebP assets used by the frontend.

One-shot developer utility (not part of the runtime):
- downloads the animated 512px WebP for every mood codepoint used by
  ``apps/web/src/lib/psyche-colors.ts`` (psyche avatar) and, best-effort, for
  the seeded personality emojis (header selector);
- fails loudly (exit 1) if any MOOD codepoint is missing from the Noto
  distribution; missing PERSONALITY animations are only reported (the UI
  falls back to the static glyph at runtime);
- ships the ORIGINAL Google encode by default: a Pillow re-encode (``--size``)
  halves the weight but flattens the variable per-frame timings, which makes
  the animations visibly choppy in the app (UAT 2026-07-11). Use ``--size``
  only if that regression is ever fixed and re-verified.

Assets are licensed CC BY 4.0 (Noto Animated Emoji, Google) — the LICENSE file
in the output directory carries the attribution and must ship with the assets.

Usage (from repo root):
    apps/api/.venv/Scripts/python scripts/assets/fetch_noto_animated_emoji.py [--size 128]
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
from pathlib import Path

# Mood -> codepoint mapping. MUST mirror MOOD_COLORS in
# apps/web/src/lib/psyche-colors.ts; the vitest asset-presence test
# (psyche-colors.test.ts) is the completeness guard on the frontend side.
MOOD_CODEPOINTS: dict[str, str] = {
    "serene": "1f60c",
    "curious": "1f9d0",
    "energized": "1f601",
    "playful": "1f61c",
    "reflective": "1f914",
    "agitated": "1f61f",
    "melancholic": "1f61e",
    "neutral": "1f610",
    "content": "1f60a",
    "determined": "1f624",
    "defiant": "1f620",
    "resigned": "1f614",
    "overwhelmed": "1f635",
    "tender": "1f970",
}

# Personality emojis (seeded set) — best-effort: personalities are DB-managed
# (infrastructure/database/seeds/personalities_seed.sql), an emoji without an
# animated Noto version simply keeps its static glyph at runtime
# (AnimatedEmoji onError fallback). Multi-codepoint sequences use '-' in
# filenames ('_' in the gstatic URL), matching emojiToCodepoint() derivation.
PERSONALITY_EMOJIS: dict[str, str] = {
    "cynic": "1f60f",
    "normal": "2696-fe0f",
    "depressed": "1f636",
    "enthusiastic": "1f389",
    "friend": "1f91d",
    "philosopher": "1f914",
    "influencer": "2728",
    "professor": "1f393",
    "rasta": "1f334",
    "teenager": "1f480",
    "jarvis": "269b-fe0f",
    "haipai": "1f95f",
    "trump": "1f4b0",
    "antagonist": "1f9d0",
}

# UI emojis (best-effort): decorative animated glyphs used by the frontend
# outside psyche/personalities (e.g. the empty-chat greeting).
UI_EMOJIS: dict[str, str] = {
    "wave": "1f44b",
    "coffee": "2615",
    "moon_face": "1f31b",
    "sleeping_face": "1f634",
}

BASE_URL = "https://fonts.gstatic.com/s/e/notoemoji/latest/{codepoint}/512.webp"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "apps" / "web" / "public" / "animated-emoji"


def fetch(codepoint: str) -> bytes:
    """Download one animated WebP; raises on any HTTP/network failure.

    Args:
        codepoint: Lowercase hex Unicode codepoint (e.g. ``"1f60a"``).

    Returns:
        Raw WebP bytes as served by the Noto distribution.

    Raises:
        RuntimeError: If the server answers with a non-200 status.
        urllib.error.URLError: On network failures or HTTP errors (404, ...).
    """
    url = BASE_URL.format(codepoint=codepoint.replace("-", "_"))
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - fixed https host
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        return resp.read()


def resize_animated_webp(data: bytes, size: int) -> bytes | None:
    """Resize every frame of an animated WebP.

    Args:
        data: Source animated WebP bytes.
        size: Target square size in pixels.

    Returns:
        Re-encoded WebP bytes, or None when Pillow (or its animated-WebP
        support) is unavailable or the input is not animated — callers then
        keep the original bytes.
    """
    try:
        from PIL import Image, ImageSequence
    except ImportError:
        return None
    im = Image.open(io.BytesIO(data))
    if getattr(im, "n_frames", 1) <= 1:
        return None
    frames: list = []
    durations: list[int] = []
    for frame in ImageSequence.Iterator(im):
        durations.append(int(frame.info.get("duration", 40)))
        frames.append(frame.convert("RGBA").resize((size, size), Image.LANCZOS))
    out = io.BytesIO()
    frames[0].save(
        out,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        quality=80,
        method=6,
    )
    return out.getvalue()


def main() -> int:
    """Fetch, optionally resize, and store all mood assets; report failures.

    Returns:
        Process exit code: 0 on full success, 1 when any codepoint is missing.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--size",
        type=int,
        default=0,
        help="Target square size (0 = keep the fluid 512px originals; see module docstring)",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for mood, codepoint in sorted(MOOD_CODEPOINTS.items()):
        try:
            data = fetch(codepoint)
        except Exception as exc:  # noqa: BLE001 - collect every failure, then exit non-zero
            failures.append(f"{mood} ({codepoint}): {exc}")
            continue
        if args.size:
            resized = resize_animated_webp(data, args.size)
            if resized is None:
                print(f"WARN {mood}: animated resize unavailable, keeping 512px original")
            elif len(resized) < len(data):
                data = resized
        target = OUTPUT_DIR / f"{codepoint}.webp"
        target.write_bytes(data)
        print(f"OK   {mood:<12} -> {target.name} ({len(data) / 1024:.0f} KB)")

    for name, codepoint in sorted({**PERSONALITY_EMOJIS, **UI_EMOJIS}.items()):
        target = OUTPUT_DIR / f"{codepoint}.webp"
        if target.exists():
            print(f"SKIP {name:<12} -> {target.name} (already fetched)")
            continue
        try:
            data = fetch(codepoint)
        except Exception:  # noqa: BLE001 - best-effort: static glyph at runtime
            print(f"MISS {name:<12} ({codepoint}) - no animated version, static glyph at runtime")
            continue
        if args.size:
            resized = resize_animated_webp(data, args.size)
            if resized is not None and len(resized) < len(data):
                data = resized
        target.write_bytes(data)
        print(f"OK   {name:<12} -> {target.name} ({len(data) / 1024:.0f} KB)")

    if failures:
        print("\nMISSING CODEPOINTS - pick substitute emojis before continuing:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1
    if not (OUTPUT_DIR / "LICENSE").exists():
        print("\nREMINDER: write LICENSE (attribution) in the output dir before shipping.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
