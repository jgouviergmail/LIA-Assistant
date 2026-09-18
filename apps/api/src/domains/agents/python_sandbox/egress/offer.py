"""What a turn may reach without asking — the hosts the prompt OFFERS (ADR-298).

The ``<Computation>`` block tells the model which hosts a script can reach at
once and which credential token each carries. That list is read from what the
ACCOUNT holds at the start of the turn — its active API-key connectors, plus
the operator's list — never from a static table: a host the prompt promises
and the run then refuses sends the model on a dead end, and a host the run
would allow but the prompt never named is a capability nobody uses.

Best-effort, like every context block (``react_context``): a connector read
that fails keeps the operator's hosts and logs; the prompt is still built.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from uuid import UUID

import structlog

from src.core.config import get_settings
from src.domains.agents.python_sandbox.egress.connectors import (
    ConnectorGate,
    active_connector_hosts,
)
from src.domains.agents.python_sandbox.egress.hosts import ConnectorHost
from src.domains.agents.python_sandbox.egress.run import token_env_name

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ReachableHost:
    """One host a run may declare without being asked.

    Attributes:
        host: The upstream host, lowercase.
        credential: The connector serving it, when the person's own key
            travels — ``None`` for an operator host.
    """

    host: str
    credential: ConnectorHost | None

    @property
    def token_env(self) -> str | None:
        """The env variable the script reads the token from, if any."""
        return token_env_name(self.credential.connector) if self.credential else None


@dataclass(frozen=True, slots=True)
class NetworkOffer:
    """What the turn's prompt may promise about the network.

    Attributes:
        hosts: Connector hosts first (in derivation order), then the
            operator's hosts sorted — every one reachable without a question.
        ask_enabled: Whether an unknown host is ASKED of the person (else
            refused before the run) — the rule the prompt states.
    """

    hosts: tuple[ReachableHost, ...]
    ask_enabled: bool


def merge_reachable(
    connectors: Mapping[str, ConnectorHost], operator_hosts: Iterable[str]
) -> tuple[ReachableHost, ...]:
    """The hosts reachable without a question: connectors first, then the operator's.

    ONE derivation for the prompt (``offer_for_account``) and the settings
    page (``router.reachable_hosts``): a connector host also on the operator's
    list keeps its credential, every group is sorted, and the case of an
    operator entry is folded to what the proxy matches.

    Args:
        connectors: ``{host: ConnectorHost}`` of the ACTIVE API-key connectors.
        operator_hosts: The operator's allowlist, any case.

    Returns:
        The reachable hosts, connector hosts first.
    """
    operator = sorted({h.lower() for h in operator_hosts} - set(connectors))
    return tuple(ReachableHost(host, connectors[host]) for host in sorted(connectors)) + tuple(
        ReachableHost(host, None) for host in operator
    )


async def offer_for_account(user_id: UUID, gate: ConnectorGate | None) -> NetworkOffer:
    """The hosts this account may reach at once, read now.

    Args:
        user_id: The account.
        gate: The connector service, or ``None`` when it could not be
            obtained — the operator's hosts are still offered.

    Returns:
        The offer, never raising: a blind connector read is logged.
    """
    settings = get_settings()
    connectors: dict[str, ConnectorHost] = {}
    if gate is not None:
        try:
            connectors = await active_connector_hosts(gate, user_id)
        except Exception as exc:  # noqa: BLE001 — best-effort context block
            logger.warning(
                "sandbox_egress_offer_connectors_unavailable",
                user_id=str(user_id),
                error=type(exc).__name__,
            )
    return NetworkOffer(
        hosts=merge_reachable(connectors, settings.python_sandbox_egress_hosts),
        ask_enabled=settings.python_sandbox_egress_ask_enabled,
    )


__all__ = ["NetworkOffer", "ReachableHost", "merge_reachable", "offer_for_account"]
