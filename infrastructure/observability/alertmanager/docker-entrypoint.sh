#!/bin/sh
# ===================================================================
# Docker Entrypoint Script for AlertManager
# ===================================================================
# Renders /etc/alertmanager/alertmanager.yml from the template and the
# ALERTMANAGER_* variables, then starts AlertManager. `--render-only <path>`
# writes the rendered config to <path> and exits: the routing matrix gate
# (`task test:alertmanager`) renders through THIS script, in the production
# image, and checks what it wrote with amtool (audit A07).
#
# Rendering, in order:
#   1. no SMTP: a log-only config (plus the LIA webhook when configured);
#   2. otherwise the template, minus every `# @begin <name>`/`# @end <name>`
#      block whose channel or team is not configured (table below);
#   3. every ${ALERTMANAGER_*} placeholder replaced LITERALLY — `&`, `|`, `\`
#      reach the config as typed — its single quotes doubled for YAML;
#   4. the LIA webhook fragments, rendered the same way, when configured.
#
#   block           kept when
#   slack-critical  ALERTMANAGER_SLACK_WEBHOOK_CRITICAL is set
#   pagerduty       ALERTMANAGER_PAGERDUTY_ROUTING_KEY is set
#   slack-warning   ALERTMANAGER_SLACK_WEBHOOK_WARNING is set
#   team-ml         ALERTMANAGER_ML_TEAM_EMAIL is set and not the backend's
#   email-security  ALERTMANAGER_SECURITY_TEAM_EMAIL is set and not the backend's
#   slack-security  ALERTMANAGER_SLACK_WEBHOOK_SECURITY is set and not the critical one
#   team-security   email-security or slack-security is kept
#
# A team told what the backend is told, on the same address or channel, would
# be told twice: severity fixes the urgency, the component adds an audience.
# ===================================================================

set -e

TEMPLATE="/etc/alertmanager/alertmanager.yml.template"
OUTPUT="/etc/alertmanager/alertmanager.yml"
RENDER_ONLY=""
if [ "$1" = "--render-only" ]; then
    [ -n "$2" ] || { echo "ERROR: --render-only needs an output path" >&2; exit 64; }
    RENDER_ONLY=1
    OUTPUT="$2"
    shift 2
fi

echo "================================================================"
echo "AlertManager Configuration Rendering"
echo "================================================================"

# A line break in a value would end its YAML scalar and write a line of its
# own: such a value is refused, never rendered.
NL='
'
for VAR in ALERTMANAGER_SMTP_SMARTHOST ALERTMANAGER_SMTP_FROM \
    ALERTMANAGER_SMTP_AUTH_USERNAME ALERTMANAGER_SMTP_AUTH_PASSWORD \
    ALERTMANAGER_BACKEND_TEAM_EMAIL \
    ALERTMANAGER_SECURITY_TEAM_EMAIL ALERTMANAGER_ML_TEAM_EMAIL \
    ALERTMANAGER_SLACK_WEBHOOK_CRITICAL ALERTMANAGER_SLACK_WEBHOOK_WARNING \
    ALERTMANAGER_SLACK_WEBHOOK_SECURITY ALERTMANAGER_PAGERDUTY_ROUTING_KEY \
    ALERTMANAGER_LIA_WEBHOOK_URL ALERTMANAGER_LIA_WEBHOOK_SECRET; do
    eval VALUE=\$$VAR
    case "$VALUE" in
        *"$NL"*)
            echo "ERROR: $VAR holds a line break: refusing to render it" >&2
            exit 65
            ;;
    esac
done

# Replace every ${ALERTMANAGER_*} placeholder of $1 by its variable, literally,
# its single quotes doubled; awk reads the values from ENVIRON, so nothing in a
# value is ever interpreted as a pattern or a replacement.
render_placeholders() {
    awk -v q="'" '
        {
            line = $0
            out = ""
            while (match(line, /\$\{ALERTMANAGER_[A-Z0-9_]+\}/)) {
                value = ENVIRON[substr(line, RSTART + 2, RLENGTH - 3)]
                gsub(q, q q, value)
                out = out substr(line, 1, RSTART - 1) value
                line = substr(line, RSTART + RLENGTH)
            }
            print out line
        }' "$1"
}

# Remove every `# @begin $1` ... `# @end $1` range of the file $2.
drop_block() {
    sed -i "/# @begin $1\$/,/# @end $1\$/d" "$2"
}

lower() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

# Whether the team address $1 is set and is not the backend team's own.
own_team_address() {
    [ -n "$1" ] && [ "$(lower "$1")" != "$(lower "$ALERTMANAGER_BACKEND_TEAM_EMAIL")" ]
}

