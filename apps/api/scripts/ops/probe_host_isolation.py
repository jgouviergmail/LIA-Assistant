"""Can this container reach the machine that hosts it?

Run INSIDE the demonstrator's API container. It opens real TCP connections to
the gateway of every network the container sits on, and reports a failure when
one of them answers.

Why it exists: `internal: true` stops a container routing to the Internet and
to other networks, but not to the bridge GATEWAY — and that address is an
interface of the host. Measured 2026-08-07 with disposable containers, a
listener bound to 0.0.0.0 in the host namespace answered a container whose
only network was created with `--internal`. On the production Raspberry that
means sshd, and from there the production stack.

`scripts/deploy/harden-demo-host.sh` closes it with iptables rules. This probe
is what turns "we installed the rules" into "the rules work": a protection
nobody measures is a protection nobody has.

Exit codes:
    0  every gateway refused or timed out — the host is unreachable
    1  at least one port answered, or the gateways could not be discovered

Usage (from the repository, through the task):
    task demo:verify

Created: 2026-08-07 (live-demonstrator programme, security audit F-NET-1)
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

#: Ports worth trying on the host. Not an exhaustive scan — a representative
#: set whose success would each be a real finding: remote shell, the web and
#: API ports a sibling stack publishes, the databases, the Docker API.
_PORTS: tuple[tuple[int, str], ...] = (
    (22, "ssh"),
    (2222, "ssh (alternate)"),
    (80, "http"),
    (443, "https"),
    (3000, "a sibling web app"),
    (5432, "postgresql"),
    (6379, "redis"),
    (8000, "a sibling api"),
    (2375, "docker api (plaintext)"),
)

#: Long enough that a silent DROP is distinguishable from a slow accept, short
#: enough that nine ports on a handful of gateways stay under a minute.
_TIMEOUT_SECONDS = 3.0


def _le_hex_to_int(value: str) -> int:
    """Kernel routing tables store addresses little-endian hex."""
    return int.from_bytes(bytes.fromhex(value), "little")


def _host_addresses() -> list[str]:
    """Every address of this container's networks that belongs to the HOST.

    Two kinds, and missing the second is what a first version of this probe
    did — reporting "no gateway, nothing to reach" on an instance whose host
    was one connect() away:

    - the DEFAULT gateway, when there is one (routed networks);
    - the first usable address of each ON-LINK subnet. A Docker network marked
      ``internal`` installs no default route at all, yet the bridge address —
      the host — sits in the subnet and answers as a direct neighbour
      (measured 2026-08-07: ``172.21.0.1`` returned TCP RST on closed ports
      from a container whose networks were all internal).

    Returns:
        Dotted-quads to probe, deduplicated, in discovery order.

    Raises:
        OSError: ``/proc/net/route`` is unreadable, which means the probe
            cannot know what to test — reported as a failure, never as a pass.
    """
    found: list[str] = []
    for line in Path("/proc/net/route").read_text(encoding="ascii").splitlines()[1:]:
        fields = line.split()
        if len(fields) < 8:
            continue
        destination, gateway, mask = _le_hex_to_int(fields[1]), fields[2], _le_hex_to_int(fields[7])

        if gateway != "00000000":
            packed = _le_hex_to_int(gateway).to_bytes(4, "big")
            address = ".".join(str(byte) for byte in packed)
            if address not in found:
                found.append(address)
            continue

        # On-link route: the host holds the first usable address of the subnet.
        if mask == 0 or mask == 0xFFFFFFFF:
            continue
        candidate = ((destination & mask) + 1).to_bytes(4, "big")
        address = ".".join(str(byte) for byte in candidate)
        if address not in found:
            found.append(address)
    return found


def _reachable(host: str, port: int) -> bool:
    """Whether a TCP connection to ``host:port`` completes."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(_TIMEOUT_SECONDS)
    try:
        sock.connect((host, port))
    except OSError:
        return False
    finally:
        sock.close()
    return True


def main() -> int:
    """Probe every host address and report.

    Returns:
        0 when the host is unreachable on every probed port, 1 otherwise.
    """
    try:
        gateways = _host_addresses()
    except OSError as exc:
        print(f"  ERROR: cannot read the routing table ({exc}) - refusing to report success")
        return 1

    if not gateways:
        # No address at all is indistinguishable from a probe that looks in the
        # wrong place — and the first version of this probe DID look in the
        # wrong place. Refuse rather than report a pass nobody measured.
        print("  ERROR: no host address discovered from the routing table")
        print("         (an internal network still exposes the bridge address;")
        print("          a probe that finds none is broken, not reassuring)")
        return 1

    answered: list[str] = []
    for gateway in gateways:
        for port, label in _PORTS:
            if _reachable(gateway, port):
                answered.append(f"{gateway}:{port} ({label})")

    if answered:
        print("  HOST REACHABLE from inside the demonstrator:")
        for entry in answered:
            print(f"      {entry}")
        print("  Run scripts/deploy/harden-demo-host.sh on the host, then re-run this.")
        return 1

    print(f"  host isolation OK: {len(gateways)} host address(es) probed, none answered")
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
