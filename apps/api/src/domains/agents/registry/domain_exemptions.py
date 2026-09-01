"""Agent domains that legitimately live outside ``DOMAIN_REGISTRY``.

``DomainConfig`` requires a ``result_key`` — the name a plan step's payload
takes in ``$steps.step_N.{result_key}``. An agent that returns a computation
rather than a domain payload has no honest key to declare, and inventing one
would put a reference in the vocabulary that nothing can ever produce.

This is the same escape hatch as the dynamic MCP domains, for the same reason:
the registry is the vocabulary of DATA, and some agents are capabilities of the
platform. It lives in its own module because the registry file is frozen at its
audited size and a shared concept deserves a name, not a corner of a bigger
file.
"""

from __future__ import annotations

#: Kept deliberately tiny: every entry is a decision that a domain-filtered
#: catalogue may skip this agent.
PLATFORM_AGENT_DOMAINS: frozenset[str] = frozenset(
    {
        # ADR-249: ephemeral Python. No server, no network, no stored payload —
        # it computes over the turn's own data and returns the result.
        "python",
    }
)


def is_platform_domain(domain_name: str) -> bool:
    """Whether a domain is a declared platform capability rather than data.

    Args:
        domain_name: Domain identifier extracted from an agent name.

    Returns:
        True when the domain is exempt from ``DOMAIN_REGISTRY`` membership.
    """
    return domain_name in PLATFORM_AGENT_DOMAINS
