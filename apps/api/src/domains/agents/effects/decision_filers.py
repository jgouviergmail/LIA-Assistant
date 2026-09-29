"""Who files each accounted run in the decision register — declared, never inferred.

The decision register holds one row per turn: the spine the ledger, the actions
and the consultations hang off, all filed under a ``run_id``. A surface that
calls a model outside the conversation graph opens an accounting of its own —
a ``TrackingContext``, or ``out_of_turn_spend`` around a whole act — and its
run reaches the register only if something files it. Joining the ledger to the
register by run on dev (2026-09-27, twelve days) found runs nobody filed: 47
radio sessions, 5 article translations, 84 journal consolidations — plus a
reflection billed twice and a heartbeat's skip filed apart from the sweep that
read for it (ADR-263 amendment 2026-09-27). Each was found by reading one family of run
ids at a time, which is not a method.

So every module that opens an accounting is listed here: with the modules that
file its run's row — each one checked by the guard to call a decision door
(``record_decision``, ``record_decision_once``, ``decision_recorder``) — or, in
``NOT_A_TURN``, with the reason its run is no turn. The guard walks the AST of
``src/``, so a new accounting cannot ship without answering the question, and a
declaration for a module that opens none fails too.

The register's own rule still holds: no model spend, no turn. A proactive sweep
that concluded without calling a model files nothing (its reads are in the
consultation register); a surface filed here files its run once a model was
called.
"""

from __future__ import annotations

from typing import Final

_CHAT_TURN: Final[str] = "domains/agents/api/service.py"
_OUT_OF_TURN_FUNNEL: Final[str] = "infrastructure/proactive/tracking.py"
_VOICE_SESSION: Final[str] = "infrastructure/scheduler/voice_session_closing.py"

#: Each module opening an accounting, and the modules that file its run's row.
DECISION_FILERS: Final[dict[str, tuple[str, ...]]] = {
    # The chat turn: ``decision_recorder`` wraps the stream it accounts for.
    "domains/agents/api/service.py": (_CHAT_TURN,),
    "domains/agents/services/conversation_orchestrator.py": (_CHAT_TURN,),
    # The learning passes bill under their caller's run — a turn, or a voice
    # session whose closing files it.
    "domains/agents/services/memory_extractor.py": (_CHAT_TURN, _VOICE_SESSION),
    "domains/interests/services/extraction_service.py": (_CHAT_TURN, _VOICE_SESSION),
    # A turn's journal extraction, or a consolidation (its own run, filed there).
    "domains/journals/extraction_service.py": (
        _CHAT_TURN,
        "domains/journals/consolidation_service.py",
    ),
    # A voice lookup, under the phone call's or the live session's run.
    "domains/agents/telephony/live_tools.py": (_VOICE_SESSION,),
    "infrastructure/scheduler/voice_session_closing.py": (_VOICE_SESSION,),
    # A billed image, joined to the act that showed it — a turn, or the cards.
    "domains/connectors/media_attribution.py": (_CHAT_TURN, "domains/briefing/service.py"),
    "domains/briefing/service.py": ("domains/briefing/service.py", _OUT_OF_TURN_FUNNEL),
    # The out-of-turn funnel files what it bills, and the surfaces that open an
    # accounting around a whole act bill their model calls through it.
    "infrastructure/proactive/tracking.py": (_OUT_OF_TURN_FUNNEL,),
    "infrastructure/proactive/runner.py": (_OUT_OF_TURN_FUNNEL,),
    "domains/meetings/enrichment.py": (_OUT_OF_TURN_FUNNEL,),
    # Native selection shares the meeting run. Its finalizer also files failed
    # synthesis attempts that never reached the normal completion funnel.
    "infrastructure/llm/jev_runtime.py": (
        _OUT_OF_TURN_FUNNEL,
        "domains/meetings/native_spend.py",
    ),
    # The personal radio: a session, and each article translated on opening.
    "domains/radio/adapters.py": ("domains/radio/register.py",),
    "domains/radio/articles.py": ("domains/radio/register.py",),
}

#: Modules opening an accounting whose run is no turn, and why.
NOT_A_TURN: Final[dict[str, str]] = {
    "domains/users/geocoding.py": (
        "Geocodes the address the person saved in their profile: a billed Maps "
        "lookup with no model in it, whose euros are traced under a run of their "
        "own like every other family the ledger holds."
    ),
    "domains/voice/text_readout.py": (
        "Reads aloud a text the person chose to hear: a speech synthesis of words "
        "already written, with no model deciding anything, billed under a run of "
        "its own."
    ),
    "infrastructure/llm/embedding_context.py": (
        "Bills an embedding under the run its caller declared — a turn, a "
        "consolidation, a session — and under a run of its own only for an "
        "indexing batch no act encloses (a knowledge-space document being "
        "processed), which is processing, not a decision."
    ),
    "infrastructure/scheduler/condition_evaluators.py": (
        "Checks whether a routine's condition is met: it reads the source the "
        "condition names and calls no model; the run it may trigger is a routine "
        "turn of its own, filed by the conversation it runs in."
    ),
}


__all__ = ["DECISION_FILERS", "NOT_A_TURN"]
