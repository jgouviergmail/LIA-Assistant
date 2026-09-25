"""Program-added domain configs (single taxonomy extension point).

``domain_taxonomy`` is frozen at its size cap, so program-delivered domains
register through this ONE aggregator (net-zero taxonomy cost per new domain
— the ``program_manifests`` pattern applied to the DOMAIN_REGISTRY).
"""

from __future__ import annotations

from src.domains.agents.registry.domain_taxonomy import DomainConfig

PROGRAM_DOMAIN_CONFIGS: dict[str, DomainConfig] = {
    # Peers program: connections between USERS of this instance (relay
    # messages assistant-to-assistant, read shared calendars/tasks).
    "peer": DomainConfig(
        name="peer",
        display_name="User Connections",
        description=(
            "Connections with OTHER USERS of this LIA instance: relay a "
            "message to a connected user through their assistant, list "
            "connections, check a connected user's shared availability or "
            "tasks. NOT for the user's own address book (use contact) nor "
            "their own calendar (use event)."
        ),
        agent_names=["peer_agent"],
        result_key="peers",  # $steps.step_N.peers
        # NOT related to "contact": peer names resolve against the user's
        # ACCEPTED connections, never the address book — listing contact as
        # related pulled Google contact tools into every peer plan, and a
        # missing contacts scope then invalidated the WHOLE plan (runtime
        # defect 2026-07-30: availability question answered "nothing is
        # configured"). "event" stays: shared-calendar reads are adjacent.
        related_domains=["event"],
        metadata={"requires_oauth": False, "feature_flag": "peers_enabled"},
    ),
    # AI Document Generation (ADR-226): downloadable files written by a
    # dedicated LLM slot, rendered locally, stored as TTL attachments.
    "document_generation": DomainConfig(
        name="document_generation",
        display_name="Document Generation",
        description=(
            "Create downloadable documents (CSV, Excel, Word, PowerPoint, PDF, "
            "Markdown, text) from instructions and optional data. "
            "Use when the user asks for a file, an export, a report document, "
            "a spreadsheet or a presentation. NOT for images."
        ),
        agent_names=["document_generation_agent"],
        result_key="document_generations",  # $steps.step_N.document_generations
        related_domains=[],
        is_routable=True,
        # requires_api_key False: uses the admin LLM Config slot.
        metadata={"provider": "internal", "requires_oauth": False, "requires_api_key": False},
    ),
    # Long-term memory as an active lookup (ADR-313): what LIA remembers about
    # the person, searched on demand for a subject the turn discovers. The
    # passive per-turn injection (memory_injection) is unchanged. Deliberately
    # absent from PHONE_DOMAINS: the voice has its own door to the same memories
    # (the native ``recall_memories`` lookup).
    "memory": DomainConfig(
        name="memory",
        display_name="Long-term memory",
        description=(
            "What LIA REMEMBERS about the user from past conversations: their "
            "preferences, the people in their life, habits, significant events, "
            "standing instructions they gave. Search it for a fact about the "
            "user that the request does not settle. Search only: remembering "
            "something new needs no tool (memories are extracted from the "
            "conversation automatically). NOT the address book (use contact), "
            "NOT the user's documents (use document)."
        ),
        agent_names=["memory_agent"],
        result_key="memories",  # $steps.step_N.memories
        related_domains=[],
        metadata={"provider": "internal", "requires_oauth": False},
    ),
    # LIA's own journal as an active lookup (ADR-318). The passive per-turn
    # injection is unchanged; the lookup serves a subject the turn discovers.
    "journal": DomainConfig(
        name="journal",
        display_name="LIA's journal",
        description=(
            "LIA's OWN journal: what LIA noted for itself from past conversations "
            "with the user — how to work with them (directives), patterns it "
            "observed, facets of its portrait of the user. Use when the user asks "
            "what LIA noticed, learned or noted about them, or to recall how LIA "
            "should handle a subject. NOT the user's memories (use memory), NOT "
            "their documents (use document)."
        ),
        agent_names=["journal_agent"],
        result_key="journals",  # $steps.step_N.journals
        related_domains=[],
        metadata={
            "provider": "internal",
            "requires_oauth": False,
            "feature_flag": "journals_enabled",
        },
    ),
    # Exact computations (ADR-318): arithmetic, dates and currency — what a model
    # must not do in its head. Internal, no OAuth, no personal data.
    "calculation": DomainConfig(
        name="calculation",
        display_name="Calculation",
        description=(
            "Exact computations the model must NOT do in its head: arithmetic "
            "(totals, percentages, VAT, unit prices, splits, averages, interest), "
            "date and time arithmetic (days until a date, ages, weekdays, adding "
            "days or business days, time zone conversion) and currency conversion "
            "at the published reference rate. Use it whenever an answer states a "
            "computed figure, a computed date or a converted amount. NOT for "
            "looking data up (use the domain that holds it)."
        ),
        agent_names=["calculation_agent"],
        result_key="calculations",  # $steps.step_N.calculations
        related_domains=[],
        metadata={"provider": "internal", "requires_oauth": False},
    ),
    # What LIA did and read for the person (ADR-318), from its own registers
    # (ADR-263). Read-only; the registers exist on every deployment.
    "activity": DomainConfig(
        name="activity",
        display_name="LIA's activity",
        description=(
            "What LIA itself DID and CONSULTED for the user, from its transparency "
            "registers: the actions it performed (messages sent, events created, "
            "notifications) with their outcome, and the data it read, over a "
            "period. Use for 'what did you do for me', 'did you send it', 'what "
            "did you do on your own'. NOT the user's own calendar or tasks (use "
            "event, task)."
        ),
        agent_names=["activity_agent"],
        result_key="activities",  # $steps.step_N.activities
        related_domains=[],
        metadata={"provider": "internal", "requires_oauth": False},
    ),
    # The files LIA produced, found again and shown (ADR-318) — the gallery of
    # ADR-279 as a lookup. Deliberately absent from PHONE_DOMAINS: what it finds
    # is shown as chat cards, which no voice surface draws.
    "generated_file": DomainConfig(
        name="generated_file",
        display_name="Files LIA produced",
        description=(
            "The files LIA PRODUCED for the user — generated images and documents, "
            "browser screenshots, images a connection shared — found again and "
            "shown in the chat. NOT the user's Drive files (use file), NOT "
            "creating a new image or document (use image_generation, "
            "document_generation)."
        ),
        agent_names=["generated_file_agent"],
        result_key="generated_files",  # $steps.step_N.generated_files
        related_domains=[],
        metadata={"provider": "internal", "requires_oauth": False},
    ),
    # Workboard (ADR-276): the person's own board of tickets, which LIA can
    # also run alone. Singular noun, like every other domain — `result_key` is
    # DERIVED here and never re-listed anywhere else.
    "ticket": DomainConfig(
        name="ticket",
        display_name="Workboard",
        description=(
            "The user's own WORKBOARD of tickets: create a ticket, move it "
            "between columns (idea, to do, in progress, waiting, validating, "
            "done, cancelled), comment on it, list what is on the board or "
            "overdue, hand one to LIA or to a connected user, delete one. "
            "Words that point here: workboard, board, ticket, kanban, column. "
            "NOT a to-do in the user's provider account (use task), NOT a "
            "push notification at a given time (use reminder), and NOT a "
            "recurring job the scheduler runs (use automation)."
        ),
        agent_names=["ticket_agent"],
        result_key="tickets",  # $steps.step_N.tickets
        # A ticket can be handed to a connected user, so a peer name in the
        # sentence must keep the peer directory in play. Nothing else: listing
        # `contact` here would pull the address book into every board plan,
        # the exact defect the peer domain records above.
        related_domains=["peer"],
        metadata={
            "provider": "internal",
            "requires_oauth": False,
            "feature_flag": "workboard_enabled",
        },
    ),
}
