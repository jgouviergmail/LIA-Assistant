#!/bin/sh
# ===================================================================
# Docker Entrypoint Script for AlertManager
# ===================================================================
# This script substitutes environment variables in the AlertManager
# configuration template before starting AlertManager
#
# Variables substituted:
#   SMTP Configuration:
#     - ALERTMANAGER_SMTP_SMARTHOST
#     - ALERTMANAGER_SMTP_FROM
#     - ALERTMANAGER_SMTP_AUTH_USERNAME
#     - ALERTMANAGER_SMTP_AUTH_PASSWORD
#
#   Email Recipients:
#     - ALERTMANAGER_BACKEND_TEAM_EMAIL
#     - ALERTMANAGER_FINANCE_TEAM_EMAIL
#     - ALERTMANAGER_SECURITY_TEAM_EMAIL
#     - ALERTMANAGER_ML_TEAM_EMAIL
#
#   Slack Webhooks (optional):
#     - ALERTMANAGER_SLACK_WEBHOOK_CRITICAL
#     - ALERTMANAGER_SLACK_WEBHOOK_WARNING
#     - ALERTMANAGER_SLACK_WEBHOOK_SECURITY
#
#   PagerDuty (optional):
#     - ALERTMANAGER_PAGERDUTY_ROUTING_KEY
# ===================================================================

set -e

echo "================================================================"
echo "AlertManager Configuration Rendering"
echo "================================================================"
echo ""
echo "Substituting environment variables in alertmanager config..."
echo ""

# ===== VALIDATE REQUIRED VARIABLES =====
echo "[1/3] Validating required environment variables..."

REQUIRED_VARS="ALERTMANAGER_SMTP_SMARTHOST ALERTMANAGER_SMTP_FROM ALERTMANAGER_SMTP_AUTH_USERNAME ALERTMANAGER_SMTP_AUTH_PASSWORD ALERTMANAGER_BACKEND_TEAM_EMAIL"
MISSING_VARS=""

for VAR in $REQUIRED_VARS; do
    eval VALUE=\$$VAR
    if [ -z "$VALUE" ]; then
        MISSING_VARS="$MISSING_VARS $VAR"
    fi
done

if [ -n "$MISSING_VARS" ]; then
    echo "ERROR: Missing required environment variables:$MISSING_VARS"
    echo ""
    echo "Please set these variables in your .env file:"
    for VAR in $MISSING_VARS; do
        echo "  $VAR=your-value"
    done
    exit 1
fi

echo "  OK - All required variables are set"
echo ""

# ===== SET DEFAULT VALUES FOR OPTIONAL VARIABLES =====
echo "[2/3] Setting defaults for optional variables..."

# Team emails (fallback to backend team)
export ALERTMANAGER_FINANCE_TEAM_EMAIL="${ALERTMANAGER_FINANCE_TEAM_EMAIL:-${ALERTMANAGER_BACKEND_TEAM_EMAIL}}"
export ALERTMANAGER_SECURITY_TEAM_EMAIL="${ALERTMANAGER_SECURITY_TEAM_EMAIL:-${ALERTMANAGER_BACKEND_TEAM_EMAIL}}"
export ALERTMANAGER_ML_TEAM_EMAIL="${ALERTMANAGER_ML_TEAM_EMAIL:-${ALERTMANAGER_BACKEND_TEAM_EMAIL}}"

# Slack webhooks (empty if not configured - will be ignored by AlertManager)
export ALERTMANAGER_SLACK_WEBHOOK_CRITICAL="${ALERTMANAGER_SLACK_WEBHOOK_CRITICAL:-}"
export ALERTMANAGER_SLACK_WEBHOOK_WARNING="${ALERTMANAGER_SLACK_WEBHOOK_WARNING:-}"
export ALERTMANAGER_SLACK_WEBHOOK_SECURITY="${ALERTMANAGER_SLACK_WEBHOOK_SECURITY:-}"

# PagerDuty routing key (empty if not configured)
export ALERTMANAGER_PAGERDUTY_ROUTING_KEY="${ALERTMANAGER_PAGERDUTY_ROUTING_KEY:-}"

echo "  OK - Defaults set"
echo ""

# ===== SUBSTITUTE VARIABLES IN TEMPLATE =====
echo "[3/3] Rendering configuration template..."

# Use sed to substitute all variables
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
    /etc/alertmanager/alertmanager.yml.template > /etc/alertmanager/alertmanager.yml.tmp

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to render configuration template"
    exit 1
fi

# ===== POST-PROCESS: REMOVE EMPTY SLACK/PAGERDUTY CONFIGS =====
# Remove slack_configs blocks with empty api_url (pattern: api_url: '')
# Remove pagerduty_configs blocks with empty routing_key (pattern: routing_key: '')
# This allows graceful degradation when Slack/PagerDuty are not configured

# Create a temporary script to process the configuration
cat > /tmp/clean_config.awk << 'AWK_SCRIPT'
BEGIN {
    in_slack_block = 0
    in_pagerduty_block = 0
    slack_buffer = ""
    pd_buffer = ""
    has_empty_slack = 0
    has_empty_pd = 0
}

