"""What a context build reports about itself: its outcome and its counts, never content."""

from collections import Counter
from dataclasses import dataclass, field

from src.domains.proactive_discussions.context_store.schemas import ProposalRefusal
from src.domains.proactive_discussions.run_types import ContextOutcome
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceSnapshot

#: The outcomes after which nothing could be interpreted: a rebuild ending on one of
#: them built nothing, and says why instead of passing for done.
NOTHING_INTERPRETED: frozenset[ContextOutcome] = frozenset({"no_source", "no_fact", "prompt_full"})


@dataclass
class ContextTally:
    """The counts of one build, gathered as it reads, admits and interprets.

    Attributes:
        pages: The latest pages read, by status.
        facts_read: The facts those pages held.
        facts_admitted: Those the person's controls admitted.
        facts_offered: The facts sent to context calls, all passes together.
        facts_unclassified: Those a call left without a topic label: kept out of
            its pass, never read as unlabelled.
        context_calls: The context calls made.
        proposals: The proposals those calls returned, readable or not.
        proposals_refused: Those set aside, one by one: unreadable, or beyond what
            their evidence supports.
        research_refused: The research requests the policy or the pages refused.
        context_updates: The publications that moved the context's generation: a
            build that updated nothing interpreted facts whose checkpoints already
            held.
        items: The context items usable at the end of the build.
    """

    pages: Counter[str] = field(default_factory=Counter)
    facts_read: int = 0
    facts_admitted: int = 0
    facts_offered: int = 0
    facts_unclassified: int = 0
    context_calls: int = 0
    proposals: int = 0
    proposals_refused: int = 0
    research_refused: int = 0
    context_updates: int = 0
    items: int = 0

    def observe(
        self, snapshots: tuple[SourceSnapshot, ...], facts: tuple[DiscussionEvidence, ...]
    ) -> None:
        """Count the pages just merged and the facts they admitted.

        Args:
            snapshots: The pages the build holds now.
            facts: The facts admitted from them.
        """
        self.pages = Counter(page.status for page in snapshots)
        self.facts_read = sum(len(page.items) for page in snapshots)
        self.facts_admitted = len(facts)

    def count_proposals(
        self,
        readable: int,
        refused_reading: Counter[ProposalRefusal],
        refused_publication: Counter[ProposalRefusal],
    ) -> None:
        """Count one call's proposals and those set aside on the way to the store.

        Args:
            readable: The proposals its answer held once read.
            refused_reading: Those set aside while the answer was read.
            refused_publication: Those its publication could not admit.
        """
        self.proposals += readable + refused_reading.total()
        self.proposals_refused += refused_reading.total() + refused_publication.total()

    def as_dict(self) -> dict[str, object]:
        """The counts as stored on the run row and logged: numbers only."""
        return {
            "pages": dict(sorted(self.pages.items())),
            "facts_read": self.facts_read,
            "facts_admitted": self.facts_admitted,
            "facts_offered": self.facts_offered,
            "facts_unclassified": self.facts_unclassified,
            "context_calls": self.context_calls,
            "proposals": self.proposals,
            "proposals_refused": self.proposals_refused,
            "research_refused": self.research_refused,
            "context_updates": self.context_updates,
            "items": self.items,
        }
