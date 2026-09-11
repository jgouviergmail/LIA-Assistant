"""Metrics of the anticipated-moments sweep.

Two questions an operator asks about a proactive feature, and neither is
answerable from the application log:

- **is it finding anything?** ``detected`` against ``served`` says whether the
  scoring is too strict, and the skip reasons say which gate is the quiet one —
  « every account is at its daily ceiling » and « nothing qualified » look
  identical from the outside and mean opposite things.
- **is it on time?** A debrief served two hours after the meeting is not the
  feature; the latency histogram is what proves the sweep cadence is right.

``kind`` is bounded by ``MomentKind`` and ``outcome`` by the settled states plus
``MomentSkipReason`` — both closed vocabularies, so the label cardinality cannot
drift with the data.

A labelled counter that never fired exposes NO series, so the dashboard panels
reading these must carry ``or vector(0)`` and ``"noValue": "0"`` — otherwise an
operator reads « No data » where a green zero is the truth.
"""

from prometheus_client import Counter, Histogram

proactive_moments_total = Counter(
    "proactive_moments_total",
    "Anticipated moments, by kind and by what became of them.",
    ["kind", "outcome"],
    # outcome: detected | served | cancelled | expired
    #          | skipped_not_eligible | skipped_llm_skip | skipped_quota
    #          | skipped_revalidation_failed | skipped_dispatch_failed | error
)

proactive_moment_latency_seconds = Histogram(
    "proactive_moment_latency_seconds",
    "Seconds between a moment falling due and the notification going out.",
    buckets=(30, 60, 120, 300, 600, 1200, 1800, 3600),
)
