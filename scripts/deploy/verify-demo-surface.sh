#!/usr/bin/env sh
# Is the demonstrator's closed surface still closed, seen from the network?
#
# Run ON the Docker host. It joins the demonstrator's ingress network — the
# same place the Cloudflare tunnel sits — and asks the edge directly, so it
# measures what a visitor reaches rather than what a config file says.
#
# Why a file and not a line inside the PowerShell driver: this check crosses
# three shells (PowerShell, ssh's argument reassembly, the remote shell) and
# every one of them owns the quote character. The version that lived inline
# had been unparseable since it was written and nobody noticed, because
# `verify` had never been run against the host (measured 2026-08-07: `sh -n`
# refused it — "unexpected EOF while looking for matching quote"). Complex
# shell belongs in a file that a shell can check.
#
# Exit 0 when the surface is intact, 1 when anything moved.
#
# Created: 2026-08-07 (live-demonstrator programme, production handover)
set -eu

PROJECT="${DEMO_COMPOSE_PROJECT:-lia-demo-instance}"
NETWORK="${PROJECT}_demo-instance-ingress"
CURL_IMAGE="${DEMO_VERIFY_CURL_IMAGE:-curlimages/curl:8.11.1}"

#: Paths a visitor must NEVER reach. Each one is a decision recorded in the
#: edge allowlist; a 200 here means the surface widened without review.
CLOSED="/api/v1/connectors/gmail/authorize
/api/v1/auth/google/login
/api/v1/auth/apple/login
/api/v1/admin/capabilities
/api/v1/usage-limits/admin/instance-daily-budget
/metrics"

#: Paths the product needs. A 404 here means the allowlist was narrowed until
#: the demonstrator stopped working — the failure mode that cost seven prefixes
#: and an empty personality picker on 2026-08-07.
OPEN="/api/v1/auth/login
/api/v1/auth/register
/api/v1/capabilities"

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
    echo "ERROR: network $NETWORK not found — is the demonstrator running?" >&2
    exit 1
fi

probe() {
    docker run --rm --network "$NETWORK" "$CURL_IMAGE" \
        curl -s -o /dev/null -w '%{http_code}' "http://demo-instance-edge$1" 2>/dev/null || echo 000
}

fail=0

for path in $CLOSED; do
    code=$(probe "$path")
    printf '  %s  %s\n' "$code" "$path"
    [ "$code" = "404" ] || { echo "      ^ attendu 404 — cette route est atteignable" >&2; fail=1; }
done

for path in $OPEN; do
    code=$(probe "$path")
    printf '  %s  %s (doit repondre)\n' "$code" "$path"
    [ "$code" = "404" ] && { echo "      ^ 404 — le produit ne peut pas fonctionner" >&2; fail=1; }
done

# --- La surface la plus exterieure : un visiteur, depuis Internet ----------
#
# Tout ce qui precede regarde la pile depuis l'interieur du reseau d'ingress.
# Un visiteur, lui, arrive par Cloudflare, et ce dernier tronçon peut etre
# rompu alors que TOUT le reste est sain -- mesure le 2026-08-07 : conteneurs
# up et healthy, /ready `ready`, DNS correct, TLS valide, et malgre cela une
# page morte, parce qu'aucun hostname public n'etait associe au tunnel.
# cloudflared le disait dans ses journaux et nulle part ailleurs :
#
#   WRN No ingress rules were defined in provided config (if any) nor from
#       the cli, cloudflared will return 503 for all incoming HTTP requests
#
# Un tunnel a jeton recoit sa configuration du tableau de bord, jamais du
# conteneur : rien dans ce depot ne peut la porter, donc rien ici ne peut la
# corriger. Ce que ce depot PEUT faire, c'est refuser de dire "OK" pendant
# qu'une page morte fait face au monde.
ENV_FILE="${DEMO_ENV_FILE:-.env.demo-instance.prod}"
if [ -f "$ENV_FILE" ]; then
    # `tr -d '\r'` : le fichier est redige sous Windows et copie tel quel, donc
    # chaque valeur porte un retour chariot -- qui rend l URL malformee et
    # ecrase le diagnostic en renvoyant le terminal en colonne zero.
    public=$(grep '^FRONTEND_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r' || true)
fi
if [ -n "${public:-}" ]; then
    body=$(curl -s --max-time 20 "$public/" 2>/dev/null | head -c 200 || true)
    if code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$public/" 2>/dev/null); then :; fi
    if [ "${code:-000}" = "000" ]; then
        echo "  PUBLIC: $public injoignable (ni DNS ni TLS)" >&2
        fail=1
    elif [ "${code:-000}" -ge 500 ] && [ -z "$body" ]; then
        echo "  PUBLIC: $public -> HTTP $code, corps vide : c est Cloudflare qui repond," >&2
        echo "          pas la pile. Cause la plus frequente : aucun hostname public" >&2
        echo "          associe au tunnel. A ajouter dans Zero Trust > Networks >" >&2
        echo "          Tunnels > (ce tunnel) > Public Hostname :" >&2
        echo "            hostname = $(printf '%s' "$public" | sed -e 's#^https\{0,1\}://##' -e 's#/.*##')" >&2
        echo "            service  = http://demo-instance-edge:80" >&2
        echo "          Verifier aussi : docker compose logs demo-instance-tunnel" >&2
        fail=1
    else
        printf '  %s  %s (vu depuis Internet)\n' "$code" "$public"
    fi
fi

if [ "$fail" -ne 0 ]; then
    echo "SURFACE REGRESSED" >&2
    exit 1
fi
echo "surface OK"
