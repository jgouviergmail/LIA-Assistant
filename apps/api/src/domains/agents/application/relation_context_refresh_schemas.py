"""A forced cache read names exactly the approved provider sections."""

from pydantic import BaseModel, ConfigDict, Field

from src.domains.agents.application.relation_context_schemas import (
    RelationContextQuery,
    RelationProviderSection,
)


class RelationContextRefreshRequest(RelationContextQuery):
    sections: list[RelationProviderSection] = Field(min_length=1, max_length=3)


class RelationContextRefreshPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    relation_context: RelationContextRefreshRequest
