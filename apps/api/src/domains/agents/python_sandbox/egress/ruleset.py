"""Rendering the proxy ruleset from the live runs (ADR-298).

LIA is the proxy's ONLY author: whatever the registry holds is rendered here
into iron-proxy's YAML — the allowlist is the union of every live run's
hosts, and one ``secrets`` rule per credential swaps the run's opaque token
for the person's real key on that host alone. The real key is read by the
proxy from a file this module writes into the shared tmpfs volume; it is
never in Redis and never in the rendering.

The empty rendering IS the bootstrap file the proxy starts on
(``infrastructure/sandbox-egress/proxy.bootstrap.yaml``): a test holds the
two byte-for-byte equal, so the proxy's shape is declared once and the init
path needs no Python.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.core.constants import (
    PYTHON_SANDBOX_EGRESS_CA_FILE,
    PYTHON_SANDBOX_EGRESS_KEY_FILE,
    PYTHON_SANDBOX_EGRESS_MANAGEMENT_API_KEY_ENV,
)
from src.domains.agents.python_sandbox.egress.registry import LiveRun, RunCredential

#: Ranges the proxy refuses at CONNECT time whatever the allowlist says — the
#: DNS-rebinding and cloud-metadata classes, the IPv4-mapped-IPv6 form
#: included. A protocol constant of the ruleset (RFC 1918, 6598, 2544, 4193,
#: 3927, 4291), not a deployment's address — which is why it lives here and
#: not in ``core.constants`` (guarded there against real addresses).
DENY_CIDRS: tuple[str, ...] = (
    "127.0.0.0/8",
    # « This host » — Linux routes a connect to 0.0.0.0 to loopback.
    "0.0.0.0/8",
    "::1/128",
    "::/128",
    "169.254.0.0/16",
    "fe80::/10",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "fc00::/7",
    "::ffff:0:0/96",
    # NAT64: an IPv4 address carried inside IPv6 (RFC 6052).
    "64:ff9b::/96",
    "100.64.0.0/10",
    "198.18.0.0/15",
)
#: Where the proxy listens for the sandbox's CONNECT (HTTPS_PROXY) — every
#: interface of its own container; the sandbox network is the boundary.
TUNNEL_LISTEN = "0.0.0.0:3128"
MANAGEMENT_LISTEN = "0.0.0.0:9093"
HEALTH_LISTEN = "0.0.0.0:9094"
#: Listeners the design never uses, bound to a loopback ephemeral port so the
#: parser is satisfied and nothing is exposed (iron-proxy defaults them to
#: :80 / :443 on every interface).
UNUSED_LISTEN = "127.0.0.1:0"
#: Leaf certificates are minted per upstream host and cached in memory.
CERT_CACHE_SIZE = 256
LEAF_CERT_EXPIRY_HOURS = 24
SECRETS_DIRNAME = "secrets"


@dataclass(frozen=True)
class RulesetConfig:
    """What the rendering reads from settings.

    Attributes:
        max_body_bytes: Largest request body the proxy forwards.
    """

    max_body_bytes: int


def render_ruleset(runs: Iterable[LiveRun], config: RulesetConfig) -> str:
    """The proxy's YAML for this set of live runs.

    Args:
        runs: Every live network run of the deployment.
        config: The tunables.

    Returns:
        The YAML text, keys in a stable order, hosts sorted and deduplicated,
        one secrets rule per credential in run order.
    """
    runs = list(runs)
    hosts = sorted({host for run in runs for host in run.hosts})
    secrets = [_secret_rule(credential) for run in runs for credential in run.credentials]
    transforms: list[dict[str, Any]] = [{"name": "allowlist", "config": {"domains": hosts}}]
    if secrets:
        transforms.append({"name": "secrets", "config": {"secrets": secrets}})
    document: dict[str, Any] = {
        # Required by the parser; tunnel-only mode never serves DNS.
        "dns": {"listen": UNUSED_LISTEN, "proxy_ip": "127.0.0.1"},
        "proxy": {
            "tunnel_listen": TUNNEL_LISTEN,
            "http_listen": UNUSED_LISTEN,
            "https_listen": UNUSED_LISTEN,
            "max_request_body_bytes": config.max_body_bytes,
            "upstream_deny_cidrs": list(DENY_CIDRS),
        },
        "metrics": {"listen": HEALTH_LISTEN},
        "management": {
            "listen": MANAGEMENT_LISTEN,
            "api_key_env": PYTHON_SANDBOX_EGRESS_MANAGEMENT_API_KEY_ENV,
        },
        "tls": {
            "ca_cert": PYTHON_SANDBOX_EGRESS_CA_FILE,
            "ca_key": PYTHON_SANDBOX_EGRESS_KEY_FILE,
            "cert_cache_size": CERT_CACHE_SIZE,
            "leaf_cert_expiry_hours": LEAF_CERT_EXPIRY_HOURS,
        },
        "transforms": transforms,
        "log": {"level": "info"},
    }
    rendered: str = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
    return rendered


def _secret_rule(credential: RunCredential) -> dict[str, Any]:
    """One token-for-key swap, bound to the credential's host.

    ``require`` stays off on purpose: the sandbox never holds a real key, so
    rejecting a token-less request protects nothing — and it WOULD refuse a
    second live run on the same host that has no credential of its own.
    """
    by_header = credential.auth_method == "header"
    return {
        "source": {"type": "file", "path": credential.secret_path},
        "replace": {
            "proxy_value": credential.token,
            "match_headers": [credential.auth_name] if by_header else [],
            "match_query": not by_header,
            "match_body": False,
            "require": False,
        },
        "rules": [{"host": credential.host}],
    }


def write_run_secrets(config_dir: Path, run_id: str, secrets: Mapping[str, str]) -> dict[str, Path]:
    """Write one private file per credential under ``secrets/<run_id>/``.

    Args:
        config_dir: The shared config volume, as mounted in THIS container.
        run_id: The run the files belong to.
        secrets: ``{connector: real key}``.

    Returns:
        ``{connector: path written}``.
    """
    run_dir = config_dir / SECRETS_DIRNAME / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(run_dir, 0o700)
    written: dict[str, Path] = {}
    for connector, value in secrets.items():
        target = run_dir / f"{connector}.key"
        # 0600 from the first byte, never at the process umask.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
        written[connector] = target
    return written


def remove_run_secrets(config_dir: Path, run_id: str) -> None:
    """Drop a run's secrets directory; silent when there is none."""
    shutil.rmtree(config_dir / SECRETS_DIRNAME / run_id, ignore_errors=True)


__all__ = [
    "DENY_CIDRS",
    "RulesetConfig",
    "remove_run_secrets",
    "render_ruleset",
    "write_run_secrets",
]
