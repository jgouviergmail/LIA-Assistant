"""Approve source configuration and generation scope, without predicting model decisions."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.journals.removal_snapshot import JournalRemovalSnapshot


class JournalConsolidationField(StrEnum):
    REQUEST = "journal_consolidation"


class JournalConsolidationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Literal["current_account"]


class JournalConsolidationScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    corpus: JournalRemovalSnapshot = Field(repr=False)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    configuration: dict[str, JsonValue]

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            "scope": "current_account",
            "owned_entries": self.corpus.entries,
            "owned_chars": self.corpus.total_chars,
            "configuration": self.configuration,
        }


class JournalConsolidationPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    journal_consolidation: JournalConsolidationScope


def canonical_journal_consolidation(draft: ApplicationActionDraftContent) -> bool:
    scope = JournalConsolidationPatch.model_validate(draft.intent).journal_consolidation
    public = scope.public_scope()
    return draft.before == {"journal_consolidation": public} and draft.after == {
        "journal_consolidation": {**public, "requested": True}
    }
