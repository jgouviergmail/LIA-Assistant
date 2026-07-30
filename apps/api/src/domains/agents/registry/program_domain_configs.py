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
}
