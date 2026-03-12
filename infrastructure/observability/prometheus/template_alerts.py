#!/usr/bin/env python3
"""
Convert alerts.yml to alerts.yml.template by replacing hardcoded thresholds with Jinja2 variables.

This script performs systematic replacement of all 39 hardcoded thresholds identified in the analysis.

Usage:
    python template_alerts.py

Output:
    - alerts.yml.template (with Jinja2 placeholders)
    - Backup: alerts.yml.backup
"""

import re
from pathlib import Path
from datetime import datetime


# Complete mapping of all 39 thresholds
# Format: (line_pattern, threshold_value, env_var_name, description)
THRESHOLDS = [
    # Application (API) - 4 thresholds
    {
        'pattern': r'(\) \* 100 >) 5(\s+#.*)?$',
        'replacement': r'\1 {{ ALERT_API_ERROR_RATE_CRITICAL_PERCENT }}\2',
        'var_name': 'ALERT_API_ERROR_RATE_CRITICAL_PERCENT',
        'default': '5',
        'description': 'API error rate threshold (percentage)',
        'context': 'HighErrorRate alert'
    },
    {
        'pattern': r'(histogram_quantile.*service\)\s+\))\s*>\s*1(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_API_LATENCY_P95_WARNING_SECONDS }}\2',
        'var_name': 'ALERT_API_LATENCY_P95_WARNING_SECONDS',
        'default': '1',
        'description': 'API P95 latency threshold (seconds)',
        'context': 'HighLatencyP95 alert'
    },
    {
        'pattern': r'(histogram_quantile\(0\.99,\s*sum.*service\)\s+\))\s*>\s*2(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_API_LATENCY_P99_CRITICAL_SECONDS }}\2',
        'var_name': 'ALERT_API_LATENCY_P99_CRITICAL_SECONDS',
        'default': '2',
        'description': 'API P99 latency threshold (seconds)',
        'context': 'CriticalLatencyP99 alert'
    },
    {
        'pattern': r'(sum\(rate\(http_requests_total\[1m\]\)\) by \(service\)) > 1000',
        'replacement': r'\1 > {{ ALERT_API_REQUEST_RATE_RPS }}',
        'var_name': 'ALERT_API_REQUEST_RATE_RPS',
        'default': '1000',
        'description': 'API request rate threshold (requests per second)',
        'context': 'HighRequestQueueing alert'
    },

    # Database (PostgreSQL) - 3 thresholds
    {
        'pattern': r'(pg_settings_max_connections\s+\) \* 100) > 80(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_DB_CONNECTIONS_WARNING_PERCENT }}\2',
        'var_name': 'ALERT_DB_CONNECTIONS_WARNING_PERCENT',
        'default': '80',
        'description': 'Database connections warning threshold (percentage)',
        'context': 'HighDatabaseConnections alert'
    },
    {
        'pattern': r'(pg_settings_max_connections\s+\) \* 100) > 90(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_DB_CONNECTIONS_CRITICAL_PERCENT }}\2',
        'var_name': 'ALERT_DB_CONNECTIONS_CRITICAL_PERCENT',
        'default': '90',
        'description': 'Database connections critical threshold (percentage)',
        'context': 'CriticalDatabaseConnections alert'
    },
    {
        'pattern': r'(rate\(pg_stat_database_tup_fetched\{datname="lia"\}\[5m\]\)) > 100000',
        'replacement': r'\1 > {{ ALERT_DB_SLOW_QUERIES_TUPLES_PER_SEC }}',
        'var_name': 'ALERT_DB_SLOW_QUERIES_TUPLES_PER_SEC',
        'default': '100000',
        'description': 'Slow queries threshold (tuples per second)',
        'context': 'SlowQueries alert'
    },

    # Infrastructure - 5 thresholds
    {
        'pattern': r'(node_filesystem_size_bytes\{fstype!="tmpfs"\}\)\s+\) \* 100) > 85(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_DISK_USAGE_WARNING_PERCENT }}\2',
        'var_name': 'ALERT_DISK_USAGE_WARNING_PERCENT',
        'default': '85',
        'description': 'Disk usage warning threshold (percentage)',
        'context': 'DiskSpaceHigh alert'
    },
    {
        'pattern': r'(node_filesystem_size_bytes\{fstype!="tmpfs"\}\)\s+\) \* 100) > 95(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_DISK_USAGE_CRITICAL_PERCENT }}\2',
        'var_name': 'ALERT_DISK_USAGE_CRITICAL_PERCENT',
        'default': '95',
        'description': 'Disk usage critical threshold (percentage)',
        'context': 'DiskSpaceCritical alert'
    },
    {
        'pattern': r'(irate\(node_cpu_seconds_total\{mode="idle"\}\[5m\]\)\) \* 100\)) > 80',
        'replacement': r'\1 > {{ ALERT_CPU_USAGE_WARNING_PERCENT }}',
        'var_name': 'ALERT_CPU_USAGE_WARNING_PERCENT',
        'default': '80',
        'description': 'CPU usage warning threshold (percentage)',
        'context': 'HighCPUUsage alert'
    },
    {
        'pattern': r'(node_memory_MemTotal_bytes\)\s+\) \* 100) > 85(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_MEMORY_USAGE_WARNING_PERCENT }}\2',
        'var_name': 'ALERT_MEMORY_USAGE_WARNING_PERCENT',
        'default': '85',
        'description': 'Memory usage warning threshold (percentage)',
        'context': 'HighMemoryUsage alert'
    },
    {
        'pattern': r'(time\(\) - container_last_seen\{name=~"lia\.\*"\}) > 60',
        'replacement': r'\1 > {{ ALERT_CONTAINER_DOWN_SECONDS }}',
        'var_name': 'ALERT_CONTAINER_DOWN_SECONDS',
        'default': '60',
        'description': 'Container down timeout threshold (seconds)',
        'context': 'ContainerDown alert'
    },
    {
        'pattern': r'(rate\(container_start_time_seconds\{name=~"lia\.\*"\}\[15m\]\)) > 0\.1',
        'replacement': r'\1 > {{ ALERT_CONTAINER_RESTART_RATE }}',
        'var_name': 'ALERT_CONTAINER_RESTART_RATE',
        'default': '0.1',
        'description': 'Container restart rate threshold (restarts per second)',
        'context': 'ContainerRestartingFrequently alert'
    },

    # Redis - 2 thresholds
    {
        'pattern': r'(\(redis_memory_used_bytes / redis_memory_max_bytes\) \* 100) > 80',
        'replacement': r'\1 > {{ ALERT_REDIS_MEMORY_WARNING_PERCENT }}',
        'var_name': 'ALERT_REDIS_MEMORY_WARNING_PERCENT',
        'default': '80',
        'description': 'Redis memory usage warning threshold (percentage)',
        'context': 'RedisMemoryHigh alert'
    },
    {
        'pattern': r'(redis_connected_clients) > 100',
        'replacement': r'\1 > {{ ALERT_REDIS_CONNECTIONS_WARNING }}',
        'var_name': 'ALERT_REDIS_CONNECTIONS_WARNING',
        'default': '100',
        'description': 'Redis connections warning threshold (count)',
        'context': 'RedisConnectionsHigh alert'
    },

    # Agents - 5 thresholds
    {
        'pattern': r'(intention\)\s+\) \* 1000) > 1000(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_AGENTS_TTFT_P95_MS }}\2',
        'var_name': 'ALERT_AGENTS_TTFT_P95_MS',
        'default': '1000',
        'description': 'Agents Time-to-First-Token P95 threshold (milliseconds)',
        'context': 'AgentsTTFTViolation alert'
    },
    {
        'pattern': r'(intention\)\s+\)) < 20(\s+#.*)?$',
        'replacement': r'\1 < {{ ALERT_AGENTS_TOKENS_PER_SECOND_MIN }}\2',
        'var_name': 'ALERT_AGENTS_TOKENS_PER_SECOND_MIN',
        'default': '20',
        'description': 'Agents minimum tokens per second threshold',
        'context': 'AgentsTokensPerSecondLow alert'
    },
    {
        'pattern': r'(le\)\s+\) \* 1000) > 500(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_AGENTS_ROUTER_LATENCY_P95_MS }}\2',
        'var_name': 'ALERT_AGENTS_ROUTER_LATENCY_P95_MS',
        'default': '500',
        'description': 'Agents router latency P95 threshold (milliseconds)',
        'context': 'AgentsRouterLatencyHigh alert'
    },
    {
        'pattern': r'(sse_streaming_duration_seconds_count\[5m\]\)\s+\) \* 100) > 5(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_AGENTS_STREAMING_ERROR_RATE_PERCENT }}\2',
        'var_name': 'ALERT_AGENTS_STREAMING_ERROR_RATE_PERCENT',
        'default': '5',
        'description': 'Agents streaming error rate threshold (percentage)',
        'context': 'AgentsStreamingErrorRateHigh alert'
    },
    {
        'pattern': r'(router_decisions_total\[10m\]\)\s+\) \* 100) > 10(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_AGENTS_ROUTER_LOW_CONFIDENCE_PERCENT }}\2',
        'var_name': 'ALERT_AGENTS_ROUTER_LOW_CONFIDENCE_PERCENT',
        'default': '10',
        'description': 'Agents router low confidence rate threshold (percentage)',
        'context': 'AgentsRouterLowConfidenceHigh alert'
    },

    # Conversations - 5 thresholds
    {
        'pattern': r'(node_name\)\)) > 2\.0(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_CHECKPOINT_SAVE_P99_CRITICAL_SECONDS }}\2',
        'var_name': 'ALERT_CHECKPOINT_SAVE_P99_CRITICAL_SECONDS',
        'default': '2.0',
        'description': 'Checkpoint save P99 critical threshold (seconds)',
        'context': 'CheckpointSaveSlowCritical alert'
    },
    {
        'pattern': r'(node_name\)\)) > 1\.0(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_CHECKPOINT_SAVE_P99_WARNING_SECONDS }}\2',
        'var_name': 'ALERT_CHECKPOINT_SAVE_P99_WARNING_SECONDS',
        'default': '1.0',
        'description': 'Checkpoint save P99 warning threshold (seconds)',
        'context': 'CheckpointSaveSlowWarning alert'
    },
    {
        'pattern': r'(sum\(rate\(conversation_resets_total\[5m\]\)\)) > 0\.5',
        'replacement': r'\1 > {{ ALERT_CONVERSATION_RESET_RATE }}',
        'var_name': 'ALERT_CONVERSATION_RESET_RATE',
        'default': '0.5',
        'description': 'Conversation reset rate threshold (resets per second)',
        'context': 'HighConversationResetRate alert'
    },
    {
        'pattern': r'(node_name\)\)) > 50000(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_CHECKPOINT_SIZE_P95_BYTES }}\2',
        'var_name': 'ALERT_CHECKPOINT_SIZE_P95_BYTES',
        'default': '50000',
        'description': 'Checkpoint size P95 threshold (bytes)',
        'context': 'CheckpointSizeGrowing alert'
    },
    {
        'pattern': r'(conversation_active_users_total) > 10',
        'replacement': r'\1 > {{ ALERT_CONVERSATION_CREATION_MIN_USERS }}',
        'var_name': 'ALERT_CONVERSATION_CREATION_MIN_USERS',
        'default': '10',
        'description': 'Minimum active users before alerting on creation stall',
        'context': 'ConversationCreationStalled alert'
    },

    # LLM & Cost - 6 thresholds
    {
        'pattern': r'(llm_api_calls_total\[5m\]\)) > 0\.05',
        'replacement': r'\1 > {{ ALERT_LLM_API_FAILURE_RATE_PERCENT }}',
        'var_name': 'ALERT_LLM_API_FAILURE_RATE_PERCENT',
        'default': '0.05',
        'description': 'LLM API failure rate threshold (5% as 0.05)',
        'context': 'LLMAPIFailureRateHigh alert'
    },
    {
        'pattern': r'(llm_api_calls_total\[5m\]\)) < 0\.95',
        'replacement': r'\1 < {{ ALERT_LLM_API_SUCCESS_RATE_PERCENT }}',
        'var_name': 'ALERT_LLM_API_SUCCESS_RATE_PERCENT',
        'default': '0.95',
        'description': 'LLM API success rate threshold (95% as 0.95)',
        'context': 'LLMAPISuccessRateLow alert'
    },
    {
        'pattern': r'(sum\(increase\(llm_cost_total\{currency="EUR"\}\[24h\]\)\)) > 100',
        'replacement': r'\1 > {{ ALERT_LLM_DAILY_BUDGET_EUR }}',
        'var_name': 'ALERT_LLM_DAILY_BUDGET_EUR',
        'default': '100',
        'description': 'LLM daily budget threshold (EUR)',
        'context': 'DailyCostBudgetExceeded alert'
    },
    {
        'pattern': r'(sum\(increase\(llm_cost_total\{currency="EUR"\}\[1h\]\)\)) > 5',
        'replacement': r'\1 > {{ ALERT_LLM_HOURLY_BUDGET_EUR }}',
        'var_name': 'ALERT_LLM_HOURLY_BUDGET_EUR',
        'default': '5',
        'description': 'LLM hourly budget threshold (EUR)',
        'context': 'HourlyCostTrendingHigh alert'
    },
    {
        'pattern': r'(model\)) > 10(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_LLM_API_LATENCY_P99_SECONDS }}\2',
        'var_name': 'ALERT_LLM_API_LATENCY_P99_SECONDS',
        'default': '10',
        'description': 'LLM API latency P99 threshold (seconds)',
        'context': 'LLMAPILatencyHigh alert'
    },
    {
        'pattern': r'(sum by \(model\) \(increase\(llm_cost_total\{currency="EUR"\}\[24h\]\)\)) > 50',
        'replacement': r'\1 > {{ ALERT_LLM_MODEL_DAILY_BUDGET_EUR }}',
        'var_name': 'ALERT_LLM_MODEL_DAILY_BUDGET_EUR',
        'default': '50',
        'description': 'LLM model-specific daily budget threshold (EUR)',
        'context': 'ModelCostBudgetExceeded alert'
    },

    # Tokens - 2 thresholds
    {
        'pattern': r'(sum\(rate\(llm_tokens_consumed_total\[5m\]\)\)) > 1000',
        'replacement': r'\1 > {{ ALERT_LLM_TOKEN_CONSUMPTION_RATE }}',
        'var_name': 'ALERT_LLM_TOKEN_CONSUMPTION_RATE',
        'default': '1000',
        'description': 'LLM token consumption rate threshold (tokens per second)',
        'context': 'HighTokenConsumptionRate alert'
    },
    {
        'pattern': r'(prompt_tokens"\}\[10m\]\)\)) > 5(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_LLM_OUTPUT_INPUT_TOKEN_RATIO }}\2',
        'var_name': 'ALERT_LLM_OUTPUT_INPUT_TOKEN_RATIO',
        'default': '5',
        'description': 'LLM output/input token ratio threshold',
        'context': 'HighOutputTokenRatio alert'
    },

    # OAuth - 6 thresholds
    {
        'pattern': r'(oauth_callback_total\[5m\]\) by \(provider\)\s+\) \* 100) > 10(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_OAUTH_FAILURE_RATE_PERCENT }}\2',
        'var_name': 'ALERT_OAUTH_FAILURE_RATE_PERCENT',
        'default': '10',
        'description': 'OAuth failure rate threshold (percentage)',
        'context': 'HighOAuthFailureRate alert'
    },
    {
        'pattern': r'(rate\(oauth_pkce_validation_total\{result="failed"\}\[5m\]\)) > 0\.1',
        'replacement': r'\1 > {{ ALERT_OAUTH_PKCE_FAILURE_RATE }}',
        'var_name': 'ALERT_OAUTH_PKCE_FAILURE_RATE',
        'default': '0.1',
        'description': 'OAuth PKCE validation failure rate threshold (failures per second)',
        'context': 'PKCEValidationFailures alert'
    },
    {
        'pattern': r'(rate\(oauth_state_validation_total\{result="failed"\}\[5m\]\)) > 0\.1',
        'replacement': r'\1 > {{ ALERT_OAUTH_STATE_FAILURE_RATE }}',
        'var_name': 'ALERT_OAUTH_STATE_FAILURE_RATE',
        'default': '0.1',
        'description': 'OAuth state token validation failure rate threshold (failures per second)',
        'context': 'StateTokenValidationFailures alert'
    },
    {
        'pattern': r'(provider\)\s+\)) > 5(\s+#.*)?$',
        'replacement': r'\1 > {{ ALERT_OAUTH_CALLBACK_LATENCY_P95_SECONDS }}\2',
        'var_name': 'ALERT_OAUTH_CALLBACK_LATENCY_P95_SECONDS',
        'default': '5',
        'description': 'OAuth callback latency P95 threshold (seconds)',
        'context': 'SlowOAuthCallback alert'
    },
    {
        'pattern': r'(rate\(oauth_provider_errors_total\[5m\]\)) > 0\.5',
        'replacement': r'\1 > {{ ALERT_OAUTH_PROVIDER_ERROR_RATE }}',
        'var_name': 'ALERT_OAUTH_PROVIDER_ERROR_RATE',
        'default': '0.5',
        'description': 'OAuth provider error rate threshold (errors per second)',
        'context': 'OAuthProviderErrors alert'
    },
    {
        'pattern': r'(rate\(oauth_callback_total\[1m\]\)) > 10',
        'replacement': r'\1 > {{ ALERT_OAUTH_CALLBACK_SPIKE_RATE }}',
        'var_name': 'ALERT_OAUTH_CALLBACK_SPIKE_RATE',
        'default': '10',
        'description': 'OAuth callback spike detection threshold (callbacks per second)',
        'context': 'OAuthCallbackSpike alert'
    },
]


