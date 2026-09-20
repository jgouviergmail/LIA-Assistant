"""Which out-of-turn surfaces read the person's data, and where they say so.

``record_treatment`` fires from exactly one place — the tool gate. A capability
that is not a tool therefore records nothing, and three surfaces were found
that way, one after another, each by a person noticing something missing rather
than by a test:

- the **briefing**, nine sources through direct fetchers;
- the **relationship debrief**, seven, whose absence made a reader take a
  neighbouring row for their own (reported 2026-09-07);
- the **heartbeat sweep**, sixteen — 824 runs over thirty days, not one row,
  and the one case where nobody can reconstruct what was read.

Finding them one at a time is not a method. This registry is: every surface
that spends out of turn declares whether it opens the person's data and, when
it does, the module that records it. The guard reads the funnel's call sites —
an enumerable, complete list — so a fourteenth surface cannot be added without
answering the question.

``NOT_A_READER`` is not an escape hatch: it carries a written reason, and it
means « this surface writes, translates or summarises what it was handed », not
« nobody checked ».
"""

from __future__ import annotations

from typing import Final

#: Surfaces that open the person's sources, and the module that records it.
#: The guard asserts each named module actually calls the recording function —
#: a pointer to a module that records nothing would certify a gap.
CONSULTATION_RECORDERS: Final[dict[str, str]] = {
    "briefing": "domains/briefing/service.py",
    "relation_debrief": "domains/relations/overview/consultations.py",
    "heartbeat": "domains/heartbeat/consultations.py",
    "interest": "domains/interests/services/content_sources/content_generator.py",
    "space": "domains/rag_spaces/consultations.py",
    "wake": "infrastructure/scheduler/heartbeat_wake_sweep.py",
    "profile": "domains/users/geocoding.py",
    # The dial path opens the calendar for the free/busy projection (and, for
    # an owner call, the context sections of lot 4); the return synthesis that
    # spends under the same task type reads nothing of its own. A live lookup
    # DURING the call (lot 7, ``agents/telephony/live_tools.py``) files on the
    # same surface through the same door.
    "phone_call": "domains/telephony/service.py",
    # A DIRECT live session (ADR-300 wave 4) reads through the phone's own
    # door: the context block at the start and every lookup during the
    # session are filed on the ``live_session`` surface by the shared runner.
    "live_session": "domains/agents/telephony/live_tools.py",
    "moment": "infrastructure/scheduler/moment_sweep.py",
}

#: Surfaces that spend out of turn WITHOUT opening the person's sources, and
#: why. Each writes, translates or summarises material it was handed by the
#: turn or the caller that already recorded the read.
NOT_A_READER: Final[dict[str, str]] = {
    "interest_subject_clustering": (
        "Re-labels interests already in hand — a maintenance pass over rows "
        "the interest surface fetched, not a new read."
    ),
    "open_loop_extraction": (
        "Reads the conversation that has just happened, inside the turn that "
        "produced it; the turn's own tools recorded what they consulted."
    ),
    "meeting": (
        "Transcribes and structures a recording the person uploaded. The "
        "upload is the read, and it is theirs."
    ),
    "psyche_summary": (
        "Summarises the psychological profile the assistant already keeps; it "
        "opens no connector and no mailbox."
    ),
    "peer_message": (
        "Composes the wording of a message the sender already asked to send; "
        "the recipient's data is never opened."
    ),
    "reminder": (
        "Writes the notification text for a reminder the person created. The "
        "reminder is their own instruction, held by us."
    ),
    "mcp_description": (
        "Describes a server from the tool list that server published — the "
        "third party's own metadata, not the person's data."
    ),
}


__all__ = ["CONSULTATION_RECORDERS", "NOT_A_READER"]
