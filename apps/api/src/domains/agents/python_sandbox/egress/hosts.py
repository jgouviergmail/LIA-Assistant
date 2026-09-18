"""What a declared host is, and what it earns (ADR-298).

The model declares the hosts a script will reach. Before any container
starts, each one is validated into the exact form the proxy matches, then
classified into one of four statuses — and the status decides everything
downstream: whether a credential travels, whether the turn's data travels,
and whether the person must be asked first.

The validation is deliberately narrow: ASCII letters, digits and hyphens,
dotted, nothing else. The proxy matches names exactly, the card the person
reads must show the name the proxy will match, and a non-ASCII name would
show one thing and match another (a homograph's whole trick). A model that
needs an internationalised domain declares its punycode form.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

from src.domains.agents.python_sandbox.egress.registry import AuthMethod

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
MAX_HOST_LENGTH = 253


class InvalidHost(ValueError):
    """A declared host the proxy could not match exactly."""


class HostStatus(str, Enum):
    """Where a host's permission comes from."""

    CONNECTOR = "connector"
    OPERATOR = "operator"
    GRANT = "grant"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ConnectorHost:
    """A host served by one of the person's own API-key connectors.

    Attributes:
        host: The upstream host.
        connector: The ``ConnectorType`` value.
        auth_method: Where the client class says the key travels.
        auth_name: The header or query parameter name.
        auth_prefix: What precedes the key in a header (``"Bearer"``), else ``""``.
    """

    host: str
    connector: str
    auth_method: AuthMethod
    auth_name: str
    auth_prefix: str


@dataclass(frozen=True)
class HostDecision:
    """The classification of one run's declared hosts.

    Attributes:
        statuses: Every declared host and its status, in declaration order.
        unknown: The hosts nobody has permitted — what the person is asked about.
        credentials: The connector hosts, whose tokens the run will hold.
        share_turn_data: Whether the turn's data may reach the script — the
            MINIMUM over the hosts (a grant given « without » narrows the run).
    """

    statuses: dict[str, HostStatus]
    unknown: tuple[str, ...]
    credentials: tuple[ConnectorHost, ...]
    share_turn_data: bool


def normalize_hosts(raw_hosts: Iterable[str], *, cap: int) -> tuple[str, ...]:
    """Validate and canonicalise the declared hosts.

    Args:
        raw_hosts: What the model declared.
        cap: The most hosts one run may declare (published in the manifest).

    Returns:
        Lowercase exact hostnames, deduplicated, in first-seen order.

    Raises:
        InvalidHost: On a name the proxy could not match exactly, or on more
            than ``cap`` distinct hosts.
    """
    seen: list[str] = []
    for raw in raw_hosts:
        host = _normalize_one(raw)
        if host not in seen:
            seen.append(host)
    if len(seen) > cap:
        raise InvalidHost(f"a run may declare at most {cap} hosts, got {len(seen)}")
    return tuple(seen)


def _normalize_one(raw: str) -> str:
    candidate = raw.strip().lower().rstrip(".")
    if not candidate:
        raise InvalidHost("empty host")
    if not candidate.isascii():
        raise InvalidHost(f"non-ASCII host {raw.strip()!r}: declare its punycode form")
    if "://" in candidate or "/" in candidate:
        raise InvalidHost(f"{raw.strip()!r} is a URL; declare the bare hostname")
    if ":" in candidate or candidate.startswith("["):
        raise InvalidHost(f"{raw.strip()!r} carries a port or is an IPv6 literal")
    if _is_ip(candidate):
        raise InvalidHost(f"{raw.strip()!r} is an IP address; declare a hostname")
    if len(candidate) > MAX_HOST_LENGTH or "." not in candidate:
        raise InvalidHost(f"{raw.strip()!r} is not a public hostname")
    if not all(_LABEL.match(label) for label in candidate.split(".")):
        raise InvalidHost(f"{raw.strip()!r} is not a valid hostname")
    return candidate


def _is_ip(candidate: str) -> bool:
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return True


def classify_hosts(
    hosts: tuple[str, ...],
    *,
    connectors: Mapping[str, ConnectorHost],
    operator_hosts: set[str],
    grants: Mapping[str, bool],
) -> HostDecision:
    """Give every declared host its status.

    A connector host wins over a grant on the same name (it brings the
    credential a grant never does); the operator's list comes next; a grant
    last; whatever is left is unknown.

    Args:
        hosts: Normalised declared hosts.
        connectors: Hosts of the person's ACTIVE API-key connectors.
        operator_hosts: The deployment's allowlist.
        grants: ``{host: share_turn_data}`` — the person's past decisions.

    Returns:
        The decision.
    """
    statuses: dict[str, HostStatus] = {}
    credentials: list[ConnectorHost] = []
    unknown: list[str] = []
    share = True
    for host in hosts:
        if host in connectors:
            statuses[host] = HostStatus.CONNECTOR
            credentials.append(connectors[host])
        elif host in operator_hosts:
            statuses[host] = HostStatus.OPERATOR
        elif host in grants:
            statuses[host] = HostStatus.GRANT
            share = share and grants[host]
        else:
            statuses[host] = HostStatus.UNKNOWN
            unknown.append(host)
    return HostDecision(
        statuses=statuses,
        unknown=tuple(unknown),
        credentials=tuple(credentials),
        share_turn_data=share,
    )


__all__ = [
    "MAX_HOST_LENGTH",
    "ConnectorHost",
    "HostDecision",
    "HostStatus",
    "InvalidHost",
    "classify_hosts",
    "normalize_hosts",
]
