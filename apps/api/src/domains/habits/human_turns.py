"""The ONE definition of a human turn for every durable habits source.

``product_outcomes`` records one row per finalized run with the channel as a
first-class column (``domains/product/constants.py::derive_channel``): a run
the user typed (web, PWA, Telegram) is ``web``; a scheduled action is
``scheduler``; the public showroom is ``web_showroom``. Unlike
``message_token_summary`` — which the conversation reset deletes, so the
primary account showed 5 human rows in 56 days for 235 real turns — the
outcome row survives a reset.

Two readers share this predicate: the rhythm repository (activity hours) and
the recurrence-ledger seed. A second wording of "human" in either is the
drift class ADR-255 named: two readings of one declaration always diverge —
the previous seed read "no token summary" as "human" and rebuilt LIA's own
scheduled routines as the user's recurrences (measured 2026-09-03: email 27
days, event 26, weather 26, web_search 27, for 5 typed turns).

The vocabulary comes from the product domain and is pinned by
``tests/unit/domains/habits/test_human_turns.py`` against ``CHANNELS`` and
``RESULT_TYPES`` — never re-declared here.
"""

from __future__ import annotations

#: Channels a human sits behind. ``web`` covers the browser, the PWA, the
#: native shells and the Telegram channel (``derive_channel`` maps every
#: non-scheduler session to it); ``web_showroom`` is the credential-less
#: public demonstrator and ``unknown`` carries no attribution — neither is a
#: user's own presence.
HUMAN_OUTCOME_CHANNELS: frozenset[str] = frozenset({"web"})

#: Result types a typed turn produces. ``automation_run`` is the scheduler's;
#: the finer types (``preparation``, ``artifact``, ``proactive_item``,
#: ``project_progress``) are reserved for surfaces that do not exist yet and
#: must be added here the day one of them is written by a human turn.
HUMAN_OUTCOME_RESULT_TYPES: frozenset[str] = frozenset({"answer", "action"})

#: SQL fragment over an alias ``po`` of ``product_outcomes``. Values are
#: inlined as literals on purpose: they are code-owned vocabulary, not user
#: input, and a bound parameter would let a caller widen the predicate.
HUMAN_OUTCOME_PREDICATE_SQL: str = (
    "po.channel IN ("
    + ", ".join(f"'{channel}'" for channel in sorted(HUMAN_OUTCOME_CHANNELS))
    + ") AND po.result_type IN ("
    + ", ".join(f"'{result_type}'" for result_type in sorted(HUMAN_OUTCOME_RESULT_TYPES))
    + ")"
)
