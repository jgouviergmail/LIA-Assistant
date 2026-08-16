#!/usr/bin/env bash
# Hermetic tests for deploy_readiness_gate.sh (audit F008): success, red
# readiness with successful rollback, and unrecoverable failure — no Docker, no
# network. Run:  bash scripts/deploy/lib/test_deploy_readiness_gate.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Subshells append one line per failure here; the parent tallies at the end.
FAILS_FILE="$(mktemp)"
trap 'rm -f "$FAILS_FILE"' EXIT

_ok() { echo "  ok: $1"; }
_bad() { echo "x" >>"$FAILS_FILE"; echo "  FAIL: $1" >&2; }
_eq() { if [ "$2" -eq "$3" ]; then _ok "$1"; else _bad "$1 (rc=$2 exp=$3)"; fi; }
_has() { if grep -q "$3" "$2" 2>/dev/null; then _ok "$1"; else _bad "$1 (missing '$3')"; fi; }
_absent() { if grep -q "$3" "$2" 2>/dev/null; then _bad "$1 (found '$3')"; else _ok "$1"; fi; }

# --- guard: no CRLF in any deploy shell script -------------------------------
# Git Bash on Windows silently tolerates CRLF in bash scripts; bash on Linux
# (CI, the production host) fails with "$'\r': command not found". Detect the
# drift here, hermetically, before it ships.
test_no_crlf_in_deploy_shell_scripts() (
    deploy_root="$(cd "$HERE/.." && pwd)"
    found=0
    while IFS= read -r -d '' f; do
        if grep -qU $'\r' "$f"; then
            _bad "CRLF line endings in $f (normalize: sed -i 's/\\r\$//' \"$f\")"
            found=1
        fi
    done < <(find "$deploy_root" -name '*.sh' -type f -print0)
    [ "$found" -eq 0 ] && _ok "no CRLF in scripts/deploy shell scripts"
)

# --- ready green: manifest written, rollback never called -------------------
test_ready_green_writes_manifest_no_rollback() (
    export MANIFEST_PATH; MANIFEST_PATH="$(mktemp)"
    export READY_RETRIES=1 READY_SLEEP=0 APP_VERSION=1.24.0 GIT_COMMIT_SHA=abc123
    source "$HERE/deploy_readiness_gate.sh"
    set +e  # the lib runs with set -e; disable it here to assert on return codes
    _curl_ready() { return 0; }
    _docker() { echo "sha256:deadbeef"; return 0; }
    restore_rollback_point() { echo "ROLLBACK_CALLED"; return 0; }
    out="$(run_readiness_gate 2>&1)"; rc=$?
    _eq "green: gate returns 0" "$rc" 0
    printf '%s' "$out" >"$MANIFEST_PATH.log"
    _absent "green: rollback not called" "$MANIFEST_PATH.log" "ROLLBACK_CALLED"
    _has "green: manifest has version" "$MANIFEST_PATH" '"app_version": "1.24.0"'
    _has "green: manifest status deployed" "$MANIFEST_PATH" '"status": "deployed"'
    rm -f "$MANIFEST_PATH" "$MANIFEST_PATH.previous" "$MANIFEST_PATH.log"
)

# --- ready red then rollback recovers: gate returns 1 (deploy failed) --------
test_ready_red_then_rollback_recovers() (
    export MANIFEST_PATH; MANIFEST_PATH="$(mktemp)"; rm -f "$MANIFEST_PATH"
    export READY_RETRIES=1 READY_SLEEP=0
    source "$HERE/deploy_readiness_gate.sh"
    set +e  # the lib runs with set -e; disable it here to assert on return codes
    _ROLLED=0
    _curl_ready() { [ "$_ROLLED" -eq 1 ]; }
    _dc() { return 0; }
    restore_rollback_point() { _ROLLED=1; return 0; }
    run_readiness_gate >/dev/null 2>&1; rc=$?
    _eq "red+rollback: gate returns 1 (failed but restored)" "$rc" 1
)

# --- ready red, rollback impossible: gate returns 1 (critical) --------------
test_ready_red_rollback_fails_is_critical() (
    export MANIFEST_PATH; MANIFEST_PATH="$(mktemp)"; rm -f "$MANIFEST_PATH"
    export READY_RETRIES=1 READY_SLEEP=0
    source "$HERE/deploy_readiness_gate.sh"
    set +e  # the lib runs with set -e; disable it here to assert on return codes
    _curl_ready() { return 1; }
    restore_rollback_point() { return 1; }
    run_readiness_gate >/dev/null 2>&1; rc=$?
    _eq "red+no-rollback: gate returns 1 (critical)" "$rc" 1
)

# --- manifest rotation keeps the previous one -------------------------------
test_manifest_rotates_previous() (
    export MANIFEST_PATH; MANIFEST_PATH="$(mktemp)"
    echo '{"old":true}' >"$MANIFEST_PATH"
    export APP_VERSION=2.0.0 GIT_COMMIT_SHA=newsha
    source "$HERE/deploy_readiness_gate.sh"
    set +e  # the lib runs with set -e; disable it here to assert on return codes
    _docker() { echo "sha256:x"; }
    write_release_manifest >/dev/null 2>&1
    _has "rotate: .previous keeps old" "$MANIFEST_PATH.previous" '"old":true'
    _has "rotate: new manifest updated" "$MANIFEST_PATH" '2.0.0'
    rm -f "$MANIFEST_PATH" "$MANIFEST_PATH.previous"
)

echo "== deploy_readiness_gate.sh hermetic tests =="
test_no_crlf_in_deploy_shell_scripts
test_ready_green_writes_manifest_no_rollback
test_ready_red_then_rollback_recovers
test_ready_red_rollback_fails_is_critical
test_manifest_rotates_previous

fails="$(wc -l <"$FAILS_FILE" | tr -d ' ')"
echo "== assertion failures: ${fails} =="
[ "${fails}" -eq 0 ]
