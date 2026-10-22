"""Partial writes preserve the difference between absence and explicit null.

Models marked MODEL-FACING below are read by a model as a JSON schema (a
structured-output contract or a tool parameter). They carry comments, never
docstrings or field descriptions: both become schema text, and changing what a
model reads is a measured decision, not documentation.
"""

from typing import Annotated, Self

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, model_validator

from src.domains.shared.discussion_sources import DiscussionValue, SensitiveTopic, SourceKey


# MODEL-FACING (settings tool): a sparse change to the person's discussion policy.
class DiscussionPolicyPatch(DiscussionValue):
    enabled: StrictBool | None = None
    start_hour: Annotated[StrictInt | None, Field(ge=0, le=23)] = None
    end_hour: Annotated[StrictInt | None, Field(ge=0, le=23)] = None
    daily_max: Annotated[StrictInt | None, Field(ge=1)] = None
    sources: tuple[SourceKey, ...] | None = None
    sensitive_topics: tuple[SensitiveTopic, ...] | None = None
    forbidden_topics: Annotated[
        tuple[Annotated[str, Field(min_length=1, max_length=160)], ...] | None,
        Field(max_length=100),
    ] = None
    paused_until: AwareDatetime | None = None

    @model_validator(mode="after")
    def null_is_explicit_and_limited(self) -> Self:
        """Refuse an explicit null on every field but ``daily_max`` and ``paused_until``.

        An absent field is left unchanged; a null ``daily_max`` lifts the daily limit
        and a null ``paused_until`` ends a pause.
        """
        for name in self.model_fields_set - {"daily_max", "paused_until"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self
