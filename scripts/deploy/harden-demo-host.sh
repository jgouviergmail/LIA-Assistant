#!/usr/bin/env sh
# Confine the demonstrator to the Internet and to itself -- nothing else on this
# machine.
#
# Docker leaves TWO paths open that `internal: true` does not close, and the
# second is the worse one:
#
#   1. THE HOST. `internal` stops a container routing outward, not reaching the
#      bridge GATEWAY, and that gateway is an interface of the host. Measured
#      2026-08-07: a listener bound to 0.0.0.0 in the host namespace answered a
#      container whose only network was created with `--internal`. On a
#      Raspberry Pi that means sshd.
#
#   2. EVERY OTHER DOCKER NETWORK. Bridge networks on the same host route to
#      one another by default, and the demonstrator NEEDS three routed
#      containers (the egress proxy, the mail relay, the tunnel). Measured
#      2026-08-07 from the egress proxy's namespace against the development
#      stack: PostgreSQL answered `fe_sendauth: no password supplied` and Redis
#      answered `NOAUTH Authentication required` -- full protocol conversations,
#      with only a password in the way. Publishing those ports on 127.0.0.1
#      protects nothing here: the container address is reached directly.
#
# The two are NOT closed the same way, and believing they were is what left the
# host open through the first version of this script -- caught by the probe
# this script exists to satisfy (measured 2026-08-07 on the Raspberry):
#
#   HOST REACHABLE from inside the demonstrator:
#       172.24.0.1:2222 (ssh)   172.25.0.1:2222 (ssh)   ...
#
# Those addresses are the gateways of the demonstrator's OWN networks. A
# gateway belongs to the subnet it serves, so the rule that lets the
# demonstrator talk to itself -- `-s demo -d demo -j RETURN`, which the API,
# squid, postfix and the tunnel all depend on -- also let it talk to the host,
# and it came FIRST. One chain cannot carry both meanings, so there are two:
#
#   LIA-DEMO-HOSTGUARD  hooked to INPUT: traffic addressed to THIS MACHINE.
#                       The demonstrator needs nothing here -- its resolver is
#                       Docker's, inside its own namespace, and its peers are
#                       containers -- so everything is dropped, its own
#                       gateways included.
#   LIA-DEMO-ISOLATION  hooked to DOCKER-USER: traffic FORWARDED to another
#                       container. Its own project is allowed, every other
#                       private destination dropped, the Internet untouched.
#
# DOCKER-USER is the chain Docker guarantees it will not flush; INPUT is where
# host-addressed traffic goes, and it never reaches DOCKER-USER. Both jump to
# dedicated chains, so the ORDER inside each is explicit instead of depending
# on insert positions.
#
# Idempotent: the chains are flushed and rebuilt, so re-running converges.
#
# Usage: harden-demo-host.sh [--check]
#   (no argument)  install the rules
#   --check        report only; exit 1 when the isolation is not in place
#
# Created: 2026-08-07 (live-demonstrator programme, security audit F-NET-1/5)
set -eu

PROJECT="${DEMO_COMPOSE_PROJECT:-lia-demo-instance}"
CHAIN="LIA-DEMO-ISOLATION"
HOSTCHAIN="LIA-DEMO-HOSTGUARD"
MODE="${1:-install}"

#: Everything private. The demonstrator has no business reaching any of it:
#: not the host, not a sibling Docker network, not the local network.
PRIVATE="10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 127.0.0.0/8"

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker is not available; cannot discover the demonstrator's subnets" >&2
    exit 1
fi

# Reachable is not the same as usable. Without this, a socket the user may not
# open produced "no network found for compose project" -- a diagnosis that
# blames the demonstrator for a permission problem (measured 2026-08-07).
if ! docker network ls >/dev/null 2>&1; then
    echo "ERROR: docker is installed but this user cannot talk to it." >&2
    echo "       $(docker network ls 2>&1 | head -1)" >&2
    echo "       Ajouter l utilisateur au groupe docker : sudo usermod -aG docker $(id -un)" >&2
    exit 1
fi

# `iptables` lives in /usr/sbin on Debian, and /usr/sbin is NOT on the PATH of
# a non-root login shell -- which is what an ssh deployment gets. Looking only
# at the PATH reported "no iptables binary found" on a host that has two
# (measured 2026-08-07 on the Raspberry).
IPT=""
for candidate in iptables-nft iptables; do
    if command -v "$candidate" >/dev/null 2>&1; then IPT="$candidate"; break; fi