def backup_file(file_path: Path):
    """Create timestamped backup of file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.parent / f"{file_path.stem}.backup.{timestamp}{file_path.suffix}"
    backup_path.write_text(file_path.read_text(encoding='utf-8'), encoding='utf-8')
    print(f"[OK] Backup created: {backup_path.name}")
    return backup_path


def template_alerts_file(alerts_path: Path, template_path: Path):
    """
    Convert alerts.yml to alerts.yml.template by replacing hardcoded thresholds.
    """
    print(f"Reading {alerts_path}...")
    content = alerts_path.read_text(encoding='utf-8')

    # Create backup
    backup_path = backup_file(alerts_path)

    # Track replacements
    replacements_made = []

    # Apply each threshold replacement
    for threshold in THRESHOLDS:
        pattern = threshold['pattern']
        replacement = threshold['replacement']
        var_name = threshold['var_name']
        context = threshold['context']

        # Perform replacement
        new_content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)

        if count > 0:
            content = new_content
            replacements_made.append({
                'var_name': var_name,
                'count': count,
                'context': context
            })
            print(f"  [OK] Replaced {var_name} ({count} occurrence{'s' if count > 1 else ''}) - {context}")
        else:
            print(f"  [WARN] Pattern not found for {var_name} - {context}")

    # Add header comment
    header = """# Alerting rules for LIA (TEMPLATE)
