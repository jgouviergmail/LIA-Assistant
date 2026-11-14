"""Measure how often an answer LIA archived repeats itself (lot 26, read only).

A MEASUREMENT, never a gate, and free. A model can fall into a loop — the same line,
sentence or tail again and again — and nothing in LIA watches for it (ADR-170 guards a
repeated TOOL call, not repeated words). Before writing a guard, this counts how often
it happens: every assistant message of the last ``--days``, three detectors, counts and
message ids only — never a word of a message. The session is forced read-only and the
check is printed.

A flagged message shows only the SHAPE of what repeats (letters as ``a``, digits as
``9``): a dated list of cards repeats its date line by design, and the shape says so
without reading the content.

Run in the API container (production: through the read-only harness)::

    python -m scripts.agents.measure_repeated_output --days 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from typing import Final

_TAG: Final = re.compile(r"<[^>]+>")
_CODE_BLOCKS: Final = re.compile(r"<(style|script)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_SENTENCE: Final = re.compile(r"(?<=[.!?。！？])\s+")
#: The tail a loop shows at, the window that repeats in it, and how often.
TAIL_CHARS: Final = 800
WINDOW_CHARS: Final = 30
LOOP_REPEATS: Final = 4


def plain(content: str) -> str:
    """The words a person reads: style and script blocks out, then every tag."""
    return _TAG.sub(" ", _CODE_BLOCKS.sub(" ", content))


def _tail_piece(text: str) -> tuple[str, int]:
    tail = text[-TAIL_CHARS:]
    pieces = Counter(tail[i : i + WINDOW_CHARS] for i in range(max(0, len(tail) - WINDOW_CHARS)))
    return pieces.most_common(1)[0] if pieces else ("", 0)


def flags(content: str) -> list[str]:
    """Which repetition shapes a message has: ``line_loop``, ``tail_loop``, ``sentence_repeat``."""
    text = plain(content)
    found: list[str] = []
    lines = [line.strip() for line in text.splitlines() if len(line.strip()) >= 20]
    run = 1
    for previous, current in zip(lines, lines[1:], strict=False):
        run = run + 1 if current == previous else 1
        if run >= 3:
            found.append("line_loop")
            break
    piece, repeats = _tail_piece(text)
    if repeats >= LOOP_REPEATS and len(set(piece)) > 8:
        found.append("tail_loop")
    sentences = Counter(
        sentence.strip() for sentence in _SENTENCE.split(text) if len(sentence.strip()) >= 30
    )
    if sentences and sentences.most_common(1)[0][1] >= LOOP_REPEATS:
        found.append("sentence_repeat")
    return found


def shape(content: str) -> str:
    """What repeats at the tail, as a shape: letters ``a``, digits ``9`` — never a word."""
    piece, repeats = _tail_piece(plain(content))
    return re.sub(r"[^\W\d_]", "a", re.sub(r"\d", "9", piece)) + f" x{repeats}"


async def _scan(days: int) -> dict[str, object]:
    from sqlalchemy import text

    from src.infrastructure.database.registry import import_all_models

    import_all_models()
    from src.infrastructure.database import get_db_context

    async with get_db_context() as db:
        await db.execute(text("SET SESSION default_transaction_read_only = on"))
        read_only = (await db.execute(text("SHOW default_transaction_read_only"))).scalar()
        rows = (
            await db.execute(
                text(
                    "SELECT id, created_at, content FROM conversation_messages "
                    "WHERE role = 'assistant' AND created_at > now() - make_interval(days => :days) "
                    "ORDER BY created_at"
                ),
                {"days": days},
            )
        ).all()
        await db.rollback()
    by_kind: Counter[str] = Counter()
    flagged: list[dict[str, object]] = []
    for row in rows:
        content = row.content or ""
        kinds = flags(content)
        by_kind.update(kinds)
        if kinds:
            flagged.append(
                {
                    "id": str(row.id),
                    "day": row.created_at.date().isoformat(),
                    "kinds": kinds,
                    "html": "<div" in content or "<table" in content,
                    "shape": shape(content) if "tail_loop" in kinds else "",
                }
            )
    return {
        "read_only": read_only,
        "assistant_messages": len(rows),
        "flagged": len(flagged),
        "by_kind": dict(by_kind),
        "flagged_rows": flagged,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--days", type=int, default=30, help="how far back to read")
    args = parser.parse_args(argv)
    json.dump(asyncio.run(_scan(args.days)), sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
