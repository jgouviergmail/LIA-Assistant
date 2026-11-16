"""The Markdown structure Telegram cannot draw, drawn with what it does (lot 3).

Telegram's HTML has no heading, no table and no list: an answer reached the
person as raw Markdown — « ## Résumé », rows of pipes, a dash before every
item. Each structure is rewritten, line by line and BEFORE the inline rules run,
into what Telegram draws:

- a heading is a bold line;
- a table is one group per row: the row's first cell in bold, then one bullet
  per other column, « header: value » in the reader's punctuation (a phone
  shows a column of pipes as a wall of text, and wraps it); a one-column table
  is a list under its header;
- a quote is a Telegram quote, the structure it holds drawn too;
- a list item opens on a bullet, a task on its box; a rule is a short line;
- a ``<br>`` is a new line (a separator inside a table cell).

What the reader shielded — a code span's or a code block's text, a reference —
holds no punctuation these rules can read (``read_as_markdown`` shields every
ASCII mark of a code body), so nothing typed as code is restructured, and a
fence line itself matches none of them.
"""

from __future__ import annotations

import re

from src.domains.shared.markdown_literal import RESERVED_MARKERS

#: Where a Telegram quote opens and closes while the inline rules run.
QUOTE_OPEN = RESERVED_MARKERS[1]
QUOTE_CLOSE = RESERVED_MARKERS[2]

#: An ATX heading, its closing hashes dropped.
_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
#: A thematic break: three or more of one mark, spaces allowed between.
_RULE = re.compile(r"^[ \t]{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
#: A bullet item (its indent kept), optionally a task with its box.
_ITEM = re.compile(r"^([ \t]*)[-*+][ \t]+(?:\[([ xX])\][ \t]+)?(.*)$")
#: A quoted line, every nesting level at once.
_QUOTED = re.compile(r"^(?:[ \t]{0,3}>[ \t]?)+")
#: A table's delimiter row: one or more ``:--:`` cells separated by pipes.
_DELIMITER_ROW = re.compile(r"^[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
#: A pipe that separates two cells (an escaped one belongs to its cell).
_CELL_SEPARATOR = re.compile(r"(?<!\\)\|")
_LINE_BREAK = re.compile(r"<br[ \t]*/?>", re.IGNORECASE)
#: What a rule is drawn as: Telegram has no horizontal line.
_RULE_DRAWN = "———"
#: What a line break inside a table cell is drawn as.
_CELL_BREAK = " · "
_BULLET = "•"
_TASK_BOXES = {" ": "☐", "x": "☑", "X": "☑"}


def draw_structure(text: str, separator: str) -> str:
    """Rewrite the block structure of Markdown into what Telegram draws.

    Args:
        text: Markdown whose code and references the reader shielded.
        separator: The reader's punctuation between a label and its value.

    Returns:
        Markdown holding only inline marks, bullets, boxes and the quote
        markers :data:`QUOTE_OPEN` / :data:`QUOTE_CLOSE`.
    """
    lines = text.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if (table_end := _table_end(lines, index)) is not None:
            out.append(_drawn_table(lines[index:table_end], separator))
            index = table_end
            continue
        if _QUOTED.match(line):
            end = index
            while end < len(lines) and _QUOTED.match(lines[end]):
                end += 1
            inner = "\n".join(_drawn_line(_QUOTED.sub("", quoted)) for quoted in lines[index:end])
            # An empty quote (« > » alone) draws nothing: Telegram has no empty quote.
            out.append(f"{QUOTE_OPEN}{inner}{QUOTE_CLOSE}" if inner.strip() else inner)
            index = end
            continue
        out.append(_drawn_line(line))
        index += 1
    return "\n".join(out)


def _drawn_line(line: str) -> str:
    """One line outside a table: a rule, a heading, an item, or prose."""
    if _RULE.match(line):
        return _RULE_DRAWN
    if heading := _HEADING.match(line):
        return _LINE_BREAK.sub("\n", _bold(heading.group(1)))
    if item := _ITEM.match(line):
        indent, task, rest = item.groups()
        mark = _BULLET if task is None else _TASK_BOXES[task]
        return _LINE_BREAK.sub("\n", f"{indent}{mark} {rest}")
    return _LINE_BREAK.sub("\n", line)


def _bold(text: str) -> str:
    """``text`` as one bold run; bold marks it already held are dropped (no empty run)."""
    plain = text.replace("**", "").replace("__", "").strip()
    return f"**{plain}**" if plain else ""


def _cells(row: str) -> list[str]:
    """The cells of a table row, an escaped pipe kept as a pipe of its cell."""
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [
        _LINE_BREAK.sub(_CELL_BREAK, cell.strip().replace("\\|", "|"))
        for cell in _CELL_SEPARATOR.split(row)
    ]


def _table_end(lines: list[str], start: int) -> int | None:
    """Where the table starting at ``start`` ends, or None when none starts there.

    A table is a header row and a delimiter row with as many cells, then every
    following line holding a pipe — a blank line or a line without one ends it.
    """
    if start + 1 >= len(lines) or "|" not in lines[start]:
        return None
    delimiter = lines[start + 1]
    if "|" not in delimiter or not _DELIMITER_ROW.match(delimiter):
        return None
    if len(_cells(lines[start])) != len(_cells(delimiter)):
        return None
    end = start + 2
    while end < len(lines) and "|" in lines[end] and lines[end].strip():
        end += 1
    return end


def _drawn_table(rows: list[str], separator: str) -> str:
    """A table as one group per row, the header naming each value."""
    header = _cells(rows[0])
    body = [_cells(row) for row in rows[2:]]
    if len(header) == 1:
        title = _bold(header[0])
        items = [f"{_BULLET} {row[0]}" for row in body if row and row[0]]
        return "\n".join([title, *items] if title else items)
    groups: list[str] = []
    for row in body:
        cells = (row + [""] * len(header))[: len(header)]
        values = [
            f"{_BULLET} {name}{separator}{value}"
            for name, value in zip(header[1:], cells[1:], strict=True)
            if value
        ]
        groups.append("\n".join([_bold(cells[0]) or "—", *values]))
    return "\n\n".join(groups)
