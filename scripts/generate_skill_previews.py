#!/usr/bin/env python3
"""Generate the gallery preview image bundled with every system skill.

Each skill's detail modal serves ``assets/preview.png`` and falls back to a
faint icon when it is missing. Every one of the fourteen system skills was
missing it (measured 2026-07-27, in the repository and in production), so the
gallery showed fourteen empty frames.

Design brief
------------
A preview answers one question: *what do I get when I run this?* So each image
is a **schematic fragment of the skill's own output**, not an icon — a calendar
grid for ``calendar-month``, a QR pattern for ``qr-code``, forecast cards for
``weather-dashboard``. The vocabulary is borrowed from what the skills already
render: the slate greys and the indigo accent their ``scripts/*.py`` emit, on
the light surface they draw on. Nothing is invented for decoration.

Two deliberate constraints keep the set reproducible and portable:

- **Geometry only, no font.** Text would be illegible at this size anyway, and
  a font dependency would make the output differ between machines. Where a
  glyph carries meaning it is drawn (the X and O of tic-tac-toe, die pips).
- **No skill name in the image.** The modal already shows it directly above;
  repeating it would be the one element quietly doing double duty.

Shapes are drawn at ``SUPERSAMPLE``× and downscaled with Lanczos, which is what
gives clean edges — Pillow does not antialias primitives.

Usage:
    python scripts/generate_skill_previews.py [--check]

``--check`` regenerates into memory and reports which files are missing or
stale without writing, for CI use.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "data" / "skills" / "system"

# Output geometry. 8:5 suits the modal's `max-h-48 w-full object-contain`.
WIDTH, HEIGHT = 480, 300
SUPERSAMPLE = 4

# Palette lifted from the skills' own renderers (render_month.py,
# render_converter.py, render_dashboard.py) so a preview looks like the thing
# it previews.
SURFACE = "#f1f5f9"  # slate-100 — page behind the artifact
CARD = "#ffffff"
LINE = "#e2e8f0"  # slate-200 — hairlines, inactive fills
MUTED = "#cbd5e1"  # slate-300 — secondary figured text
INK = "#64748b"  # slate-500 — primary figured text
STRONG = "#334155"  # slate-700 — headings, emphasis
ACCENT = "#4f46e5"  # indigo-600 — the one live element per image
ACCENT_SOFT = "#c7d2fe"  # indigo-200


class Canvas:
    """Drawing helper working in final-image coordinates.

    Every primitive multiplies by :data:`SUPERSAMPLE` internally, so callers
    reason in the 480x300 space while Pillow draws four times larger.
    """

    def __init__(self) -> None:
        self.image = Image.new("RGB", (WIDTH * SUPERSAMPLE, HEIGHT * SUPERSAMPLE), SURFACE)
        self.draw = ImageDraw.Draw(self.image)

    def _s(self, value: float) -> float:
        return value * SUPERSAMPLE

    def rect(
        self,
        box: tuple[float, float, float, float],
        fill: str | None = None,
        outline: str | None = None,
        width: float = 1,
        radius: float = 0,
    ) -> None:
        """Draw a (rounded) rectangle from an (x0, y0, x1, y1) box."""
        scaled = tuple(self._s(v) for v in box)
        if radius:
            self.draw.rounded_rectangle(
                scaled,
                radius=self._s(radius),
                fill=fill,
                outline=outline,
                width=int(self._s(width)),
            )
        else:
            self.draw.rectangle(scaled, fill=fill, outline=outline, width=int(self._s(width)))

    def bar(self, x: float, y: float, w: float, h: float, fill: str, radius: float = 2) -> None:
        """Draw a rounded bar — the stand-in for a line of text."""
        self.rect((x, y, x + w, y + h), fill=fill, radius=radius)

    def ellipse(
        self,
        box: tuple[float, float, float, float],
        fill: str | None = None,
        outline: str | None = None,
        width: float = 1,
    ) -> None:
        """Draw an ellipse from an (x0, y0, x1, y1) box."""
        self.draw.ellipse(
            tuple(self._s(v) for v in box),
            fill=fill,
            outline=outline,
            width=int(self._s(width)),
        )

    def line(self, points: list[tuple[float, float]], fill: str, width: float = 2) -> None:
        """Draw a polyline with rounded joints."""
        self.draw.line(
            [(self._s(x), self._s(y)) for x, y in points],
            fill=fill,
            width=int(self._s(width)),
            joint="curve",
        )

    def polygon(self, points: list[tuple[float, float]], fill: str) -> None:
        """Draw a filled polygon."""
        self.draw.polygon([(self._s(x), self._s(y)) for x, y in points], fill=fill)

    def card(self, box: tuple[float, float, float, float], radius: float = 6) -> None:
        """Draw the white surface the artifact sits on."""
        self.rect(box, fill=CARD, outline=LINE, width=1, radius=radius)

    def finish(self) -> Image.Image:
        """Downscale to the final size — this is what antialiases the edges."""
        return self.image.resize((WIDTH, HEIGHT), Image.LANCZOS)


# ---------------------------------------------------------------------------
# One drawing per skill. Each shows the artifact the skill actually produces.
# ---------------------------------------------------------------------------


def briefing_quotidien(c: Canvas) -> None:
    """Stacked day sections, each led by an accent bullet."""
    c.card((40, 28, 440, 272))
    y = 50
    for widths in ((150, 250, 210), (170, 230, 260), (140, 240, 200)):
        c.ellipse((60, y + 1, 70, y + 11), fill=ACCENT)
        c.bar(80, y + 2, widths[0], 8, STRONG)
        y += 24
        for w in widths[1:]:
            c.bar(80, y, w, 6, MUTED)
            y += 14
        y += 12


def calendar_month(c: Canvas) -> None:
    """A month grid with today filled in."""
    c.card((40, 28, 440, 272))
    for i in range(7):
        c.bar(64 + i * 52, 48, 22, 6, INK)
    for row in range(5):
        for col in range(7):
            x, y = 60 + col * 52, 66 + row * 38
            today = row == 2 and col == 3
            c.rect(
                (x, y, x + 40, y + 30),
                fill=ACCENT if today else CARD,
                outline=LINE if not today else None,
                radius=4,
            )
            c.bar(x + 8, y + 11, 14, 6, CARD if today else MUTED)


def coaching_productivite(c: Canvas) -> None:
    """An Eisenhower matrix with tasks distributed across quadrants."""
    c.card((40, 28, 440, 272))
    c.line([(240, 48), (240, 252)], LINE, 1)
    c.line([(60, 150), (420, 150)], LINE, 1)
    quadrants = {
        (72, 62): (ACCENT, 3),
        (252, 62): (INK, 2),
        (72, 164): (MUTED, 2),
        (252, 164): (MUTED, 1),
    }
    for (qx, qy), (colour, count) in quadrants.items():
        for i in range(count):
            y = qy + i * 22
            c.ellipse((qx, y, qx + 10, y + 10), fill=colour)
            c.bar(qx + 18, y + 2, 120 - i * 18, 6, colour)


def dice_roller(c: Canvas) -> None:
    """Two dice showing a five and a three; the first one carries the accent."""
    c.card((40, 28, 440, 272))
    faces = [
        ((110, 90), [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2)], ACCENT),
        ((250, 90), [(0, 0), (1, 1), (2, 2)], STRONG),
    ]
    for (dx, dy), pips, pip_colour in faces:
        c.rect((dx, dy, dx + 120, dy + 120), fill=CARD, outline=STRONG, width=2, radius=14)
        for px, py in pips:
            cx, cy = dx + 26 + px * 34, dy + 26 + py * 34
            c.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=pip_colour)


def interactive_map(c: Canvas) -> None:
    """A road layout with a dropped pin."""
    c.card((40, 28, 440, 272))
    c.rect((41, 29, 439, 271), fill="#eef2f7", radius=6)
    for pts in (
        [(41, 120), (170, 120), (210, 90), (439, 90)],
        [(41, 210), (250, 210), (300, 175), (439, 175)],
        [(150, 29), (150, 120)],
        [(330, 90), (330, 271)],
    ):
        c.line(pts, CARD, 9)
        c.line(pts, LINE, 1)
    c.polygon([(240, 165), (222, 128), (258, 128)], ACCENT)
    c.ellipse((222, 104, 258, 140), fill=ACCENT)
    c.ellipse((233, 115, 247, 129), fill=CARD)


def pomodoro_timer(c: Canvas) -> None:
    """A countdown ring, roughly two thirds elapsed."""
    c.card((40, 28, 440, 272))
    box = (170, 60, 310, 200)
    scaled = tuple(v * SUPERSAMPLE for v in box)
    c.draw.arc(scaled, 0, 360, fill=LINE, width=14 * SUPERSAMPLE)
    c.draw.arc(scaled, -90, 145, fill=ACCENT, width=14 * SUPERSAMPLE)
    c.bar(206, 118, 68, 12, STRONG, radius=4)
    c.bar(220, 138, 40, 7, MUTED, radius=3)
    for i in range(4):
        c.ellipse((196 + i * 24, 226, 208 + i * 24, 238), fill=ACCENT if i < 2 else LINE)


def preparation_reunion(c: Canvas) -> None:
    """Meeting header, attendees, then the agenda."""
    c.card((40, 28, 440, 272))
    c.bar(64, 52, 190, 10, STRONG)
    c.bar(64, 70, 120, 6, MUTED)
    for i in range(4):
        c.ellipse((330 + i * 22, 48, 356 + i * 22, 74), fill=CARD, outline=LINE, width=2)
        c.ellipse((336 + i * 22, 54, 350 + i * 22, 68), fill=ACCENT_SOFT if i else ACCENT)
    c.line([(64, 96), (416, 96)], LINE, 1)
    for i in range(4):
        y = 116 + i * 34
        c.rect((64, y, 76, y + 12), fill=ACCENT if i == 0 else LINE, radius=3)
        c.bar(88, y + 1, 240 - i * 30, 8, INK)
        c.bar(88, y + 15, 150 - i * 20, 5, MUTED)


def qr_code(c: Canvas) -> None:
    """A QR pattern: three finder squares and a deterministic module field."""
    c.card((40, 28, 440, 272))
    size, origin, cell = 21, (150, 40), 10
    # Deterministic pseudo-random field — stable across runs, no RNG seeding.
    for row in range(size):
        for col in range(size):
            in_finder = (
                (row < 7 and col < 7)
                or (row < 7 and col >= size - 7)
                or (row >= size - 7 and col < 7)
            )
            if in_finder:
                continue
            if (row * 7 + col * 13 + (row * col) % 5) % 3 == 0:
                x, y = origin[0] + col * cell, origin[1] + row * cell
                c.rect((x, y, x + cell - 1, y + cell - 1), fill=STRONG)
    for fx, fy in ((0, 0), (size - 7, 0), (0, size - 7)):
        x, y = origin[0] + fx * cell, origin[1] + fy * cell
        c.rect((x, y, x + 7 * cell - 1, y + 7 * cell - 1), fill=STRONG, radius=6)
        c.rect(
            (x + cell, y + cell, x + 6 * cell - 1, y + 6 * cell - 1),
            fill=CARD,
            radius=4,
        )
        c.rect(
            (x + 2 * cell, y + 2 * cell, x + 5 * cell - 1, y + 5 * cell - 1),
            fill=ACCENT,
            radius=3,
        )


def redaction_professionnelle(c: Canvas) -> None:
    """A drafted document with one revised line highlighted."""
    c.card((40, 28, 440, 272))
    c.bar(64, 52, 210, 10, STRONG)
    y = 84
    for i, w in enumerate((330, 300, 340, 260, 320, 290)):
        highlight = i == 3
        if highlight:
            c.rect((60, y - 5, 60 + w + 8, y + 13), fill=ACCENT_SOFT, radius=4)
        c.bar(64, y, w, 7, ACCENT if highlight else MUTED)
        y += 26
    c.bar(64, y + 6, 120, 7, INK)


def skill_generator(c: Canvas) -> None:
    """A skill file being assembled, with the accent marking what is added."""
    c.card((40, 28, 440, 272))
    c.rect((96, 56, 300, 256), fill=CARD, outline=LINE, width=2, radius=8)
    c.rect((96, 56, 300, 92), fill=ACCENT, radius=8)
    c.rect((96, 84, 300, 92), fill=ACCENT)
    c.bar(112, 68, 90, 10, CARD)
    y = 110
    for w in (150, 120, 165, 100, 140):
        c.bar(112, y, w, 7, MUTED)
        y += 24
    cx, cy = 350, 150
    c.ellipse((cx - 34, cy - 34, cx + 34, cy + 34), fill=ACCENT)
    c.rect((cx - 16, cy - 4, cx + 16, cy + 4), fill=CARD, radius=2)
    c.rect((cx - 4, cy - 16, cx + 4, cy + 16), fill=CARD, radius=2)


def synthese_recherche(c: Canvas) -> None:
    """Three sources converging into one synthesis."""
    c.card((40, 28, 440, 272))
    for i in range(3):
        x = 64 + i * 116
        c.rect((x, 52, x + 92, 128), fill=CARD, outline=LINE, width=2, radius=6)
        c.bar(x + 12, 64, 58, 7, INK)
        for j in range(3):
            c.bar(x + 12, 82 + j * 13, 68 - j * 12, 5, MUTED)
        c.line([(x + 46, 128), (x + 46, 150), (240, 150), (240, 176)], ACCENT_SOFT, 3)
    c.rect((120, 176, 360, 252), fill=CARD, outline=ACCENT, width=2, radius=6)
    c.bar(140, 192, 110, 9, ACCENT)
    for j in range(3):
        c.bar(140, 212 + j * 14, 200 - j * 40, 6, INK)


def tic_tac_toe(c: Canvas) -> None:
    """A board mid-game, with the winning row already on the diagonal."""
    c.card((40, 28, 440, 272))
    ox, oy, cell = 165, 45, 70
    for i in (1, 2):
        c.line([(ox + i * cell, oy + 6), (ox + i * cell, oy + 3 * cell - 6)], LINE, 3)
        c.line([(ox + 6, oy + i * cell), (ox + 3 * cell - 6, oy + i * cell)], LINE, 3)
    marks = {(0, 0): "x", (1, 1): "x", (2, 2): "x", (0, 2): "o", (1, 0): "o"}
    for (row, col), mark in marks.items():
        cx, cy = ox + col * cell + cell / 2, oy + row * cell + cell / 2
        if mark == "x":
            c.line([(cx - 17, cy - 17), (cx + 17, cy + 17)], ACCENT, 6)
            c.line([(cx + 17, cy - 17), (cx - 17, cy + 17)], ACCENT, 6)
        else:
            c.ellipse((cx - 18, cy - 18, cx + 18, cy + 18), outline=STRONG, width=6)


def unit_converter(c: Canvas) -> None:
    """Two fields and the conversion between them."""
    c.card((40, 28, 440, 272))
    for i, (y, colour) in enumerate(((72, INK), (188, ACCENT))):
        c.rect(
            (72, y, 408, y + 64),
            fill=CARD,
            outline=ACCENT if i else LINE,
            width=2,
            radius=8,
        )
        c.bar(92, y + 18, 96, 14, colour)
        c.bar(92, y + 40, 54, 7, MUTED)
        c.rect((330, y + 20, 388, y + 44), fill=ACCENT_SOFT if i else LINE, radius=4)
    cx = 240
    c.ellipse((cx - 22, 138, cx + 22, 182), fill=ACCENT)
    c.line([(cx, 150), (cx, 170)], CARD, 4)
    c.polygon([(cx - 8, 166), (cx + 8, 166), (cx, 176)], CARD)


def weather_dashboard(c: Canvas) -> None:
    """A row of daily forecast cards with a min/max range bar."""
    c.card((40, 28, 440, 272))
    for i in range(4):
        x = 60 + i * 96
        c.rect(
            (x, 52, x + 80, 248),
            fill=CARD,
            outline=ACCENT if i == 0 else LINE,
            width=2,
            radius=8,
        )
        c.bar(x + 22, 68, 36, 7, INK)
        cx, cy = x + 40, 112
        if i in (0, 2):
            c.ellipse((cx - 17, cy - 17, cx + 17, cy + 17), fill=ACCENT if i == 0 else MUTED)
        else:
            c.ellipse((cx - 20, cy - 6, cx + 4, cy + 18), fill=MUTED)
            c.ellipse((cx - 4, cy - 14, cx + 22, cy + 18), fill=MUTED)
            c.rect((cx - 20, cy + 6, cx + 22, cy + 18), fill=MUTED, radius=6)
        top, bottom = 156 + i * 6, 210 - i * 4
        c.rect((cx - 4, top, cx + 4, bottom), fill=ACCENT_SOFT, radius=4)
        c.bar(x + 20, 224, 40, 6, MUTED)


DRAWINGS: dict[str, Callable[[Canvas], None]] = {
    "briefing-quotidien": briefing_quotidien,
    "calendar-month": calendar_month,
    "coaching-productivite": coaching_productivite,
    "dice-roller": dice_roller,
    "interactive-map": interactive_map,
    "pomodoro-timer": pomodoro_timer,
    "preparation-reunion": preparation_reunion,
    "qr-code": qr_code,
    "redaction-professionnelle": redaction_professionnelle,
    "skill-generator": skill_generator,
    "synthese-recherche": synthese_recherche,
    "tic-tac-toe": tic_tac_toe,
    "unit-converter": unit_converter,
    "weather-dashboard": weather_dashboard,
}


def render(skill_name: str) -> bytes:
    """Render one preview to PNG bytes.

    Args:
        skill_name: Directory name under ``data/skills/system``.

    Returns:
        Encoded PNG.

    Raises:
        KeyError: When no drawing is registered for the skill.
    """
    canvas = Canvas()
    DRAWINGS[skill_name](canvas)
    buffer = io.BytesIO()
    canvas.finish().save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _same_pixels(left: bytes, right: bytes) -> bool:
    """Whether two encoded PNGs decode to the same image.

    Args:
        left: First encoded PNG.
        right: Second encoded PNG.

    Returns:
        True when size, mode and pixel data all match.
    """
    first, second = Image.open(io.BytesIO(left)), Image.open(io.BytesIO(right))
    return (first.size, first.mode, first.tobytes()) == (
        second.size,
        second.mode,
        second.tobytes(),
    )


def main() -> int:
    """Write (or verify) every system skill's preview.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report missing or stale previews without writing anything.",
    )
    args = parser.parse_args()

    on_disk = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()} if SKILLS_DIR.is_dir() else set()
    missing_drawing = sorted(on_disk - DRAWINGS.keys())
    if missing_drawing:
        print(
            f"ERROR: no drawing registered for: {', '.join(missing_drawing)}",
            file=sys.stderr,
        )
        return 1

    stale: list[str] = []
    for skill_name in sorted(DRAWINGS):
        skill_dir = SKILLS_DIR / skill_name
        if not skill_dir.is_dir():
            print(f"skip {skill_name}: directory absent")
            continue
        target = skill_dir / "assets" / "preview.png"
        payload = render(skill_name)
        if args.check:
            # Pixels, not bytes: zlib output is platform-dependent, so a
            # byte comparison flags every image as stale on another OS.
            if not target.is_file() or not _same_pixels(target.read_bytes(), payload):
                stale.append(skill_name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        print(f"wrote {target.relative_to(REPO_ROOT)} ({len(payload) / 1024:.1f} KB)")

    if args.check and stale:
        print(f"ERROR: previews missing or stale: {', '.join(stale)}", file=sys.stderr)
        print("Run: python scripts/generate_skill_previews.py", file=sys.stderr)
        return 1
    if args.check:
        print(f"OK: {len(DRAWINGS)} previews match their generator.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
