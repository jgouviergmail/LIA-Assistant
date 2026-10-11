"""Verify narrative meaning separately from exact-source bookkeeping.

One bounded review covers only complete facets admitted to publication. Its
receipt binds the candidate wording and exact proofs to the compiler policy;
no model work occurs during the SQL publication transaction.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from time import time
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from src.core.llm_config_helper import get_effective_context_window
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.journals.consolidation_output import (
    MaintenanceOutput,
    PortraitClaim,
    grounded_portraits,
    render_exact_evidence,
)
from src.domains.journals.constants import (
    JOURNAL_PORTRAIT_POLICY_VERSION,
    JOURNAL_PORTRAIT_REVIEW_MAX_INPUT_TOKENS,
)
from src.domains.journals.models import JournalEntry
from src.domains.journals.output_json import load_complete_json
from src.domains.journals.portrait_diagnostics import PortraitValidationError
from src.domains.journals.portrait_sources import PortraitSourceBundle
from src.infrastructure.cache.pricing_cache import capture_pricing_snapshot
from src.infrastructure.llm.output_truncation import is_output_truncated
from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.llm.usage_metadata import model_name_of_response
from src.infrastructure.proactive.tracking import settle_known_billing


@dataclass(frozen=True)
class PortraitReviewInput:
    evidence: list[dict[str, Any]]
    digest: str
    claims: tuple[PortraitClaim, ...] = ()


@dataclass(frozen=True)
class PortraitReviewReceipt:
    digest: str
    model: str
    reviewed_at: float
    reviewed_digest: str | None = None
    approved_indices: tuple[int, ...] | None = None
    rejected: tuple[dict[str, Any], ...] = ()

    def provenance(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "policy": JOURNAL_PORTRAIT_POLICY_VERSION,
            "digest": self.digest,
            "model": self.model,
            "reviewed_at": self.reviewed_at,
        }
        if self.reviewed_digest is not None:
            result.update(
                reviewed_digest=self.reviewed_digest,
                approved_indices=list(self.approved_indices or ()),
                rejected=list(self.rejected),
            )
        return result


class _ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: StrictInt = Field(ge=0)
    supported: StrictBool
    scope_preserved: StrictBool
    uncertainty_preserved: StrictBool
    synthesized: StrictBool


class _ReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviews: list[_ClaimReview] = Field(min_length=1, max_length=32)


def _unchanged_supports(output: MaintenanceOutput, claims: list[PortraitClaim]) -> None:
    changed = {action.entry_id for action in output.actions if action.entry_id}
    changed.update(
        str(identifier) for action in output.actions for identifier in action.merge_source_ids
    )
    if any(
        support.source.removeprefix("journal:") in changed
        for claim in claims
        for support in claim.supports
        if support.source.startswith("journal:")
    ):
        raise ValueError("Portrait supports must survive maintenance unchanged")


def prepare_portrait_review(
    output: MaintenanceOutput, entries: list[JournalEntry], sources: PortraitSourceBundle
) -> PortraitReviewInput | None:
    claims = output.portrait_claims or []
    admitted: list[PortraitClaim] = []
    grounded_portraits(claims, entries, sources.sections, published=admitted)
    _unchanged_supports(output, admitted)
    if not admitted:
        return None
    evidence = render_exact_evidence(admitted, entries, sources.sections)
    for item, claim in zip(evidence, admitted, strict=True):
        item["in_brief"] = claim.in_brief
    return PortraitReviewInput(evidence, _evidence_digest(evidence), tuple(admitted))


def _evidence_digest(evidence: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        {"policy": JOURNAL_PORTRAIT_POLICY_VERSION, "facets": evidence},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _review_selection(
    raw: str, candidate: PortraitReviewInput
) -> tuple[tuple[int, ...], tuple[dict[str, Any], ...]]:
    """A complete verdict selects only facets passing every semantic criterion."""
    try:
        result = _ReviewOutput.model_validate(load_complete_json(raw))
    except ValueError, TypeError:
        raise ValueError("Invalid portrait semantic review payload") from None
    indices = [review.index for review in result.reviews]
    if len(indices) != len(candidate.evidence) or set(indices) != set(range(len(indices))):
        raise ValueError("Incomplete or duplicate portrait semantic review")
    criteria = ("supported", "scope_preserved", "uncertainty_preserved", "synthesized")
    rejected = [
        {"claim_index": verdict.index, "criteria": failed}
        for verdict in sorted(result.reviews, key=lambda item: item.index)
        if (failed := [name for name in criteria if not getattr(verdict, name)])
    ]
    rejected_indices = {item["claim_index"] for item in rejected}
    approved = tuple(index for index in range(len(indices)) if index not in rejected_indices)
    if not approved:
        raise PortraitValidationError(
            "Portrait semantic review rejected the candidate",
            {"phase": "semantic_review", "rejected": rejected},
        )
    return approved, tuple(rejected)


def approve_portrait_review(raw: str, candidate: PortraitReviewInput) -> tuple[int, ...]:
    """Return only independently approved facets; an ambiguous verdict fails closed."""
    return _review_selection(raw, candidate)[0]


def reviewed_portrait(
    output: MaintenanceOutput,
    entries: list[JournalEntry],
    sources: PortraitSourceBundle,
    receipt: PortraitReviewReceipt | None,
) -> MaintenanceOutput:
    """Revalidate the reviewed batch and its exact, already budget-admitted subset."""
    candidate = prepare_portrait_review(output, entries, sources)
    if candidate is None:
        if receipt is not None:
            raise ValueError("Portrait publication lacks its exact semantic review")
        return output
    if receipt is None or (receipt.reviewed_digest or receipt.digest) != candidate.digest:
        raise ValueError("Portrait publication lacks its exact semantic review")
    indices = _approved_indices(receipt, len(candidate.claims))
    selected = output.model_copy(
        update={"portrait_claims": [candidate.claims[index] for index in indices]}
    )
    publication = prepare_portrait_review(selected, entries, sources)
    if publication is None or publication.digest != receipt.digest:
        raise ValueError("Portrait publication lacks its exact semantic review")
    return selected


def _approved_indices(receipt: PortraitReviewReceipt, size: int) -> tuple[int, ...]:
    indices = receipt.approved_indices
    if indices is None:
        indices = tuple(range(size))
    if (
        not indices
        or any(type(index) is not int for index in indices)
        or tuple(sorted(set(indices))) != indices
        or indices[0] < 0
        or indices[-1] >= size
    ):
        raise ValueError("Invalid portrait review selection")
    return indices


def require_portrait_review(
    output: MaintenanceOutput,
    entries: list[JournalEntry],
    sources: PortraitSourceBundle,
    receipt: PortraitReviewReceipt | None,
) -> None:
    reviewed_portrait(output, entries, sources, receipt)


def compact_review_evidence(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Repeated support passages are transmitted once, without losing metadata."""
    proofs: list[dict[str, Any]] = []
    identities: dict[str, int] = {}
    facets = []
    for item in evidence:
        refs = []
        for proof in item["supports"]:
            identity = json.dumps(proof, sort_keys=True, ensure_ascii=False)
            if identity not in identities:
                identities[identity] = len(proofs)
                proofs.append(proof)
            refs.append(identities[identity])
        facets.append(
            {**{k: v for k, v in item.items() if k != "supports"}, "support_indices": refs}
        )
    return {"proofs": proofs, "facets": facets}


