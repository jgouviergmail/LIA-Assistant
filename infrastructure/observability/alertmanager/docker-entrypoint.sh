#!/bin/sh
# ===================================================================
# Docker Entrypoint Script for AlertManager
# ===================================================================
# Substitutes environment variables in the configuration template,
# removes unconfigured Slack/PagerDuty blocks, then starts AlertManager.
# ===================================================================

set -e

echo "================================================================"
echo "AlertManager Configuration Rendering"
echo "================================================================"

# ===== LIA SELF-DIAGNOSTICS WEBHOOK (spec 2026-08-27) =====
# When BOTH variables are set, inject the committed fragments into the
# rendered config: the route fragment right after the `  routes:` anchor,
# the receiver fragment appended at EOF. Two trivial operations on purpose —
# tests/unit/test_alertmanager_webhook_matrix.py replays exactly these and
# validates the whole matrix in CI.
inject_lia_webhook() {
    CONFIG="$1"
    [ -z "$ALERTMANAGER_LIA_WEBHOOK_URL" ] && return 0
    [ -z "$ALERTMANAGER_LIA_WEBHOOK_SECRET" ] && return 0
    sed -e "s|\${ALERTMANAGER_LIA_WEBHOOK_URL}|${ALERTMANAGER_LIA_WEBHOOK_URL}|g" \
        -e "s|\${ALERTMANAGER_LIA_WEBHOOK_SECRET}|${ALERTMANAGER_LIA_WEBHOOK_SECRET}|g" \
        /etc/alertmanager/lia-webhook-route.fragment > /tmp/lia-route.yml
    sed -e "s|\${ALERTMANAGER_LIA_WEBHOOK_URL}|${ALERTMANAGER_LIA_WEBHOOK_URL}|g" \
        -e "s|\${ALERTMANAGER_LIA_WEBHOOK_SECRET}|${ALERTMANAGER_LIA_WEBHOOK_SECRET}|g" \
        /etc/alertmanager/lia-webhook-receiver.fragment > /tmp/lia-receiver.yml
    sed -i "/^  routes:$/r /tmp/lia-route.yml" "$CONFIG"
    cat /tmp/lia-receiver.yml >> "$CONFIG"
    echo "LIA webhook: CONFIGURED (${ALERTMANAGER_LIA_WEBHOOK_URL})"
}

# ===== CHECK IF SMTP IS CONFIGURED =====
REQUIRED_VARS="ALERTMANAGER_SMTP_SMARTHOST ALERTMANAGER_SMTP_FROM ALERTMANAGER_SMTP_AUTH_USERNAME ALERTMANAGER_SMTP_AUTH_PASSWORD ALERTMANAGER_BACKEND_TEAM_EMAIL"
MISSING=""
for VAR in $REQUIRED_VARS; do
    eval VALUE=\$$VAR
    [ -z "$VALUE" ] && MISSING="$MISSING $VAR"
done

if [ -n "$MISSING" ]; then
    echo "WARNING: Missing SMTP variables:$MISSING"
    echo "Starting with minimal log-only configuration."

    # The `  routes:` anchor line exists only when the webhook will be
    # injected: an empty `routes:` key (null) is not a valid routes list.
    ROUTES_ANCHOR=""
    if [ -n "$ALERTMANAGER_LIA_WEBHOOK_URL" ] && [ -n "$ALERTMANAGER_LIA_WEBHOOK_SECRET" ]; then
        ROUTES_ANCHOR="  routes:"
    fi
    cat > /etc/alertmanager/alertmanager.yml << EOF
global:
  resolve_timeout: 5m
route:
  receiver: 'default-log'
  group_by: ['alertname', 'component', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
${ROUTES_ANCHOR}
inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'component']
receivers:
  - name: 'default-log'
EOF
    # Same injection helper as the full modes: a self-hosted instance without
    # SMTP still gets its incidents in-app when the webhook is configured.
    inject_lia_webhook /etc/alertmanager/alertmanager.yml
    exec /bin/alertmanager "$@"
fi

