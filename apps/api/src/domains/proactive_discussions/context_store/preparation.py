"""Resolve model proposals against admitted source identities, never against model text."""

from collections import Counter
from datetime import datetime, timedelta
from uuid import UUID, uuid5

from src.core.config import settings
from src.domains.proactive_discussions.context_store.admission import observation_key, support_key
from src.domains.proactive_discussions.context_store.schemas import (
    ContextEvidenceLink,
    ContextItem,
    ContextProposal,
    ProposalRefusal,
)
from src.domains.proactive_discussions.contextualization.proposals import validate_pattern_proposal
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SensitiveTopic,
    SourceSnapshot,
)


class ProposalRefused(ValueError):
    """A model proposal its evidence cannot carry, refused under a named reason."""

    def __init__(self, code: ProposalRefusal, message: str) -> None:
        """Name why the proposal is refused.

        Args:
            code: The reason, in the refusals' closed vocabulary.
            message: What the check found, in fixed technical English.
        """
        super().__init__(message)
        self.code: ProposalRefusal = code


def proof_of(
    item: DiscussionEvidence, references: dict[str, DiscussionEvidence], *, now: datetime
) -> ContextEvidenceLink:
    """Build the body-free proof of one evidence, as it is stored and cited.

    Its retention is the source's own, capped by the configured context retention
    (a shorter one for peers and their messages); its supports are resolved to their
    identity keys.

    Args:
        item: The evidence.
        references: The admitted evidence by reference, to resolve supports.
        now: The current instant.

    Returns:
        The proof.
    """
    days = (
        settings.discussion_peer_context_retention_days
        if item.source.value in {"peers", "peer_messages"}
        else settings.discussion_context_retention_days
    )
    ceiling = now + timedelta(days=days)
    supports = tuple(
        sorted(
            {
                observation_key(references[ref]) if ref in references else support_key(ref)
                for ref in item.supports
            }
        )
    )
    return ContextEvidenceLink(
        root=observation_key(item),
        reference=item.reference,
        source=item.source,
        source_account=item.source_account,
        object_id=item.object_id,
        version=item.version,
        observed_at=item.observed_at,
        recorded_at=item.recorded_at,
        occurred_at=item.occurred_at,
        interval_start=item.interval_start,
        interval_end=item.interval_end,
        expires_at=min(item.expires_at, ceiling) if item.expires_at else ceiling,
        assertion=item.assertion,
        subject_id=item.subject_id,
        series_id=item.series_id,
        original_start=item.original_start,
        original_date=item.original_date,
        planned_date=item.planned_date,
        occurrence_state=item.occurrence_state,
        recurrence_rule=item.recurrence_rule,
        recurrence_spec=item.recurrence_spec,
        native_recurrence=item.native_recurrence,
        category=item.category,
        usage_nuance=item.usage_nuance,
        emotional_weight=item.emotional_weight,
        required_sources=item.required_sources,
        sensitive_topics=item.sensitive_topics,
        support_roots=supports,
    )


