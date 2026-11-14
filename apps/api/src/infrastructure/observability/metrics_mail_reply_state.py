"""Prometheus metrics for the reply state of listed mail (ADR-379).

The door that tells whether a listed message was answered fails OPEN: a mailbox that
cannot be read leaves a page without states, and nothing on the page says so. These are
what says it to the operator — how often the read fails, how long it takes (the time
budget is sized on it), and what it finds.
"""

from prometheus_client import Counter, Histogram

mail_reply_state_reads_total = Counter(
    "mail_reply_state_reads_total",
    "Reads of a listed page's conversations, to tell which messages were answered",
    # provider: the connector type of the mailbox
    # outcome: read | failed | timeout
    ["provider", "outcome"],
)

mail_reply_state_read_duration_seconds = Histogram(
    "mail_reply_state_read_duration_seconds",
    "Time one read of a listed page's conversations took, whatever its outcome",
    ["provider"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0),
)

mail_reply_states_total = Counter(
    "mail_reply_states_total",
    "Listed messages by the reply state decided for them",
    # status: answered | answer_drafted | unanswered | reply_received | awaiting_reply
    #         | unknown (nothing could be established)
    ["provider", "status"],
)
