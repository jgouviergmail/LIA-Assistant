"""Prometheus metrics for sending a file or an answer by e-mail (ADR-321).

A send is the person's explicit act, so its outcome is SAID to them on the spot;
this counter is what tells the operator how the roads behave — a mailbox that
keeps refusing, a relay that fails, files larger than a road accepts.
"""

from prometheus_client import Counter

email_shares_total = Counter(
    "email_shares_total",
    "Generated files and answers sent by e-mail from the chat or the gallery",
    # route: mailbox | relay | none
    # outcome: sent | too_large | file_gone | no_recipient | recipients_locked |
    #          unavailable | reconnect | refused | failed
    ["route", "outcome"],
)
