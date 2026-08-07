#!/bin/sh
# LIA self-host installer bootstrap (ADR-215, B01).
#
# Read-only host checks, then delegation to the Python wizard:
#   PYTHONDONTWRITEBYTECODE=1 python3 -B -m scripts.install "$@"
#
# The bytecode scan runs BEFORE the first Python command and is fail-closed:
# a release bundle never ships .pyc/.pyo/__pycache__, and -B keeps the
# integrity check itself from mutating the canonical tree on resume.
set -eu

say() { printf '%s\n' "$*" >&2; }
die() { say "ERROR: $*"; exit 3; }

# --- Host prerequisites (read-only) ----------------------------------------
[ "$(uname -s)" = "Linux" ] || die "supported host OS is Linux (got $(uname -s))"

arch="$(uname -m)"
case "$arch" in
  x86_64|aarch64) : ;;
  *) die "supported architectures are x86_64 and aarch64 (got $arch)" ;;
esac

command -v python3 >/dev/null 2>&1 || die "python3 >= 3.10 is required"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || die "python3 >= 3.10 is required (got $(python3 -V 2>&1))"

command -v docker >/dev/null 2>&1 || die "docker CLI is required"
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required"
compose_version="$(docker compose version --short 2>/dev/null || echo 0)"
# LAN port lists use the Compose `!override` tag (>= 2.24.4).
python3 - "$compose_version" <<'PYEOF' || die "docker compose >= 2.24.4 is required (got $compose_version)"
import sys
parts = (sys.argv[1].lstrip("v").split(".") + ["0", "0"])[:3]
try:
    ok = tuple(int(p) for p in parts) >= (2, 24, 4)
except ValueError:
    ok = False
sys.exit(0 if ok else 1)
PYEOF

free_kib="$(df -Pk . | awk 'NR==2 {print $4}')"
[ "${free_kib:-0}" -ge 10485760 ] || die "at least 10 GiB free disk space is required"

# --- Bytecode integrity scan (before ANY Python import of the wizard) ------
stale="$(find scripts/install -name '__pycache__' -o -name '*.pyc' -o -name '*.pyo' 2>/dev/null | head -5)"
[ -z "$stale" ] || die "stale Python bytecode under scripts/install (refusing to import): $stale"

# --- Delegate ---------------------------------------------------------------
PYTHONDONTWRITEBYTECODE=1 exec python3 -B -m scripts.install "$@"
