"""Preserve established reset counters, publishing only committed first attempts."""

from src.infrastructure.observability.metrics import conversation_length_messages
from src.infrastructure.observability.metrics_agents import conversation_resets_total
from src.infrastructure.observability.metrics_business import (
    conversation_abandonment_at_message_count,
    conversation_abandonment_total,
    conversation_tokens_total,
)


def record_reset(message_count: int, total_tokens: int) -> None:
    """A replay or rollback records nothing; a zero-message reset still counts once."""
    conversation_resets_total.inc()
    if message_count <= 0:
        return
    conversation_length_messages.observe(message_count)
    if total_tokens > 0:
        conversation_tokens_total.labels(agent_type="generic").observe(total_tokens)
    conversation_abandonment_total.labels(
        abandonment_reason="user_reset", agent_type="generic"
    ).inc()
    conversation_abandonment_at_message_count.labels(abandonment_reason="user_reset").observe(
        message_count
    )
