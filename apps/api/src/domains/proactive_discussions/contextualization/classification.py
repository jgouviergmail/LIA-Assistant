"""A context pass classifies only evidence it actually saw, with restrictive labels only."""

from src.domains.proactive_discussions.llm_contracts import ContextInterpretation
from src.domains.shared.discussion_sources import DiscussionEvidence, SensitiveTopic


def classified_evidence(
    output: ContextInterpretation, offered: tuple[DiscussionEvidence, ...]
) -> tuple[DiscussionEvidence, ...]:
    """Apply a context call's topic classifications to the evidence it was shown.

    Labels only add topics, whatever model wrote them: a reference classified twice
    takes both labels, and a classification of a reference the call was not shown is
    ignored. An offered reference the call left unclassified leaves the pass: never
    read as unlabelled, it is neither interpreted nor checkpointed, so a later pass
    offers it again. One forgotten label used to refuse the whole answer, and the run.

    Args:
        output: The context call's output.
        offered: The evidence the call was shown.

    Returns:
        The offered evidence the call classified, in offered order, each with its
        classified topics added.
    """
    labels: dict[str, set[SensitiveTopic]] = {}
    for classification in output.classifications:
        labels.setdefault(classification.reference, set()).update(classification.sensitive_topics)
    return tuple(
        item.model_copy(
            update={
                "sensitive_topics": tuple(
                    sorted(set(item.sensitive_topics) | labels[item.reference])
                )
            }
        )
        for item in offered
        if item.reference in labels
    )