# ===== LIA SELF-DIAGNOSTICS WEBHOOK (spec 2026-08-27) =====
# When BOTH variables are set, the route fragment goes right after the
# `  routes:` anchor (the first child route, `continue: true`) and the
# receiver fragment at EOF — rendered by the same literal substitution.
inject_lia_webhook() {
    [ -z "$ALERTMANAGER_LIA_WEBHOOK_URL" ] && return 0
    [ -z "$ALERTMANAGER_LIA_WEBHOOK_SECRET" ] && return 0
    render_placeholders /etc/alertmanager/lia-webhook-route.fragment > /tmp/lia-route.yml
    render_placeholders /etc/alertmanager/lia-webhook-receiver.fragment > /tmp/lia-receiver.yml
    sed -i "/^  routes:$/r /tmp/lia-route.yml" "$1"
    cat /tmp/lia-receiver.yml >> "$1"
    rm -f /tmp/lia-route.yml /tmp/lia-receiver.yml
    echo "LIA webhook: CONFIGURED (${ALERTMANAGER_LIA_WEBHOOK_URL})"
}

start() {
    if [ -n "$RENDER_ONLY" ]; then
        echo "Rendered to ${OUTPUT}"
        exit 0
    fi
    exec /bin/alertmanager "$@"
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
    cat > "$OUTPUT" << EOF
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
    # Same injection helper as the full mode: a self-hosted instance without
    # SMTP still gets its incidents in-app when the webhook is configured.
    inject_lia_webhook "$OUTPUT"
    start "$@"
fi

# ===== DROP WHAT IS NOT CONFIGURED =====
WORK="$(mktemp)"
cp "$TEMPLATE" "$WORK"
[ -n "$ALERTMANAGER_SLACK_WEBHOOK_CRITICAL" ] || drop_block slack-critical "$WORK"
[ -n "$ALERTMANAGER_PAGERDUTY_ROUTING_KEY" ] || drop_block pagerduty "$WORK"
[ -n "$ALERTMANAGER_SLACK_WEBHOOK_WARNING" ] || drop_block slack-warning "$WORK"
own_team_address "$ALERTMANAGER_ML_TEAM_EMAIL" || drop_block team-ml "$WORK"
SECURITY_EMAIL=""
SECURITY_SLACK=""
own_team_address "$ALERTMANAGER_SECURITY_TEAM_EMAIL" && SECURITY_EMAIL=1
[ -n "$ALERTMANAGER_SLACK_WEBHOOK_SECURITY" ] \
    && [ "$ALERTMANAGER_SLACK_WEBHOOK_SECURITY" != "$ALERTMANAGER_SLACK_WEBHOOK_CRITICAL" ] \
    && SECURITY_SLACK=1
[ -n "$SECURITY_EMAIL" ] || drop_block email-security "$WORK"
[ -n "$SECURITY_SLACK" ] || drop_block slack-security "$WORK"
[ -n "$SECURITY_EMAIL$SECURITY_SLACK" ] || drop_block team-security "$WORK"
sed -i '/# @begin [a-z-]*$/d; /# @end [a-z-]*$/d' "$WORK"

# ===== SUBSTITUTE, THEN INJECT =====
echo "Rendering configuration..."
render_placeholders "$WORK" > "$OUTPUT"
rm -f "$WORK"
inject_lia_webhook "$OUTPUT"
if grep -q '\${ALERTMANAGER_' "$OUTPUT"; then
    echo "ERROR: unsubstituted placeholders remain in ${OUTPUT}" >&2
    exit 70
fi

# The e-mail addresses, the Slack webhooks and the keys are configured, never
# printed (the SMTP relay's host and the LIA webhook's internal URL carry no secret,
# and are): this banner reaches Loki like every other log line (ADR-317). Their
# states are computed first, so no line that prints names one of them.
state() { [ -n "$1" ] && printf 'CONFIGURED' || printf 'NOT CONFIGURED'; }
SLACK_CRITICAL_STATE="$(state "$ALERTMANAGER_SLACK_WEBHOOK_CRITICAL")"
SLACK_WARNING_STATE="$(state "$ALERTMANAGER_SLACK_WEBHOOK_WARNING")"
PAGERDUTY_STATE="$(state "$ALERTMANAGER_PAGERDUTY_ROUTING_KEY")"
ML_STATE="NOT ROUTED (no address of its own)"
SECURITY_STATE="NOT ROUTED (no address or channel of its own)"
own_team_address "$ALERTMANAGER_ML_TEAM_EMAIL" && ML_STATE="ROUTED"
[ -n "$SECURITY_EMAIL$SECURITY_SLACK" ] && SECURITY_STATE="ROUTED"
echo "SMTP: ${ALERTMANAGER_SMTP_SMARTHOST}"
echo "From: CONFIGURED"
echo "To:   CONFIGURED"
echo "Slack critical: ${SLACK_CRITICAL_STATE}"
echo "Slack warning: ${SLACK_WARNING_STATE}"
echo "PagerDuty: ${PAGERDUTY_STATE}"
echo "ML team: ${ML_STATE}"
echo "Security team: ${SECURITY_STATE}"
echo ""

start "$@"