# ===== SET DEFAULTS =====
export ALERTMANAGER_FINANCE_TEAM_EMAIL="${ALERTMANAGER_FINANCE_TEAM_EMAIL:-${ALERTMANAGER_BACKEND_TEAM_EMAIL}}"
export ALERTMANAGER_SECURITY_TEAM_EMAIL="${ALERTMANAGER_SECURITY_TEAM_EMAIL:-${ALERTMANAGER_BACKEND_TEAM_EMAIL}}"
export ALERTMANAGER_ML_TEAM_EMAIL="${ALERTMANAGER_ML_TEAM_EMAIL:-${ALERTMANAGER_BACKEND_TEAM_EMAIL}}"

# ===== SELECT TEMPLATE =====
# Use email-only template when Slack/PagerDuty not configured
HAS_SLACK=""
HAS_PD=""
[ -n "$ALERTMANAGER_SLACK_WEBHOOK_CRITICAL" ] && HAS_SLACK=1
[ -n "$ALERTMANAGER_PAGERDUTY_ROUTING_KEY" ] && HAS_PD=1

if [ -n "$HAS_SLACK" ] || [ -n "$HAS_PD" ]; then
    TEMPLATE="/etc/alertmanager/alertmanager.yml.template"
    echo "Mode: Email + Slack/PagerDuty"
else
    TEMPLATE="/etc/alertmanager/alertmanager-email-only.yml.template"
    echo "Mode: Email only (no Slack/PagerDuty)"
fi

# ===== SUBSTITUTE VARIABLES =====
echo "Rendering configuration..."

sed -e "s|\${ALERTMANAGER_SMTP_SMARTHOST}|${ALERTMANAGER_SMTP_SMARTHOST}|g" \
    -e "s|\${ALERTMANAGER_SMTP_FROM}|${ALERTMANAGER_SMTP_FROM}|g" \
    -e "s|\${ALERTMANAGER_SMTP_AUTH_USERNAME}|${ALERTMANAGER_SMTP_AUTH_USERNAME}|g" \
    -e "s|\${ALERTMANAGER_SMTP_AUTH_PASSWORD}|${ALERTMANAGER_SMTP_AUTH_PASSWORD}|g" \
    -e "s|\${ALERTMANAGER_BACKEND_TEAM_EMAIL}|${ALERTMANAGER_BACKEND_TEAM_EMAIL}|g" \
    -e "s|\${ALERTMANAGER_FINANCE_TEAM_EMAIL}|${ALERTMANAGER_FINANCE_TEAM_EMAIL}|g" \
    -e "s|\${ALERTMANAGER_SECURITY_TEAM_EMAIL}|${ALERTMANAGER_SECURITY_TEAM_EMAIL}|g" \
    -e "s|\${ALERTMANAGER_ML_TEAM_EMAIL}|${ALERTMANAGER_ML_TEAM_EMAIL}|g" \
    -e "s|\${ALERTMANAGER_SLACK_WEBHOOK_CRITICAL}|${ALERTMANAGER_SLACK_WEBHOOK_CRITICAL}|g" \
    -e "s|\${ALERTMANAGER_SLACK_WEBHOOK_WARNING}|${ALERTMANAGER_SLACK_WEBHOOK_WARNING}|g" \
    -e "s|\${ALERTMANAGER_SLACK_WEBHOOK_SECURITY}|${ALERTMANAGER_SLACK_WEBHOOK_SECURITY}|g" \
    -e "s|\${ALERTMANAGER_PAGERDUTY_ROUTING_KEY}|${ALERTMANAGER_PAGERDUTY_ROUTING_KEY}|g" \
    "$TEMPLATE" > /etc/alertmanager/alertmanager.yml

inject_lia_webhook /etc/alertmanager/alertmanager.yml

echo "SMTP: ${ALERTMANAGER_SMTP_SMARTHOST}"
echo "From: ${ALERTMANAGER_SMTP_FROM}"
echo "To:   ${ALERTMANAGER_BACKEND_TEAM_EMAIL}"
[ -n "$HAS_SLACK" ] && echo "Slack: CONFIGURED" || echo "Slack: NOT CONFIGURED"
[ -n "$HAS_PD" ] && echo "PagerDuty: CONFIGURED" || echo "PagerDuty: NOT CONFIGURED"
echo ""

exec /bin/alertmanager "$@"