def portrait_review_messages(
    evidence: list[dict[str, Any]], model: str, *, context_window: int | None = None
) -> list[Any]:
    """Bound the entire rendered request before any additional provider work."""
    system = str(load_prompt("journal_portrait_review_prompt"))
    content = json.dumps(compact_review_evidence(evidence), ensure_ascii=False)
    window = context_window if context_window is not None else get_effective_context_window(model)
    ceiling = min(JOURNAL_PORTRAIT_REVIEW_MAX_INPUT_TOKENS, window // 2)
    if OpenAITokenCounter().count(system + content, model) + 32 > ceiling:
        raise ValueError("Portrait semantic review input exceeds its complete-request budget")
    return [SystemMessage(content=system), HumanMessage(content=content)]


async def review_portrait(
    candidate: PortraitReviewInput,
    *,
    llm: Any,
    user_id: UUID,
    run_id: str,
    configured_model: str,
    requested_model: str,
    capture: TokenCaptureHandler,
    invoke: Callable[..., Awaitable[AIMessage]],
    persist: Callable[..., Coroutine[Any, Any, None]],
    context_window: int | None = None,
) -> PortraitReviewReceipt:
    """One review request with the operation's existing slot and spend ownership."""
    messages = portrait_review_messages(
        candidate.evidence, configured_model, context_window=context_window
    )
    started_at = time()
    pricing = capture_pricing_snapshot()
    checkpoint = len(capture.get_billing_records(configured_model))
    result: AIMessage | None = None
    try:
        result = await invoke(
            llm=llm,
            llm_type="journal_consolidation",
            messages=messages,
            user_id=str(user_id),
            config={"callbacks": [capture]},
        )
    finally:
        model = model_name_of_response(result) or configured_model
        if result is not None:
            capture.ensure_response_record(
                result,
                model_name=model,
                started_at=started_at,
                snapshot=pricing,
                known_calls_before=checkpoint,
            )
        await settle_known_billing(
            persist(
                user_id=str(user_id),
                session_id="consolidation",
                conversation_id=None,
                result=result,
                model_name=model,
                parent_run_id=run_id,
                node_name="journal_consolidation",
                duration_ms=(time() - started_at) * 1000,
                started_at=started_at,
                requested_model=requested_model,
                capture=capture,
                failed=result is None,
            )
        )
    if is_output_truncated(result):
        raise ValueError("Portrait semantic review was truncated")
    assert result is not None
    approved, rejected = _review_selection(result.text, candidate)
    evidence = [
        {**candidate.evidence[index], "index": position} for position, index in enumerate(approved)
    ]
    return PortraitReviewReceipt(
        _evidence_digest(evidence), model, started_at, candidate.digest, approved, rejected
    )
