"""What the assistant reads and confirms of the person's writing style (ADR-383).

Reading answers the record the settings show. Learning and forgetting are acts the
person confirms on an exact card: learning binds the switch it needs and the record it
replaces, forgetting binds the very record it removes — a card answered after either
changed refuses instead of acting on another state (amendment 2026-11-16).
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class WritingStyleActionField(StrEnum):
    """What a confirmed writing-style act tells the open screens changed."""

    LEARNING = "writing_style_learning"
    RECORD = "writing_style_record"


class WritingStyleRecord(BaseModel):
    """The record a card names, as the person saw it.

    Attributes:
        learned_at: When it was learned (ISO 8601, UTC): its identity.
        mails_read: How many sent e-mails it was learned from.
        profile_learned: Whether it holds a profile (False: too few e-mails were found).
    """

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    learned_at: str
    mails_read: int
    profile_learned: bool


class WritingStyleLearnRequest(BaseModel):
    """Learn the current account's writing style: no other scope exists."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Literal["current_account"]


class WritingStyleLearnScope(BaseModel):
    """What a confirmed learning reads, and the record it replaces (None: nothing learned)."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    mails_to_read: int
    replaces: WritingStyleRecord | None


class WritingStyleLearnPatch(BaseModel):
    """The exact learning the person confirms."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    writing_style_learning: WritingStyleLearnScope


class WritingStyleForgetRequest(BaseModel):
    """Forget the current account's writing style: no other scope exists."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Literal["current_account"]


class WritingStyleForgetPatch(BaseModel):
    """The exact record the person confirms forgetting."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    writing_style_record: WritingStyleRecord
