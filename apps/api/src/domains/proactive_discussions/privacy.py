"""ADR-357 for discussion openings: an SMS a run read makes its opening private to LIA.

The rule is independent of what the decision cites. A run that READ an SMS — as a
fact or through a context item resting on one — offered it to a model call, and
the opening that call shaped is private: the push is masked, no external channel
forwards it, Radio never airs it, and no later decision window offers its wording
back (``relevant_opening_history``).
"""

from collections.abc import Iterable

from src.domains.proactive_discussions.context_store.schemas import ContextItem
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey

#: Archive metadata key written with the opening and read by the history window.
DISCUSSION_SMS_CONTEXT_FIELD = "discussion_sms_context"


def _rests_on_sms(source: SourceKey, required: Iterable[SourceKey]) -> bool:
    return source is SourceKey.SMS or SourceKey.SMS in required


def sms_in_context(facts: Iterable[DiscussionEvidence], knowledge: Iterable[ContextItem]) -> bool:
    """Whether a model context carries SMS content, directly or derived.

    Args:
        facts: Every source item the run read and could offer to a model.
        knowledge: The derived context items the run offered.

    Returns:
        True when a fact comes from (or depends on) the SMS source, or when a
        context item rests on such a proof.
    """
    return any(_rests_on_sms(fact.source, fact.required_sources) for fact in facts) or any(
        _rests_on_sms(proof.source, proof.required_sources)
        for item in knowledge
        for proof in item.proofs
    )
