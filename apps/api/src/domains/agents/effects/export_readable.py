"""Taking a register out of the application, readable (ADR-263, lot 4).

Four extractions were asked for — a user's own register, and an administrator's
over one, several or every account for a period — and this module is the engine
under all of them. Two formats, because they answer different questions
(Markdown is read, CSV is counted) and ONE renderer per format, driven by a
:class:`RegisterSpec`, because two implementations would drift and a register
whose exports disagree with each other is evidence of nothing.

Four properties the wording must have, each of them a defect avoided:

- **the reader's clock, not the server's.** An action stamped 23:40 UTC
  happened the next day in Auckland and the previous one in Los Angeles; day
  headers cut on the server's clock would put entries under the wrong date for
  everyone but the operator.
- **the reader's language**, resolved at export time from the stored key — the
  same rule the account archive follows.
- **the authority on the line.** "Who allowed this" is the question a register
  exists to answer; an export that dropped it would be a list of events.
- **nothing invented.** A provider reference is printed when the world gave one
  back and omitted otherwise, never rendered as ``None``.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

logger = structlog.get_logger(__name__)

#: Prefixes a spreadsheet reads as a formula. A register is data; a cell that
#: computes is a payload. Neutralised with a leading apostrophe, the convention
#: every spreadsheet honours, rather than by dropping the character — the
#: exported value must stay the value that was stored.
_FORMULA_PREFIXES: Final[tuple[str, ...]] = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class RegisterSpec:
    """How one register renders.

    Attributes:
        slug: File-name stem, and the register's identity in a download.
        heading: Title, resolved in the reader's language.
        stamp_of: The row's own moment — actions are dated by their claim,
            consultations by their return.
        sentence_of: One readable line, without its timestamp.
        csv_columns: Column names, in order.
        cells_of: One CSV row, in :attr:`csv_columns` order.
    """

    slug: str
    heading: Callable[[str], str]
    stamp_of: Callable[[Any], datetime | None]
    sentence_of: Callable[[Any, str], str]
    csv_columns: tuple[str, ...]
    cells_of: Callable[[Any, str], tuple[Any, ...]]


def _zone(timezone_name: str) -> tzinfo:
    """The reader's timezone, or UTC when the preference is unusable.

    Args:
        timezone_name: An IANA name from the user's preferences.

    Returns:
        The zone. A stale or misspelled preference degrades the DATES, it never
        loses the register.
    """
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError, ValueError, KeyError:
        logger.debug("export_timezone_unusable", timezone=timezone_name)
        return ZoneInfo("UTC")


def _local(stamp: datetime | None, zone: tzinfo) -> datetime | None:
    """Move a stored UTC moment into the reader's clock."""
    return None if stamp is None else stamp.astimezone(zone)


