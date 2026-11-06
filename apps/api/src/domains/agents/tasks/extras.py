"""What a task tool call asks beyond a title, notes and a day (ADR-369, lot 9).

Read by the tools, the draft factories and the executors: a value object depending on nothing, so
none of them depends on another.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskExtras:
    """What a tool call asks beyond a title, notes and a day."""

    importance: str | None = None
    reminder: str | None = None
    repeat: str | None = None
    steps: tuple[str, ...] = ()
    clear_reminder: bool = False
    clear_repeat: bool = False

    @property
    def asked(self) -> bool:
        """Whether the call asks any of it."""
        return bool(
            self.importance
            or self.reminder
            or self.repeat
            or self.steps
            or self.clear_reminder
            or self.clear_repeat
        )

    def fields(self) -> dict[str, Any]:
        """The draft's fields."""
        return {
            "importance": self.importance,
            "reminder": self.reminder,
            "repeat": self.repeat,
            "steps": list(self.steps),
            "clear_reminder": self.clear_reminder,
            "clear_repeat": self.clear_repeat,
        }


def read_extras(kwargs: Mapping[str, Any]) -> TaskExtras:
    """What a tool call or a draft asks; what it leaves out is not asked."""
    return TaskExtras(
        importance=kwargs.get("importance"),
        reminder=kwargs.get("reminder"),
        repeat=kwargs.get("repeat"),
        steps=tuple(kwargs.get("steps") or ()),
        clear_reminder=bool(kwargs.get("clear_reminder")),
        clear_repeat=bool(kwargs.get("clear_repeat")),
    )


__all__ = ["TaskExtras", "read_extras"]