def prepare_item(
    owner_id: UUID,
    proposal: ContextProposal,
    references: dict[str, DiscussionEvidence],
    *,
    generation: int,
    revision: int,
    now: datetime,
    coverage: tuple[SourceSnapshot, ...] = (),
    timezone: str,
) -> ContextItem:
    """Turn a model proposal into a context item resting only on admitted evidence.

    Every reference must be admitted, the qualification must not exceed what its
    evidence supports, and a pattern must concern one subject. The item's id is
    stable for its kind and anchor, so the same understanding updates one item.

    Args:
        owner_id: The account.
        proposal: The model's proposal.
        references: The admitted evidence by reference.
        generation: The generation the item will belong to.
        revision: The item's revision.
        now: The current instant.
        coverage: The source pages read, which a recurrence must cover.
        timezone: The person's timezone, in which weekly patterns are judged.

    Returns:
        The prepared item.

    Raises:
        ProposalRefused: A reference is not admitted, the qualification is
            unsupported, or a pattern mixes subjects.
    """
    if not set(proposal.references) <= references.keys():
        raise ProposalRefused(
            "inadmissible_reference", "unresolved or inadmissible context evidence"
        )
    proofs = tuple(
        proof_of(references[reference], references, now=now).model_copy(
            update={
                "sensitive_topics": tuple(
                    sorted(
                        set(references[reference].sensitive_topics) | set(proposal.sensitive_topics)
                    )
                )
            }
        )
        for reference in proposal.references
    )
    try:
        validate_pattern_proposal(
            proposal,
            tuple(references[ref] for ref in proposal.references),
            coverage=coverage,
            timezone=timezone,
        )
    except ValueError as exc:
        raise ProposalRefused("unsupported_qualification", str(exc)) from exc
    subjects = {proof.subject_id for proof in proofs if proof.subject_id is not None}
    if proposal.kind == "pattern" and len(subjects) > 1:
        raise ProposalRefused("mixed_subjects", "incompatible subjects cannot form one pattern")
    root = observation_key(references[proposal.anchor])
    return ContextItem(
        id=uuid5(owner_id, f"{proposal.kind}:{root}"),
        kind=proposal.kind,
        summary=proposal.summary,
        qualification=proposal.qualification,
        revision=revision,
        generation=generation,
        proofs=proofs,
    )


def prepare_items(
    owner_id: UUID,
    proposals: tuple[ContextProposal, ...],
    references: dict[str, DiscussionEvidence],
    *,
    allowed_topics: frozenset[SensitiveTopic],
    generation: int,
    now: datetime,
    coverage: tuple[SourceSnapshot, ...] = (),
    timezone: str,
) -> tuple[tuple[ContextItem, ...], Counter[ProposalRefusal]]:
    """Prepare each proposal on its own: one its evidence cannot carry is set aside alone.

    A proposal touching a topic the person refused, resting on evidence no longer
    admitted, qualified beyond what its evidence supports, or making an item another
    proposal of the same pass already makes is refused and counted; the others are
    prepared, whatever model wrote them (ADR-343's doctrine: never the batch).

    Args:
        owner_id: The account.
        proposals: The model's proposals, in order.
        references: The admitted evidence by reference.
        allowed_topics: The sensitive topics the person allowed.
        generation: The generation the items will belong to.
        now: The current instant.
        coverage: The source pages read, which a recurrence must cover.
        timezone: The person's timezone, in which weekly patterns are judged.

    Returns:
        The prepared items, one per stable id (the first proposal making it wins),
        and why each other proposal was set aside.
    """
    items: dict[UUID, ContextItem] = {}
    refused: Counter[ProposalRefusal] = Counter()
    for proposal in proposals:
        if not set(proposal.sensitive_topics) <= allowed_topics:
            refused["refused_topic"] += 1
            continue
        try:
            item = prepare_item(
                owner_id,
                proposal,
                references,
                generation=generation,
                revision=1,
                now=now,
                coverage=coverage,
                timezone=timezone,
            )
        except ProposalRefused as exc:
            refused[exc.code] += 1
            continue
        if item.id in items:
            refused["duplicate_item"] += 1
            continue
        items[item.id] = item
    return tuple(items.values()), refused


def same_meaning(old: ContextItem, new: ContextItem) -> bool:
    """Whether two versions of an item say the same thing.

    Revision, generation, read time and retention are ignored.

    Args:
        old: The stored version.
        new: The prepared version.

    Returns:
        True when nothing the item states changed.
    """

    def semantic(item: ContextItem) -> dict[str, object]:
        values = item.model_dump(mode="json", exclude={"revision", "generation"})
        values["proofs"] = [
            proof.model_dump(mode="json", exclude={"observed_at", "expires_at"})
            for proof in item.proofs
        ]
        return values

    return semantic(old) == semantic(new)