def _text(value: Any) -> str:
    """One cell's text: an absent value is absent, never the word ``None``."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _safe_cell(value: Any) -> str:
    """Neutralise a cell a spreadsheet would execute.

    Args:
        value: The stored value.

    Returns:
        The same text, prefixed with an apostrophe when it would otherwise be
        read as a formula. Nothing is removed: an export must carry what was
        recorded, not a cleaned-up version of it.
    """
    text = _text(value)
    return f"'{text}" if text.startswith(_FORMULA_PREFIXES) else text


def render_markdown(
    spec: RegisterSpec, rows: Sequence[Any], language: str, timezone_name: str
) -> str:
    """Render one register as a document, grouped by the reader's days.

    Args:
        spec: Which register.
        rows: Its rows, oldest first.
        language: The reader's language.
        timezone_name: The reader's display timezone.

    Returns:
        Markdown: a title, then one section per day.
    """
    zone = _zone(timezone_name)
    lines = [f"# {spec.heading(language)}", ""]
    current_day = ""
    for row in rows:
        stamp = _local(spec.stamp_of(row), zone)
        day = stamp.strftime("%Y-%m-%d") if stamp else ""
        if day != current_day:
            lines.extend([f"## {day}", ""])
            current_day = day
        clock = stamp.strftime("%H:%M:%S") if stamp else ""
        lines.append(f"- {clock} — {spec.sentence_of(row, language)}")
    return "\n".join(lines) + "\n"


def render_csv(spec: RegisterSpec, rows: Sequence[Any], language: str, timezone_name: str) -> str:
    """Render one register as a table.

    Args:
        spec: Which register.
        rows: Its rows, oldest first.
        language: The reader's language, for the readable column.
        timezone_name: The reader's display timezone.

    Returns:
        CSV text, header first — including for an empty register, so a reader
        can tell "nothing happened" from "the export failed".
    """
    zone = _zone(timezone_name)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(spec.csv_columns)
    for row in rows:
        cells = spec.cells_of(row, language)
        stamped = tuple(
            _local(cell, zone) if isinstance(cell, datetime) else cell for cell in cells
        )
        writer.writerow([_safe_cell(cell) for cell in stamped])
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# The two registers
# ---------------------------------------------------------------------------


def _action_sentence(row: Any, language: str) -> str:
    """One action, with the authority that allowed it.

    Args:
        row: An ``AgentEffect`` row.
        language: The reader's language.

    Returns:
        The sentence, carrying the capability, the outcome, the authority and —
        only when the world gave one back — the provider's own reference. The
        capability is named here as it is in the consultation register: a
        masked export must still say WHICH capability acted, or masking hides
        the one fact an administrator needs.
    """
    from src.core.i18n_effects import render_effect_label

    label = row.label
    if isinstance(label, str):
        try:
            label = json.loads(label)
        except TypeError, ValueError:
            label = None
    parts = [
        render_effect_label(label, language),
        f"({row.tool_name})",
        f"[{_value(row.status)}]",
        f"({_value(row.source)}",
    ]
    approval = getattr(row, "approval_kind", None)
    parts[-1] += f", {approval})" if approval else ")"
    reference = getattr(row, "provider_ref", None)
    if reference:
        parts.append(f"ref: {reference}")
    return " ".join(parts)


def _treatment_sentence(row: Any, language: str) -> str:
    """One consultation, named by its domain and followed by its capability."""
    from src.core.i18n_treatments import render_treatment_domain, render_treatment_failure
    from src.domains.agents.effects.treatment_labels import treatment_domain

    domain = render_treatment_domain(treatment_domain(row.tool_name), language)
    marker = "" if _value(row.outcome) == "ok" else f" [{render_treatment_failure(language)}]"
    return f"{domain} ({row.tool_name}){marker} — {row.duration_ms} ms ({_value(row.source)})"


def _value(value: Any) -> str:
    """The stored spelling of an enum column, or the string itself."""
    return str(getattr(value, "value", value))


def _action_heading(language: str) -> str:
    from src.core.i18n_effects import render_effect_heading

    return render_effect_heading(language)


def _treatment_heading(language: str) -> str:
    from src.core.i18n_treatments import render_treatment_heading

    return render_treatment_heading(language)


def _action_cells(row: Any, language: str) -> tuple[Any, ...]:
    return (
        row.claimed_at,
        row.closed_at,
        _action_sentence(row, language),
        row.tool_name,
        _value(row.mutation_policy),
        _value(row.status),
        _value(row.source),
        row.execution_mode,
        getattr(row, "approval_kind", None),
        getattr(row, "provider_ref", None),
        getattr(row, "error_code", None),
        row.thread_id,
    )


def _treatment_cells(row: Any, language: str) -> tuple[Any, ...]:
    from src.core.i18n_treatments import render_treatment_domain
    from src.domains.agents.effects.treatment_labels import treatment_domain

    return (
        row.occurred_at,
        render_treatment_domain(treatment_domain(row.tool_name), language),
        row.tool_name,
        _value(getattr(row, "mutation_policy", None) or ""),
        _value(row.outcome),
        _value(row.source),
        row.execution_mode,
        row.duration_ms,
        row.thread_id,
    )


ACTIONS: Final[RegisterSpec] = RegisterSpec(
    slug="actions",
    heading=_action_heading,
    # An action is dated by its CLAIM: that is the moment it was decided, and
    # the only one a refused or abandoned row has at all.
    stamp_of=lambda row: row.claimed_at,
    sentence_of=_action_sentence,
    csv_columns=(
        "claimed_at",
        "closed_at",
        "action",
        "tool_name",
        "mutation_policy",
        "status",
        "source",
        "execution_mode",
        "approval_kind",
        "provider_ref",
        "error_code",
        "conversation",
    ),
    cells_of=_action_cells,
)

TREATMENTS: Final[RegisterSpec] = RegisterSpec(
    slug="consultations",
    heading=_treatment_heading,
    stamp_of=lambda row: row.occurred_at,
    sentence_of=_treatment_sentence,
    csv_columns=(
        "occurred_at",
        "domain",
        "tool_name",
        "mutation_policy",
        "outcome",
        "source",
        "execution_mode",
        "duration_ms",
        "conversation",
    ),
    cells_of=_treatment_cells,
)
