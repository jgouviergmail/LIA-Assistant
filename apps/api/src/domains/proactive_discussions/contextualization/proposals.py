"""Keep persisted pattern qualifications within the actual evidence's authority."""

from src.domains.proactive_discussions.context_store.schemas import ContextProposal
from src.domains.proactive_discussions.contextualization.patterns import qualify_pattern
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey, SourceSnapshot


def validate_pattern_proposal(
    proposal: ContextProposal,
    facts: tuple[DiscussionEvidence, ...],
    *,
    coverage: tuple[SourceSnapshot, ...] = (),
    timezone: str,
) -> None:
    """Refuse a qualification its evidence does not support.

    A fact's qualification may not upgrade its source's authority; a declaration
    needs a native recurrence or an exact first-party quote; a contradiction needs
    a cancelled occurrence or a quote. A pattern is declared only on a native
    recurrence or a quote, observed only over complete coverage, and possible only
    on independent positive evidence.

    Args:
        proposal: The model's proposal.
        facts: The evidence it cites.
        coverage: The source pages read, which an observed recurrence must cover.
        timezone: The person's timezone, in which recurrence is judged.

    Raises:
        ValueError: The qualification exceeds what the evidence supports.
    """
    if proposal.kind != "pattern":
        _validate_fact_qualification(proposal, facts)
        return
    pattern = qualify_pattern(facts, coverage=coverage, timezone=timezone)
    if proposal.qualification == "declared":
        if pattern.basis == "declared" or _quoted_declaration(proposal, facts):
            return
        raise ValueError("declared pattern needs native recurrence or explicit human declaration")
    if proposal.qualification == "observed" and pattern.basis != "observed":
        raise ValueError("observed recurrence needs qualified complete occurrence coverage")
    if proposal.qualification == "possible" and pattern.basis == "insufficient":
        raise ValueError("possible recurrence needs independent positive evidence")
    if proposal.qualification == "contradicted" and not _quoted_declaration(proposal, facts):
        raise ValueError("contradicted recurrence needs an explicit positive statement")


def _validate_fact_qualification(
    proposal: ContextProposal, facts: tuple[DiscussionEvidence, ...]
) -> None:
    assertions = {fact.assertion for fact in facts}
    if proposal.qualification in {"reported", "observed", "planned"} and assertions != {
        proposal.qualification
    }:
        raise ValueError("context qualification cannot upgrade its source authority")
    if proposal.qualification == "declared" and not (
        _quoted_declaration(proposal, facts)
        or qualify_pattern(facts, coverage=(), timezone="UTC").basis == "declared"
    ):
        raise ValueError("declaration needs an explicit native or first-party statement")
    if proposal.qualification == "contradicted" and not (
        any(fact.occurrence_state == "cancelled" for fact in facts)
        or _quoted_declaration(proposal, facts)
    ):
        raise ValueError("contradiction needs positive native or first-party evidence")


def _quoted_declaration(proposal: ContextProposal, facts: tuple[DiscussionEvidence, ...]) -> bool:
    quote = proposal.declaration_quote
    return bool(
        quote
        and any(
            fact.source in {SourceKey.MEMORIES, SourceKey.CONVERSATIONS}
            and fact.assertion == "reported"
            and quote in fact.excerpt
            for fact in facts
        )
    )
