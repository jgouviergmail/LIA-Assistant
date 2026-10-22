"""Complete canonical instruction snapshot, separate from factual memory retrieval."""

from html import escape
from uuid import UUID

from pydantic import StrictBool

from src.domains.shared.discussion_sources import DiscussionValue, NonEmpty


class DirectiveBudgetExceeded(ValueError):
    """No model may run with a silently incomplete instruction snapshot."""


class DirectiveRule(DiscussionValue):
    """One procedural memory the person stated: its text, nuance and trigger topic."""

    id: UUID
    text: str
    usage_nuance: str
    trigger_topic: str


class DirectiveSnapshot(DiscussionValue):
    """Every procedural rule a run must read, and the revision naming that set."""

    owner_id: UUID
    enabled: StrictBool
    revision: NonEmpty
    rules: tuple[DirectiveRule, ...]

    def prompt_text(self) -> str:
        """Render the rules as escaped rule blocks for the prompt."""
        return render_directives(self.rules)


def render_directives(rules: tuple[DirectiveRule, ...]) -> str:
    """Render rules as escaped ``<rule id>`` blocks, one per rule.

    Args:
        rules: The rules.

    Returns:
        The blocks, one per line group.
    """
    return "\n".join(
        f'<rule id="{rule.id}">{escape(rule.text)}\n{escape(rule.usage_nuance)}\n{escape(rule.trigger_topic)}</rule>'
        for rule in rules
    )