#
# This file is a Jinja2 template. Thresholds are externalized in .env.alerting.{environment}
#
# To generate alerts.yml:
#   python render_alerts.py --env production
#   python render_alerts.py --env staging
#   python render_alerts.py --env development
#
# Available variables: 39 thresholds (see .env.alerting.example)
#
"""
    content = header + content[content.index('groups:'):]

    # Write template
    template_path.write_text(content, encoding='utf-8')
    print(f"\n[OK] Template created: {template_path}")

    # Print summary
    print(f"\nSummary:")
    print(f"  Total replacements: {len(replacements_made)}")
    print(f"  Unique variables: {len(set(r['var_name'] for r in replacements_made))}")
    print(f"  Backup: {backup_path}")
    print(f"  Template: {template_path}")

    return replacements_made


if __name__ == "__main__":
    script_dir = Path(__file__).parent
    alerts_path = script_dir / "alerts.yml"
    template_path = script_dir / "alerts.yml.template"

    if not alerts_path.exists():
        print(f"ERROR: {alerts_path} not found!")
        exit(1)

    print("=" * 80)
    print("CONVERTING alerts.yml TO alerts.yml.template")
    print("=" * 80)
    print()

    replacements = template_alerts_file(alerts_path, template_path)

    print("\n" + "=" * 80)
    print("[SUCCESS] CONVERSION COMPLETE")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Review alerts.yml.template to verify all replacements")
    print("  2. Update .env.alerting.example with all 39 variables")
    print("  3. Create environment-specific files (.env.alerting.production, etc.)")
    print("  4. Test rendering: python render_alerts.py --env production --dry-run")