# Detect slack_configs block start
/^ {4,}slack_configs:/ {
    in_slack_block = 1
    slack_buffer = $0 "\n"
    has_empty_slack = 0
    next
}

# Inside slack_configs block
in_slack_block {
    slack_buffer = slack_buffer $0 "\n"

    # Check for empty api_url
    if ($0 ~ /api_url: ''/) {
        has_empty_slack = 1
    }

    # End of slack block (next receiver section or pagerduty/email configs)
    if ($0 ~ /^ {4,}(pagerduty_configs|email_configs):/ || $0 ~ /^ {2,}- name:/) {
        # Don't output if empty
        if (!has_empty_slack) {
            printf "%s", slack_buffer
        }
        in_slack_block = 0
        slack_buffer = ""

        # If this line starts a new section, process it normally
        if ($0 ~ /^ {4,}pagerduty_configs:/) {
            in_pagerduty_block = 1
            pd_buffer = $0 "\n"
            has_empty_pd = 0
            next
        } else {
            print
            next
        }
    }
    next
}

# Detect pagerduty_configs block start
/^ {4,}pagerduty_configs:/ {
    in_pagerduty_block = 1
    pd_buffer = $0 "\n"
    has_empty_pd = 0
    next
}

# Inside pagerduty_configs block
in_pagerduty_block {
    pd_buffer = pd_buffer $0 "\n"

    # Check for empty routing_key
    if ($0 ~ /routing_key: ''/) {
        has_empty_pd = 1
    }

    # End of pagerduty block
    if ($0 ~ /^ {4,}(slack_configs|email_configs):/ || $0 ~ /^ {2,}- name:/) {
        # Don't output if empty
        if (!has_empty_pd) {
            printf "%s", pd_buffer
        }
        in_pagerduty_block = 0
        pd_buffer = ""
        print
        next
    }
    next
}

# Regular lines (not in slack or pagerduty blocks)
{
    print
}

END {
    # Flush any remaining buffers
    if (in_slack_block && !has_empty_slack) {
        printf "%s", slack_buffer
    }
    if (in_pagerduty_block && !has_empty_pd) {
        printf "%s", pd_buffer
    }
}
AWK_SCRIPT

# Apply the cleaning script
awk -f /tmp/clean_config.awk /etc/alertmanager/alertmanager.yml.tmp > /etc/alertmanager/alertmanager.yml

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to post-process configuration"
    exit 1
fi

rm /tmp/clean_config.awk /etc/alertmanager/alertmanager.yml.tmp

echo "  OK - Configuration rendered and cleaned successfully"
echo ""

# ===== DISPLAY CONFIG SUMMARY =====
echo "================================================================"
echo "Configuration Summary"
echo "================================================================"
echo "SMTP Server:        ${ALERTMANAGER_SMTP_SMARTHOST}"
echo "SMTP From:          ${ALERTMANAGER_SMTP_FROM}"
echo "Backend Team Email: ${ALERTMANAGER_BACKEND_TEAM_EMAIL}"
echo "Finance Team Email: ${ALERTMANAGER_FINANCE_TEAM_EMAIL}"
echo "Security Team Email: ${ALERTMANAGER_SECURITY_TEAM_EMAIL}"
echo "ML Team Email:      ${ALERTMANAGER_ML_TEAM_EMAIL}"
echo ""
echo "Optional Integrations:"
if [ -n "$ALERTMANAGER_SLACK_WEBHOOK_CRITICAL" ]; then
    echo "  Slack Critical:   CONFIGURED"
else
    echo "  Slack Critical:   NOT CONFIGURED (email only)"
fi
if [ -n "$ALERTMANAGER_SLACK_WEBHOOK_WARNING" ]; then
    echo "  Slack Warning:    CONFIGURED"
else
    echo "  Slack Warning:    NOT CONFIGURED (email only)"
fi
if [ -n "$ALERTMANAGER_SLACK_WEBHOOK_SECURITY" ]; then
    echo "  Slack Security:   CONFIGURED"
else
    echo "  Slack Security:   NOT CONFIGURED (email only)"
fi
if [ -n "$ALERTMANAGER_PAGERDUTY_ROUTING_KEY" ]; then
    echo "  PagerDuty:        CONFIGURED"
else
    echo "  PagerDuty:        NOT CONFIGURED (email/Slack only)"
fi
echo ""

# ===== DISPLAY FIRST 30 LINES OF RENDERED CONFIG =====
echo "================================================================"
echo "Rendered Configuration (first 30 lines)"
echo "================================================================"
head -30 /etc/alertmanager/alertmanager.yml
echo ""
echo "... (configuration continues)"
echo ""

# ===== START ALERTMANAGER =====
echo "================================================================"
echo "Starting AlertManager..."
echo "================================================================"
echo ""

# Execute AlertManager with all provided arguments
exec /bin/alertmanager "$@"
