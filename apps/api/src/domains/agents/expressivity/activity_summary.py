"""A constant-size, passive record of the families a delivered answer used."""

from collections.abc import Mapping
from typing import Literal, TypedDict

from pydantic import ValidationError

from src.domains.agents.expressivity.activity import Activity, ActivityFamily


class ActivitySnapshot(TypedDict):
    version: Literal[1]
    families: list[ActivityFamily]
    performed: list[ActivityFamily]
    prepared: bool
    failed: bool


class ActivitySummary:
    """Set semantics make duplicate delivery idempotent without retaining call IDs."""

    def __init__(self) -> None:
        self._families: set[ActivityFamily] = set()
        self._performed: set[ActivityFamily] = set()
        self._prepared = False
        self._failed = False

    def observe(self, metadata: object) -> None:
        if not isinstance(metadata, Mapping) or "activity" not in metadata:
            return
        try:
            event = Activity.model_validate(metadata["activity"])
        except ValidationError:
            return
        self._families.add(event.family)
        self._prepared |= event.outcome == "prepared"
        self._failed |= event.outcome == "failed"
        if event.phase == "finished" and event.outcome == "succeeded" and event.intent == "act":
            self._performed.add(event.family)

    def snapshot(self) -> ActivitySnapshot | None:
        if not self._families:
            return None
        return {
            "version": 1,
            "families": sorted(self._families),
            "performed": sorted(self._performed),
            "prepared": self._prepared,
            "failed": self._failed,
        }
