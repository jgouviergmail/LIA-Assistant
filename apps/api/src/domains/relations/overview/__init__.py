"""The 360° evidence assembly — one implementation, several consumers.

Everything LIA holds about ONE person, under the scope the user declared on the
relationship card: the database-local half (open commitments, calls, relayed
messages, memories) and the provider-backed half (contact card, mail, meetings),
each with its own failure boundary and the list of what could not be read.

It lived inside ``agents/tools/person_tools`` while the 360° tool was its only
consumer. The daily relationship debrief needs the same answer, and a second
implementation would let two surfaces disagree about who someone is and what was
read about them — the defect class ADR-185 exists to prevent.
"""

from src.domains.relations.overview.evidence import (
    OverviewEvidence,
    OverviewEvidenceUnavailable,
    build_overview_evidence,
    overview_payload,
)

__all__ = [
    "OverviewEvidence",
    "OverviewEvidenceUnavailable",
    "build_overview_evidence",
    "overview_payload",
]
