"""Provider-card selectors and inherited source output are pure catalogue contracts."""

from datetime import datetime
from typing import Literal, Self, get_args

from pydantic import ConfigDict, Field, model_validator

from src.domains.agents.application.relation_debrief_read import RelationStoredDebriefQuery
from src.domains.relations.providers.schemas import RelationContext

RelationProviderSection = Literal["contact", "emails", "events"]
RELATION_CONTEXT_MAX_BYTES = 64_000


class RelationContextQuery(RelationStoredDebriefQuery):
    sections: list[RelationProviderSection] = Field(
        default_factory=lambda: list(get_args(RelationProviderSection)),
        max_length=3,
        description="Source sections to read. Mail/events may need the contact as address input; excluded sections are not reported.",
    )

    @model_validator(mode="after")
    def unique_sections(self) -> Self:
        if len(set(self.sections)) != len(self.sections):
            raise ValueError("Select each provider section once")
        return self


class RelationContextProjection(RelationContext):
    model_config = ConfigDict(frozen=True, extra="forbid")
    observed_at: datetime