done
if [ -z "$IPT" ]; then
    for candidate in /usr/sbin/iptables-nft /usr/sbin/iptables /sbin/iptables-nft /sbin/iptables; do
        if [ -x "$candidate" ]; then IPT="$candidate"; break; fi
    done
fi
if [ -z "$IPT" ]; then
    echo "ERROR: no iptables binary found; the demonstrator must not be exposed on this host" >&2
    exit 1
fi

# Netfilter is root's. The deployment user is not, so every call goes through
# sudo -- non-interactive, because there is no terminal on the other end of an
# ssh command and a password prompt would hang until the timeout.
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo -n"
        # Probe with the SAME shape the rules use: one sudo, the binary, a
        # read-only listing. Probing `sudo sudo iptables` would demand a right
        # that a narrow `NOPASSWD: /usr/sbin/iptables` grant does not give, and
        # would refuse a host that is in fact correctly configured.
        if ! $SUDO "$IPT" -L -n >/dev/null 2>&1; then
            echo "ERROR: sudo -n $IPT is refused for $(id -un)." >&2
            echo "       Grant passwordless sudo for iptables, or run this as root:" >&2
            echo "         echo '$(id -un) ALL=(root) NOPASSWD: $IPT' | sudo tee /etc/sudoers.d/lia-demo-iptables" >&2
            exit 1
        fi
    else
        echo "ERROR: not root and sudo is absent; netfilter rules cannot be written" >&2
        exit 1
    fi
fi

# DISCOVERED, never typed: Docker allocates these, and a hand-written range
# silently protects nothing the day the allocation moves.
SUBNETS=$(docker network ls --filter "name=^${PROJECT}_" --format '{{.Name}}' \
    | while read -r net; do
        docker network inspect "$net" --format '{{range .IPAM.Config}}{{.Subnet}}{{"\n"}}{{end}}' 2>/dev/null
      done | sed '/^$/d' | sort -u)

if [ -z "$SUBNETS" ]; then
    echo "ERROR: no network found for compose project '${PROJECT}' -- start it first, or set DEMO_COMPOSE_PROJECT" >&2
    exit 1
fi

