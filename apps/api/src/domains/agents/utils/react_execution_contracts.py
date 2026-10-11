"""Serializable observations owned by one ReAct turn, independent of nodes."""

from __future__ import annotations

from typing import Literal, TypedDict


class CachedRead(TypedDict):
    """An exact successful read, scoped by its keyed signature and expiry."""

    content: str
    registry: dict[str, object]
    expires_at: float


class ReadObservation(TypedDict):
    """Evidence about a read actually attempted, never an inferred user promise."""

    tool_name: str
    signature: str
    outcome: Literal["obtained", "failed", "empty", "partial"]


class ReadEvidence(TypedDict):
    """Only observed outcome markers; no interpretation of free text."""

    outcome: Literal["obtained", "failed", "empty", "partial"]


class ReactExecutionUpdate(TypedDict, total=False):
    """Sidecars returned by execution, with checkpoint-safe values."""

    react_read_results: dict[str, CachedRead]
    react_read_observations: dict[str, ReadObservation]
    react_last_productive_message_id: str | None
