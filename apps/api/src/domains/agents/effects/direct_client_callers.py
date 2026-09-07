"""Which modules reach an external service WITHOUT going through a tool.

The consultation register is filled by one place — the tool gate. A module that
imports a client from ``domains/connectors/clients`` and calls it directly
bypasses that gate entirely, so the capability it used is recorded nowhere.

The consequence is not abstract, and it is not a corner case: **the same Brave
search is recorded when a person asks for it in a conversation and silent when
LIA runs it alone** (owner correction, 2026-09-07, on the interest sweep).

Finding those one at a time is what this whole programme keeps failing at. The
briefing, the relationship debrief, the heartbeat sweep and the interest sweep
were each discovered by someone noticing an absence — four times, the same
family. So the family is enumerated instead: every module outside the tool
layer that imports a client declares which of three things it is.

- :data:`CLIENT_CALL_RECORDERS` — it reads, and it records; the value names the
  surface that does.
- :data:`NOT_A_CAPABILITY_READ` — it touches a client without reading anyone's
  data (a registry object, a teardown, a subscription renewal), with the
  reason written out.
- :data:`AWAITING_RECORDING` — it DOES read and does NOT record yet. This is a
  declared debt, not an exemption: the register is knowingly incomplete here,
  and the guard counts it rather than letting it hide. Emptying this table is
  the point.

``AWAITING_RECORDING`` is deliberately uncomfortable. A silent gap reads as
« nobody thought about it »; a named one reads as « we know, and it is
measured » — which is the only honest state between finding a defect and
fixing it.
"""

from __future__ import annotations

from typing import Final

#: Reads, and records. The value is the surface key of
#: :data:`CONSULTATION_SURFACES`, or ``"tool gate"`` when the module's calls
#: reach the register through a tool after all.
CLIENT_CALL_RECORDERS: Final[dict[str, str]] = {
    # In a TURN, through ``record_treatment``: the authorship is whatever set
    # the turn in motion, so these declare a capability rather than a surface
    # (``IN_TURN_CAPABILITIES``).
    "domains/agents/services/knowledge_enrichment_service.py": "in-turn",
    "domains/agents/services/planner/hue_discovery.py": "in-turn",
    "domains/briefing/fetchers.py": "briefing",
    "domains/rag_spaces/drive_ingest.py": "space",
    "domains/rag_spaces/drive_sync.py": "space",
    "domains/rag_spaces/mail_source_service.py": "space",
    "domains/users/geocoding.py": "profile",
    "infrastructure/scheduler/heartbeat_wake_sweep.py": "wake",
    "domains/heartbeat/context_aggregator.py": "heartbeat",
    "domains/heartbeat/context_sources.py": "heartbeat",
    "domains/interests/services/content_sources/brave_source.py": "interest",
    "domains/interests/services/content_sources/perplexity_source.py": "interest",
    "domains/interests/services/content_sources/wikipedia_source.py": "interest",
}

#: Touches a client without reading anyone's data. Each entry is an argument,
#: never a convenience: it must say what the module does with the client.
NOT_A_CAPABILITY_READ: Final[dict[str, str]] = {
    "domains/agents/api/service.py": (
        "Holds a ClientRegistry to hand clients to the agents; it opens no "
        "connector itself, and every tool it serves is gated."
    ),
    "domains/relations/providers/client.py": (
        "The 360° assembly's own client factory. What it fetches is recorded "
        "by the relation_debrief surface, at the assembly that asked for it."
    ),
    "domains/telephony/availability.py": (
        "Reads whether the telephony provider is reachable — the deployment's "
        "own configuration, never the person's data."
    ),
    "domains/push_channels/sync.py": (
        "Registers and renews Google push WATCH subscriptions. It tells "
        "Google where to send change notices; it fetches no content, and the "
        "read those notices trigger is recorded by whoever performs it."
    ),
    "domains/meetings/enrichment.py": (
        "Turns coordinates the recording already carried into a place name. "
        "The upload is the read, and it is the person's own."
    ),
    "domains/agents/utils/email_enricher.py": (
        "Borrows the Gmail client's PARSER (``_extract_body_recursive``) on a "
        "payload the turn already holds. Verified 2026-09-07: not one call "
        "leaves the process — it opens no connection and fetches nothing. It "
        "was first listed as a read on the strength of its import alone, "
        "which is the very shortcut this table exists to replace."
    ),
    "domains/rag_spaces/mail_render.py": (
        "Borrows two STATIC parsers from the Gmail client to turn a thread "
        "resource it was handed into a document. Its own docstring says it: "
        "« Pure: no session, no client, no clock ». Verified 2026-09-07, not "
        "one call leaves the process — the second module listed as a read on "
        "the strength of its import alone."
    ),
    "infrastructure/security/web_risk.py": (
        "Imports the Google API COUNTER, not a client: it accounts for calls " "someone else made."
    ),
    "infrastructure/startup/shutdown.py": (
        "Closes the shared geocoding client at teardown. Opening nothing is "
        "the whole point of this module."
    ),
}

#: Reads the person's data and does NOT record it yet. Measured 2026-09-07.
#: Each entry says WHAT is read, so the debt is legible rather than a name on
#: a list. Emptying this table is the work; hiding it would be the defect.
AWAITING_RECORDING: Final[dict[str, str]] = {}


__all__ = [
    "AWAITING_RECORDING",
    "CLIENT_CALL_RECORDERS",
    "NOT_A_CAPABILITY_READ",
]