if [ "$MODE" = "--check" ]; then
    problems=0

    # Read what the kernel PRINTS, never ask `-C` whether a rule exists.
    #
    # On iptables-nft, `-C` answered "Bad rule (does a matching rule exist in
    # that chain?)" for two of three DROP rules that `-S` listed verbatim, in
    # the same shell, seconds after installing them (measured 2026-08-07). A
    # verification that reports an installed rule as missing is worse than no
    # verification: it sends the next person to re-run an install that was
    # already correct, and it teaches them to disbelieve the alarm.
    #
    # `-S` also normalises what it prints -- `ESTABLISHED,RELATED` comes back
    # as `RELATED,ESTABLISHED` -- so the reply exemption is matched on its
    # invariant part rather than on the spelling used to create it.
    rules_of() { $SUDO "$IPT" -S "$1" 2>/dev/null || true; }
    has() { printf '%s\n' "$1" | grep -qF -- "$2"; }

    hostrules=$(rules_of "$HOSTCHAIN")
    fwdrules=$(rules_of "$CHAIN")

    for pair in "INPUT $HOSTCHAIN" "DOCKER-USER $CHAIN"; do
        hook=${pair% *}
        chain=${pair#* }
        chainrules=$(rules_of "$chain")
        if [ -z "$chainrules" ]; then
            echo "  MISSING : chain $chain does not exist"
            problems=$((problems + 1))
            continue
        fi
        if has "$(rules_of "$hook")" "-j $chain"; then
            echo "  present : $hook -> $chain"
        else
            echo "  MISSING : $hook -> $chain"
            problems=$((problems + 1))
        fi
        if printf '%s\n' "$chainrules" | grep -- '-m conntrack' | grep -q -- '-j RETURN'; then
            echo "  present : $chain exempts replies"
        else
            echo "  MISSING : $chain ESTABLISHED,RELATED exemption"
            problems=$((problems + 1))
        fi
    done

    # The jump the previous version left behind. It puts "demo -> demo is
    # allowed" on the path where demo -> demo reaches the host, so it must be
    # gone, not merely outranked by the guard that precedes it.
    if has "$(rules_of INPUT)" "-j $CHAIN"; then
        echo "  STALE   : INPUT -> $CHAIN (forward rules on the host path)"
        problems=$((problems + 1))
    fi

    # The rule the Raspberry proved was missing: the demonstrator addressing
    # THIS MACHINE, its own bridge gateways included.
    for subnet in $SUBNETS; do
        if has "$hostrules" "-s $subnet -j DROP"; then
            echo "  present : DROP $subnet -> this host (gateways included)"
        else
            echo "  MISSING : DROP $subnet -> this host (gateways included)"
            problems=$((problems + 1))
        fi
        for private in $PRIVATE; do
            if ! has "$fwdrules" "-s $subnet -d $private -j DROP"; then
                echo "  MISSING : DROP $subnet -> $private (forwarded)"
                problems=$((problems + 1))
            fi
        done
    done

    if [ "$problems" -gt 0 ]; then
        echo "ERROR: $problems rule(s) missing -- the demonstrator can reach this machine" >&2
        exit 1
    fi
    echo "host and sibling-network isolation OK"
    exit 0
fi

# Rebuild from scratch: flushing is what makes a re-run converge instead of
# stacking duplicates, and it also drops rules for subnets Docker has since
# reallocated.
$SUDO "$IPT" -N "$HOSTCHAIN" 2>/dev/null || $SUDO "$IPT" -F "$HOSTCHAIN"
$SUDO "$IPT" -N "$CHAIN" 2>/dev/null || $SUDO "$IPT" -F "$CHAIN"

# --- INPUT: what the demonstrator may say to THIS MACHINE. Nothing. ---------
#
# FIRST, and the rule whose absence breaks everything else: replies.
# A request from the host to a published port arrives as `host -> subnet`,
# which no rule here matches -- but its REPLY is `subnet -> host`, which the
# drop below matches exactly. Without this line the edge's published port
# answers nothing, and the failure looks like a broken application rather than
# a firewall. A connection the demonstrator OPENS is NEW, so it never earns
# this exemption.
$SUDO "$IPT" -A "$HOSTCHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
for subnet in $SUBNETS; do
    $SUDO "$IPT" -A "$HOSTCHAIN" -s "$subnet" -j DROP
done

# --- DOCKER-USER: what the demonstrator may say to OTHER CONTAINERS ---------
#
# Here, and only here, the demonstrator's own subnets are allowed: the API
# talks to its database, squid and postfix and the tunnel are peers. Order is
# load-bearing -- that RETURN must precede the private-range drops, or the
# envelope would cut itself in half.
$SUDO "$IPT" -A "$CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
for subnet in $SUBNETS; do
    for own in $SUBNETS; do
        $SUDO "$IPT" -A "$CHAIN" -s "$subnet" -d "$own" -j RETURN
    done
done
for subnet in $SUBNETS; do
    for private in $PRIVATE; do
        $SUDO "$IPT" -A "$CHAIN" -s "$subnet" -d "$private" -j DROP
    done
done

# MIGRATION, and it is a security fix rather than tidying: the previous version
# of this script jumped the FORWARD chain from INPUT too. That chain opens with
# "the demonstrator's own subnets are allowed" -- correct between containers,
# and on the INPUT path it is the very permission that made the host reachable,
# because a gateway belongs to the subnet it serves. Rebuilding the chains does
# not remove a jump, so an upgraded host would keep it: harmless only for as
# long as the new guard stays ahead of it. Delete every occurrence -- iptables
# removes one per call.
while $SUDO "$IPT" -D INPUT -j "$CHAIN" 2>/dev/null; do :; done

# Hook each chain where its traffic actually goes. Traffic to the host is INPUT
# and never reaches DOCKER-USER; traffic to another container is FORWARD and
# never reaches INPUT. Guarding only one of them protects only half of what is
# open.
$SUDO "$IPT" -C INPUT -j "$HOSTCHAIN" 2>/dev/null || $SUDO "$IPT" -I INPUT 1 -j "$HOSTCHAIN"
$SUDO "$IPT" -C DOCKER-USER -j "$CHAIN" 2>/dev/null || $SUDO "$IPT" -I DOCKER-USER 1 -j "$CHAIN"

echo "Isolation installed for '${PROJECT}':"
for subnet in $SUBNETS; do echo "  $subnet -> this host, gateways included: dropped"; done
echo "  ${PROJECT} -> its own containers: allowed"
echo "  every other private destination (sibling Docker networks, LAN): dropped"
echo "  the Internet: still reachable, which is what the proxy and the relay need"
echo
echo "The rules survive a Docker restart but NOT a host reboot unless your"
echo "distribution persists iptables -- the deploy task re-runs this every time."
