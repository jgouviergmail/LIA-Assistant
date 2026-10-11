"""The source reset is shown explicitly; its execution clock is never invented by a model."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.core.constants import INTEREST_INITIAL_NEGATIVE_SIGNALS, INTEREST_INITIAL_POSITIVE_SIGNALS
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.interests.management_reactivation import InterestReactivationSnapshot


class InterestReactivateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interest_id: UUID


class InterestReactivationResult(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    status: Literal["active"]
    positive_signals: int
    negative_signals: int
    last_mentioned_at: Literal["execution_time"]
    last_notified_at: None
    dormant_since: None


def reactivation_result() -> InterestReactivationResult:
    return InterestReactivationResult(
        status="active",
        positive_signals=INTEREST_INITIAL_POSITIVE_SIGNALS,
        negative_signals=INTEREST_INITIAL_NEGATIVE_SIGNALS,
        last_mentioned_at="execution_time",
        last_notified_at=None,
        dormant_since=None,
    )


class InterestReactivationValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected: InterestReactivationSnapshot
    result: InterestReactivationResult


class InterestReactivationPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interest_to_reactivate: InterestReactivationValues


def canonical_interest_reactivation(draft: ApplicationActionDraftContent) -> bool:
    values = InterestReactivationPatch.model_validate(draft.intent).interest_to_reactivate
    return (
        values.result == reactivation_result()
        and draft.before == {"interest_to_reactivate": values.expected.model_dump(mode="json")}
        and draft.after == {"interest_to_reactivate": values.result.model_dump(mode="json")}
    )
