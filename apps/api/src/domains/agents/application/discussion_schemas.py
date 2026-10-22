"""Closed personal controls; account identity and optimistic revisions are server-owned.

The request and intent models are MODEL-FACING: their JSON schema is the discussion
tools' parameter schema and the fingerprint a confirmation is checked against, so they
carry comments, never docstrings or field descriptions.
"""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool

from src.domains.proactive_discussions.context_store.filters import ContextFilters
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.domains.shared.discussion_sources import DiscussionValue


# MODEL-FACING (discussion tools): the context page the read tool asks for.
class DiscussionPageRequest(DiscussionValue):
    limit: Annotated[int, Field(ge=1, le=50)] = 30
    after_id: UUID | None = None
    after_exclusion_id: UUID | None = None
    filters: ContextFilters = Field(default_factory=ContextFilters)


# MODEL-FACING (discussion tools): the opening whose details the read tool asks for.
class DiscussionDetailsRequest(DiscussionValue):
    opening_id: UUID


# MODEL-FACING (discussion tools): a sparse change to the discussion settings.
class DiscussionPreferencesIntent(DiscussionValue):
    discussion_preferences: DiscussionPolicyPatch


# MODEL-FACING (discussion tools): one context item to exclude or allow again.
class DiscussionUseSelection(DiscussionValue):
    item_id: UUID
    usable: StrictBool


# MODEL-FACING (discussion tools): the usability change the action carries.
class DiscussionUseIntent(DiscussionValue):
    discussion_context_use: DiscussionUseSelection


# MODEL-FACING (discussion tools): the items to purge, or none for the whole context.
class DiscussionPurgeSelection(DiscussionValue):
    selection: Annotated[tuple[UUID, ...] | None, Field(min_length=1, max_length=100)] = None


# MODEL-FACING (discussion tools): the purge the action carries.
class DiscussionPurgeIntent(DiscussionValue):
    discussion_context_purge: DiscussionPurgeSelection


# MODEL-FACING (discussion tools): a rebuild request.
class DiscussionRebuildIntent(DiscussionValue):
    discussion_context_rebuild: Literal[True]


class DiscussionActionField(StrEnum):
    """The intents' field names: which discussion action a draft carries."""

    PREFERENCES = "discussion_preferences"
    USE = "discussion_context_use"
    PURGE = "discussion_context_purge"
    REBUILD = "discussion_context_rebuild"
