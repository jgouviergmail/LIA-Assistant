"""What each direct-read surface consults, declared once for every reader.

``record_treatment`` fires from exactly one place — the tool gate — so a
capability that is not a tool records nothing. Three surfaces read the person's
sources through direct calls (the briefing, the relationship debrief, the
heartbeat sweep), and each was given the same three pieces BY HAND: a prefix, a
section-to-domain table, and a recording loop.

Three copies of one shape is how they drifted, and the drift was measured
2026-09-07, on this codebase, after the fix that created them:

- the register kept a THIRD copy of all thirty-one names, hand-transcribed into
  ``TREATMENT_DOMAIN_OVERRIDES``;
- two tables written to bridge that gap — ``HEARTBEAT_DOMAIN_OVERRIDES`` and
  ``DEBRIEF_DOMAIN_OVERRIDES`` — were exported and read by NOBODY;
- the boot guard walked ``get_all_tools()`` only, so not one of the thirty-one
  was checked where every other completeness rule is checked;
- one surface guarded its capabilities against orphans, the other two did not;
- one wrapped its recording, the other two did not;
- and the authorship each row carries was a free string typed at three call
  sites, checked by a guard that only ever read two other doors.

So the vocabulary is declared HERE, once, and everyone reads it: each surface
for its own names, the register for its domain table, one recorder for the
writing, and one guard for all of them. A fourth surface adds an entry and
inherits the whole net.

**This module imports nothing outside its own package**, and that is the same
rule :mod:`src.domains.shared.consultation_sink` follows: the register lives in
``domains/agents/effects``, ``agents`` already imports ``relations``
(ADR-269), and the coupling ratchet counts LOCAL imports too — so a feature
domain reaching either way would close a cycle that hiding the import inside a
function would only make harder to see. ``source`` is therefore a plain string
here and the guard, which may import both sides, is what refuses a value
:class:`~src.domains.agents.effects.models.EffectSource` cannot emit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

import structlog

from src.domains.shared.consultation_sink import record_consultation

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ConsultationSurface:
    """One surface that opens the person's sources without going through a tool.

    Attributes:
        key: How the surface names itself out of turn — the same key
            ``user_data_readers.CONSULTATION_RECORDERS`` uses, so the registry
            of readers and the registry of vocabularies cannot name two
            different sets.
        prefix: What every capability of this surface starts with, so the
            register tells them apart from tool names without matching each.
        source: The authorship every row of this surface carries. Declared once
            rather than typed at each call site: it is a property of the
            surface (nobody schedules a briefing; nobody asks for a sweep), not
            a decision the recording loop gets to make.
        domains: Each section, and the taxonomy noun the register headlines it
            with.
    """

    key: str
    prefix: str
    source: str
    domains: Mapping[str, str]

    def __post_init__(self) -> None:
        """Freeze the table for real.

        ``frozen=True`` protects the ATTRIBUTE, never what it points at: a
        plain dict here stays writable, and this one is a module-level global
        the register reads. One stray write and the register's table says
        something the surface never declared — the exact silence this module
        exists to end.
        """
        object.__setattr__(self, "domains", MappingProxyType(dict(self.domains)))

    def capability(self, section: str) -> str:
        """The register name of one section.

        Args:
            section: Section key, as this surface names it.

        Returns:
            The bounded capability name, e.g. ``briefing:mails``.
        """
        return f"{self.prefix}{section}"

    def capabilities(self) -> dict[str, str]:
        """This surface's capability-to-domain table.

        Returns:
            ``{"briefing:mails": "email", ...}``.
        """
        return {self.capability(section): domain for section, domain in self.domains.items()}


#: Every surface that reads through direct calls, and the vocabulary it uses.
#: Keys match ``user_data_readers.CONSULTATION_RECORDERS`` exactly; the guard
#: refuses a surface declared in one and absent from the other.
CONSULTATION_SURFACES: Final[Mapping[str, ConsultationSurface]] = {
    # The briefing answers a REQUEST: nothing schedules it — verified on the
    # call graph 2026-09-07, it is reached only from ``GET /briefing/*`` and
    # from chat suggestions. Filing it as an initiative would credit LIA with
    # page loads it never chose to make.
    #
    # Each section reads as the domain of the source it opened — owner
    # arbitration 2026-09-07, on a real screen: « Météo » for the weather card
    # is what the reader expects, because the detail line already says
    # ``briefing:weather`` and the two together say « the briefing opened your
    # weather ». ``for_you`` gathers open loops and automation runs, which is
    # what ``automation`` names.
    "briefing": ConsultationSurface(
        key="briefing",
        prefix="briefing:",
        source="user",
        domains={
            "weather": "weather",
            "agenda": "event",
            "mails": "email",
            "birthdays": "contact",
            "reminders": "reminder",
            "health": "health",
            "for_you": "automation",
            "tasks": "task",
            "documents": "document",
        },
    ),
    # The reader opened the card; the debrief answers that view — the same
    # authorship as the briefing, and the reason both stay in the two main
    # lists rather than moving to a tab their owner never opens.
    #
    # ``open_loops`` and ``peer_messages`` both read as ``peer``, which is what
    # ``get_open_loops_tool`` already resolves to: one vocabulary, not two.
    "relation_debrief": ConsultationSurface(
        key="relation_debrief",
        prefix="relation:",
        source="user",
        domains={
            "contact": "contact",
            "emails": "email",
            "events": "event",
            "calls": "telephony",
            "memories": "context",
            "open_loops": "peer",
            "peer_messages": "peer",
        },
    ),
    # A documentary space is a STANDING INSTRUCTION: « keep this Drive folder
    # indexed », « follow this Gmail label » (ADR-262). Every read of it
    # happens because of that instruction — whether the person just clicked
    # « add this folder » or a Google push triggered a reindex at four in the
    # morning — which is exactly what ``scheduled`` names in this codebase:
    # the person's own deferred instruction, never LIA's own idea.
    "space": ConsultationSurface(
        key="space",
        prefix="space:",
        source="scheduled",
        domains={
            "drive": "document",
            "mail": "email",
        },
    ),
    # The push-driven wake reads the METADATA of new mail and calendar changes
    # to decide whether waking the person is worth it (ADR-261). Nobody asked;
    # it runs on a scheduler, on their mailbox, and — unlike a sweep that then
    # writes to them — it usually decides NOT to, so there is nothing else
    # they could ever consult about it.
    #
    # ONE row per wake and per source probed, never one per message: the
    # register records the capability, never the mail (owner arbitration,
    # 2026-09-07, « fais au plus simple »).
    "wake": ConsultationSurface(
        key="wake",
        prefix="wake:",
        source="proactive",
        domains={
            "emails": "email",
            "calendar": "event",
        },
    ),
    # Geocoding the address the person is setting: their own action, their own
    # data, and a paid Maps call on the deployment's key.
    "profile": ConsultationSurface(
        key="profile",
        prefix="profile:",
        source="user",
        domains={"geocoding": "place"},
    ),
    # An interest sweep does NOT only write text: it queries Brave, Perplexity
    # and Wikipedia through their clients directly, bypassing the tool layer
    # entirely. The same Brave search is therefore recorded when a person asks
    # for it in a conversation — the tool gate sees it — and invisible when LIA
    # runs it alone (owner correction, 2026-09-07). This surface was first
    # declared NOT_A_READER on the argument that it "explores public content";
    # that argument was about WHOSE data, and the register answers a different
    # question: which capability did LIA use.
    "interest": ConsultationSurface(
        key="interest",
        prefix="interest:",
        source="proactive",
        domains={
            "brave": "brave",
            "perplexity": "perplexity",
            "wikipedia": "wikipedia",
            # A reflection re-reads the person's OWN declared interests, which
            # is the one source here that is theirs.
            "llm_reflection": "interest",
        },
    ),
    # Nobody asked. The sweep runs on its own schedule, which is exactly why it
    # belongs in the initiative reading — and why its absence mattered most:
    # 824 runs over thirty days without a single row (measured 2026-09-07). A
    # conversation can be re-read; a sweep that opened someone's mail at four
    # in the morning leaves them nothing to consult.
    #
    # The three anti-redundancy windows read LIA's OWN past notifications
    # rather than the person's data, and read as ``automation`` for that
    # reason — still recorded, because « I checked what I had already sent » is
    # part of what the sweep did.
    "heartbeat": ConsultationSurface(
        key="heartbeat",
        prefix="heartbeat:",
        source="proactive",
        domains={
            "calendar": "event",
            "tasks": "task",
            "emails": "email",
            "weather": "weather",
            "interests": "interest",
            "activity": "automation",
            "recent_heartbeats": "automation",
            "recent_interests": "automation",
            "recent_other": "automation",
            "health_signals": "health",
            "birthdays": "contact",
            "open_loops": "peer",
            "habits": "automation",
            # Second pass — a dynamic query rather than the static one the
            # historical implementation anchored on (ADR-135).
            "journals": "journal",
            # Departure advice reads the person's HOME LOCATION and calls the
            # Routes API with it. Consuming calendar events the first pass
            # already fetched made it look like a computation rather than a
            # read, and it was missed when the other fifteen were declared
            # (found by a cold review, 2026-09-07) — the sixteenth source, and
            # the only one that leaves the deployment to a paid provider.
            "departure": "route",
            "memories": "context",
        },
    ),
}


#: Capabilities a node reaches DIRECTLY during a turn, through a client rather
#: than a tool — so the gate never sees them, and the same read is registered
#: when the person asks for it and silent when a node decides it.
#:
#: These are NOT surfaces: a surface fixes its authorship (nobody schedules a
#: briefing, nobody asks for a sweep), whereas a turn's authorship is whatever
#: set that turn in motion — the person, one of their routines, a sub-agent.
#: ``record_treatment`` resolves it from the runtime context, so all that is
#: needed here is the name and the noun it reads as.
IN_TURN_CAPABILITIES: Final[dict[str, str]] = {
    # The planner reads the NAMES of the person's lights and rooms so its plan
    # can cite them exactly. The Hue WRITES go through gated tools and were
    # never at risk; only this discovery read escaped.
    "planner:hue": "hue",
    # A Brave search a node decided to run, never asked for as a tool.
    "enrichment:brave": "brave",
    # The person's own mail, fetched to resolve a reference in their message.
    "enrichment:email": "email",
}


def capability_domains() -> dict[str, str]:
    """Every direct-read capability, and the domain it reads as.

    This is what the register merges into its own table. Transcribing it by
    hand is what produced two dead tables and thirty-one duplicated entries.

    Returns:
        ``{"briefing:mails": "email", "heartbeat:emails": "email", ...}``.
    """
    merged: dict[str, str] = dict(IN_TURN_CAPABILITIES)
    for surface in CONSULTATION_SURFACES.values():
        merged.update(surface.capabilities())
    return merged


def surface_of(capability: str) -> ConsultationSurface | None:
    """Which surface a capability belongs to, if any.

    Args:
        capability: A capability name, possibly a tool's.

    Returns:
        The surface, or None when no declared prefix matches.
    """
    for surface in CONSULTATION_SURFACES.values():
        if capability.startswith(surface.prefix):
            return surface
    return None


def record_surface_consultations(
    *,
    surface: str,
    user_id: object,
    opened: Iterable[str],
    failed: Iterable[str] = (),
    duration_ms: int,
    run_id: str | None = None,
) -> None:
    """Record what one direct-read surface actually opened.

    The single implementation of a loop that existed three times, with three
    different spellings of its error handling. Best-effort IN FULL: this runs
    after the work is already done, and a register that can take the home page
    or the heartbeat down is worse than the gap it closes.

    Three rules the loop inherits, and each of them is a decision:

    - **what was not opened records nothing.** A cached section (Redis
      answered, the mailbox was never opened), a section the person silenced,
      and a scope that deliberately excluded a source are all « not opened » —
      the caller decides, and passes only what it read.
    - **unreadable is not empty.** A source that could not be read reads as
      ``failed``, never as a silent success. « Nothing to report » is not
      « I could not look ».
    - **an unknown section records nothing**, because a consultation with no
      readable domain would headline as « Unknown », which ADR-263 refuses.
      The guard keeps that branch unreachable.

    Args:
        surface: Which surface read — a key of :data:`CONSULTATION_SURFACES`.
        user_id: Whose data was read.
        opened: Section keys that were actually read.
        failed: Section keys among them that could not be read; the rest
            answered.
        duration_ms: Wall-clock duration of the read. Sources gathered
            concurrently carry the same figure on each row rather than an
            invented per-source split.
        run_id: The run, or None to take the collector's own — a fetcher deep
            in an aggregation has no other use for an identifier.
    """
    # Batch-level, deliberately. The sink is ALREADY per-row best-effort
    # (``record_out_of_turn_consultation`` swallows its own write), so the only
    # failures that reach here are ones that make continuing meaningless: an
    # unknown surface, or an ``opened`` iterable that raises mid-iteration.
    try:
        declared = CONSULTATION_SURFACES.get(surface)
        if declared is None:
            logger.debug("consultation_surface_unknown", surface=surface)
            return
        refused = set(failed)
        for section in opened:
            if section not in declared.domains:
                continue
            record_consultation(
                user_id=user_id,
                run_id=run_id,
                capability=declared.capability(section),
                source=declared.source,
                succeeded=section not in refused,
                duration_ms=duration_ms,
            )
    except Exception as exc:  # noqa: BLE001 - observing never breaks the observed
        logger.debug(
            "consultation_not_recorded",
            surface=surface,
            error_type=type(exc).__name__,
        )


__all__ = [
    "CONSULTATION_SURFACES",
    "IN_TURN_CAPABILITIES",
    "ConsultationSurface",
    "capability_domains",
    "record_surface_consultations",
    "surface_of",
]
