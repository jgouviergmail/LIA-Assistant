"""What the assistant says of a repeating event (ADR-369, lot 10, D2).

Out of ``calendar_tools.py``, frozen at its audited size. The manifests read these words, so
nothing here reaches the tool layer: a rule a tool call dictates is read in
``tools/calendar_series``. The rule rides the draft as plain data, with its sentence in the
person's language for the card.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from src.core.recurrence import RecurrenceSpec
from src.domains.agents.registry.catalogue import ParameterSchema
from src.domains.agents.registry.recurrence_parameters import RECURRENCE_DOCS

EVENT_SCOPE_DESCRIPTION: Final = (
    "'series' reaches every occurrence of a repeating event, and asks it only when the person "
    "said so; omit it to reach this occurrence alone. A new time keeps the series' first day."
)
_REPEAT_FIELDS: Final = (
    ("repeat", "string"),
    ("repeat_every", "integer"),
    ("weekdays", "array"),
    ("month_days", "array"),
    ("months", "array"),
    ("nth_weekday", "string"),
    ("until_date", "string"),
    ("max_occurrences", "integer"),
)
EVENT_REPEAT_PARAMETERS: Final = tuple(
    ParameterSchema(name=name, type=kind, required=False, description=RECURRENCE_DOCS[name])
    for name, kind in _REPEAT_FIELDS
)
EVENT_SCOPE_PARAMETER: Final = ParameterSchema(
    name="scope", type="string", required=False, description=EVENT_SCOPE_DESCRIPTION
)


def readable_series(source: Mapping[str, Any]) -> dict[str, Any]:
    """What a source says of a series: only what it does say."""
    read = {key: source[key] for key in ("recurrence", "recurrence_text") if source.get(key)}
    if source.get("scope") == "series":
        read["scope"] = "series"
    if source.get("moves_series"):
        read["moves_series"] = True
    return read


def spec_of(source: Mapping[str, Any]) -> RecurrenceSpec | None:
    """The rule a draft carries."""
    held = source.get("recurrence")
    return RecurrenceSpec.model_validate(held) if held else None


__all__ = [
    "EVENT_REPEAT_PARAMETERS",
    "EVENT_SCOPE_DESCRIPTION",
    "EVENT_SCOPE_PARAMETER",
    "readable_series",
    "spec_of",
]
