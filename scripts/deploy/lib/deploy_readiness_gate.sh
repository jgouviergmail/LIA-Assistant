#!/usr/bin/env bash
# Readiness gate with provenance manifest + automatic rollback (audit F008).
#
# Sourced by the generated prod deploy.sh. Turns the previously text-only
# rollback into an operational one and records what was actually deployed:
#
#   1. before building, capture the currently-running images as a rollback point;
#   2. after `up`, poll /ready;
#   3. on success  -> write a release manifest (version, commit, build date,
#      image digests, timestamp), rotating the previous one to *.previous;
#   4. on failure  -> restore the captured images, recreate, re-check /ready, and
#      exit non-zero either way so the operator is never left guessing.
#
# Every command is guarded so a missing previous image (first deploy) degrades
# gracefully. All the docker/curl calls are indirected through functions so the
# gate is unit-testable by overriding them. Those hermetic tests live in the repo
# at scripts/deploy/lib/test_deploy_readiness_gate.sh (run in CI); the deploy
# bundle ships this library alone, not the test.

set -euo pipefail

# --- Indirections (overridable in tests) ------------------------------------
: "${COMPOSE_FILE:=docker-compose.prod.yml}"
: "${ROLLBACK_IMAGES:=lia-api:local lia-web:local}"  # explicit compose image tags
: "${MANIFEST_PATH:=release-manifest.json}"
: "${READY_URL:=https://localhost:8000/ready}"
: "${READY_URL_HTTP:=http://localhost:8000/ready}"
: "${READY_RETRIES:=30}"
: "${READY_SLEEP:=2}"

_dc() { docker compose -f "$COMPOSE_FILE" "$@"; }
_docker() { docker "$@"; }
_curl_ready() { curl -fsk "$READY_URL" >/dev/null 2>&1 || curl -fs "$READY_URL_HTTP" >/dev/null 2>&1; }
_now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# --- Rollback point ----------------------------------------------------------
# Tag each current image as ``<image>__rollback`` BEFORE the new build overwrites
# it, so a failed deploy can be reverted without a rebuild.
capture_rollback_point() {
    for img in $ROLLBACK_IMAGES; do
        if _docker image inspect "$img" >/dev/null 2>&1; then
            _docker tag "$img" "${img%%:*}:__rollback" || true
            echo "  -> rollback point captured: ${img%%:*}:__rollback"
        else
            echo "  -> no current '$img' (first deploy?) — rollback point skipped"
        fi
    done
}

restore_rollback_point() {
    local restored=0
    for img in $ROLLBACK_IMAGES; do
        local rb="${img%%:*}:__rollback"
        if _docker image inspect "$rb" >/dev/null 2>&1; then
            _docker tag "$rb" "$img" || true
            restored=1
        fi
    done
    [ "$restored" -eq 1 ] || { echo "  -> no rollback point to restore" >&2; return 1; }
    _dc up -d --force-recreate --no-build >/dev/null 2>&1 || return 1
    return 0
}

# --- Readiness ---------------------------------------------------------------
poll_ready() {
    local i
    for i in $(seq 1 "$READY_RETRIES"); do
        if _curl_ready; then return 0; fi
        sleep "$READY_SLEEP"
    done
    return 1
}

# --- Manifest ----------------------------------------------------------------
write_release_manifest() {
    [ -f "$MANIFEST_PATH" ] && cp -f "$MANIFEST_PATH" "${MANIFEST_PATH}.previous" 2>/dev/null || true
    local api_digest web_digest
    api_digest="$(_docker image inspect --format '{{.Id}}' lia-api:local 2>/dev/null || echo unknown)"
    web_digest="$(_docker image inspect --format '{{.Id}}' lia-web:local 2>/dev/null || echo unknown)"
    cat > "$MANIFEST_PATH" <<JSON
{
  "app_version": "${APP_VERSION:-unknown}",
  "git_commit_sha": "${GIT_COMMIT_SHA:-unknown}",
  "build_date": "${BUILD_DATE:-unknown}",
  "deployed_at": "$(_now_iso)",
  "api_image_id": "${api_digest}",
  "web_image_id": "${web_digest}",
  "status": "deployed"
}
JSON
    echo "  -> release manifest written: $MANIFEST_PATH (version ${APP_VERSION:-unknown}, commit ${GIT_COMMIT_SHA:-unknown})"
}

# --- Orchestrator ------------------------------------------------------------
# Call AFTER `docker compose ... up -d`. Returns 0 on ready, rolls back and
# returns 1 on failure.
run_readiness_gate() {
    echo "  -> Verification de la readiness (/ready)..."
    if poll_ready; then
        echo "  -> API prete (/ready OK)"
        write_release_manifest
        return 0
    fi

    echo "ERREUR: l'API n'est pas prete (/ready) apres readiness window." >&2
    echo "  -> Rollback automatique vers l'image precedente (F008)..." >&2
    if restore_rollback_point && poll_ready; then
        echo "  -> Rollback reussi: l'image precedente est de nouveau prete (/ready OK)." >&2
        echo "     Le deploiement a ECHOUE mais le service est restaure. Investiguer:" >&2
        echo "       _dc ps ; _dc logs --tail=120 api" >&2
        return 1
    fi
    echo "ERREUR CRITIQUE: rollback impossible ou toujours pas pret. Intervention manuelle requise." >&2
    echo "    docker compose -f $COMPOSE_FILE ps" >&2
    echo "    docker compose -f $COMPOSE_FILE logs --tail=120 api" >&2
    return 1
}
