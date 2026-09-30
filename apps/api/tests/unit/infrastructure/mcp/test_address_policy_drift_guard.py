"""Two validators, ONE address policy (ADR-326).

``agents/web_fetch/url_validator.py`` decides what a page fetch may reach and
``infrastructure/mcp/security.py`` what an MCP endpoint may be — the same
question, answered by two copies of the same tables because ``infrastructure``
must not import a domain. A copy that drifts (a range added to one, a suffix
to the other) is a private address one surface refuses and the other reaches.
This guard holds the copies equal, member for member, until the policy has one
home both layers can import.
"""

from __future__ import annotations

import pytest

from src.domains.agents.web_fetch import url_validator
from src.infrastructure.mcp import security as mcp_security

pytestmark = pytest.mark.unit


def test_the_blocked_networks_are_the_same_set() -> None:
    assert set(url_validator._BLOCKED_IP_NETWORKS) == set(mcp_security._BLOCKED_IP_NETWORKS)


def test_the_blocked_hostnames_are_the_same_set() -> None:
    assert url_validator._BLOCKED_HOSTNAMES == mcp_security._BLOCKED_HOSTNAMES


def test_the_blocked_suffixes_are_the_same_set() -> None:
    assert set(url_validator._BLOCKED_HOSTNAME_SUFFIXES) == set(
        mcp_security._BLOCKED_HOSTNAME_SUFFIXES
    )


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::ffff:192.168.0.1", "fd00::1", "8.8.8.8"],
)
def test_one_address_gets_one_answer(address: str) -> None:
    assert url_validator.check_ip_safety(address) == mcp_security._check_ip_safety(address)
