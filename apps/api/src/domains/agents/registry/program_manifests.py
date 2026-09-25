"""Interdomain-program manifest registration (single loader entry point).

The frozen ``catalogue_loader`` is at its size cap, so the program's new
domains register through this ONE aggregator (net-zero loader cost per new
domain). One function per lot-delivered domain, fanned out below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.agents.registry.agent_registry import AgentRegistry


def register_program_manifests(registry: AgentRegistry) -> None:
    """Register every interdomain-program agent + tool manifest.

    Args:
        registry: Global agent registry being initialized.
    """
    from src.domains.agents.activity.catalogue_manifests import (
        ACTIVITY_AGENT_MANIFEST,
        get_my_activity_catalogue_manifest,
    )
    from src.domains.agents.automation.catalogue_registration import (
        register_automation_manifests,
    )
    from src.domains.agents.calculation.catalogue_manifests import (
        CALCULATION_AGENT_MANIFEST,
        calculate_catalogue_manifest,
        convert_currency_catalogue_manifest,
        date_time_catalogue_manifest,
    )
    from src.domains.agents.documents.catalogue_manifests import (
        DOCUMENT_AGENT_MANIFEST,
        search_user_documents_catalogue_manifest,
    )
    from src.domains.agents.emails.self_send_manifest import (
        send_email_to_me_catalogue_manifest,
    )
    from src.domains.agents.generated_file.catalogue_manifests import (
        GENERATED_FILE_AGENT_MANIFEST,
        find_generated_files_catalogue_manifest,
    )
    from src.domains.agents.google_contacts.person_overview_manifest import (
        get_person_overview_catalogue_manifest,
    )
    from src.domains.agents.memory.catalogue_manifests import (
        MEMORY_AGENT_MANIFEST,
        search_memories_catalogue_manifest,
    )

    register_automation_manifests(registry)
    registry.register_agent_manifest(DOCUMENT_AGENT_MANIFEST)
    registry.register_tool_manifest(search_user_documents_catalogue_manifest)
    registry.register_tool_manifest(get_person_overview_catalogue_manifest)
    # Long-term memory as an active lookup (ADR-313). Unflagged: reading the
    # person's memories is gated per account (memory_enabled), like the
    # injection it complements — the MEMORY capability governs the extraction.
    registry.register_agent_manifest(MEMORY_AGENT_MANIFEST)
    registry.register_tool_manifest(search_memories_catalogue_manifest)
    # An e-mail to the user themselves (ADR-314): the email agent ships always.
    registry.register_tool_manifest(send_email_to_me_catalogue_manifest)
    # LIA's own registers and gallery as lookups (ADR-318): both exist on every
    # deployment, so neither is flag-gated.
    registry.register_agent_manifest(ACTIVITY_AGENT_MANIFEST)
    registry.register_tool_manifest(get_my_activity_catalogue_manifest)
    registry.register_agent_manifest(GENERATED_FILE_AGENT_MANIFEST)
    registry.register_tool_manifest(find_generated_files_catalogue_manifest)
    # Exact arithmetic, dates and currency (ADR-318): no data, no flag.
    registry.register_agent_manifest(CALCULATION_AGENT_MANIFEST)
    for manifest in (
        calculate_catalogue_manifest,
        date_time_catalogue_manifest,
        convert_currency_catalogue_manifest,
    ):
        registry.register_tool_manifest(manifest)

    from src.core.config import settings

    # The CRM read capabilities. Each follows the flag of the AGENT it belongs
    # to: a tool whose agent manifest is absent is an orphan the planner can
    # still be offered, in a domain the analyzer cannot even route to. Open
    # commitments live on task_agent, which always ships.
    from src.domains.agents.relations.catalogue_manifests import (
        get_calls_catalogue_manifest,
        get_open_loops_catalogue_manifest,
        get_peer_messages_catalogue_manifest,
    )

    registry.register_tool_manifest(get_open_loops_catalogue_manifest)
    if getattr(settings, "telephony_enabled", False):
        registry.register_tool_manifest(get_calls_catalogue_manifest)

    # Peers program: flag-gated like its router — a disabled instance must
    # not advertise tools whose REST surface is absent.
    if getattr(settings, "peers_enabled", False):
        from src.domains.agents.peer.catalogue_registration import (
            register_peer_manifests,
        )

        register_peer_manifests(registry)
        registry.register_tool_manifest(get_peer_messages_catalogue_manifest)

    # LIA's own journal (ADR-318): flag-gated like the journals themselves —
    # the tool module registers under the same flag (tool_registry).
    if getattr(settings, "journals_enabled", False):
        from src.domains.agents.journal.catalogue_manifests import (
            JOURNAL_AGENT_MANIFEST,
            search_journal_catalogue_manifest,
        )

        registry.register_agent_manifest(JOURNAL_AGENT_MANIFEST)
        registry.register_tool_manifest(search_journal_catalogue_manifest)

    # Workboard (ADR-276): flag-gated like its router and its sweep — a
    # disabled instance must not advertise tools whose REST surface is absent.
    if getattr(settings, "workboard_enabled", False):
        from src.domains.agents.workboard.catalogue_registration import (
            register_workboard_manifests,
        )

        register_workboard_manifests(registry)
