#!/usr/bin/env python3
"""
Render alerts.yml from alerts.yml.template with environment-specific thresholds.

This script:
1. Loads environment variables from .env.alerting.{environment}
2. Renders alerts.yml.template with Jinja2
3. Validates generated YAML syntax
4. Outputs to alerts.yml (or specified output)

Usage:
    # Production
    python render_alerts.py --env production

    # Staging
    python render_alerts.py --env staging

    # Development
    python render_alerts.py --env development

    # Custom env file
    python render_alerts.py --env-file /path/to/custom.env

Requirements:
    pip install jinja2 pyyaml python-dotenv
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict

try:
    import yaml
    from jinja2 import Template, Environment, FileSystemLoader, StrictUndefined
    from dotenv import dotenv_values
except ImportError as e:
    print(f"ERROR: Missing required package: {e}")
    print("Install with: pip install jinja2 pyyaml python-dotenv")
    sys.exit(1)


# Threshold mapping: Alert expression pattern -> Environment variable name
THRESHOLD_MAPPING = {
    # Application (API)
    r') * 100 > 5\n        for: 5m\n        labels:\n          severity: critical\n          component: api':
        ('ALERT_API_ERROR_RATE_CRITICAL_PERCENT', '5'),

    r') > 1\n        for: 5m\n        labels:\n          severity: warning\n          component: api\n        annotations:\n          summary: "Latence P95':
        ('ALERT_API_LATENCY_P95_WARNING_SECONDS', '1'),

    r') > 2\n        for: 5m\n        labels:\n          severity: critical\n          component: api\n        annotations:\n          summary: "Latence P99':
        ('ALERT_API_LATENCY_P99_CRITICAL_SECONDS', '2'),

    r'sum(rate(http_requests_total[1m])) by (service) > 1000':
        ('ALERT_API_REQUEST_RATE_RPS', '1000'),

    # Database (PostgreSQL)
    r') * 100 > 80\n        for: 5m\n        labels:\n          severity: warning\n          component: postgresql':
        ('ALERT_DB_CONNECTIONS_WARNING_PERCENT', '80'),

    r') * 100 > 90\n        for: 2m\n        labels:\n          severity: critical\n          component: postgresql':
        ('ALERT_DB_CONNECTIONS_CRITICAL_PERCENT', '90'),

    r'rate(pg_stat_database_tup_fetched{datname="lia"}[5m]) > 100000':
        ('ALERT_DB_SLOW_QUERIES_TUPLES_PER_SEC', '100000'),

    # Infrastructure
    r') * 100 > 85\n        for: 5m\n        labels:\n          severity: warning\n          component: storage':
        ('ALERT_DISK_USAGE_WARNING_PERCENT', '85'),

    r') * 100 > 95\n        for: 2m\n        labels:\n          severity: critical\n          component: storage':
        ('ALERT_DISK_USAGE_CRITICAL_PERCENT', '95'),

    r'irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80':
        ('ALERT_CPU_USAGE_WARNING_PERCENT', '80'),

    r') * 100 > 85\n        for: 5m\n        labels:\n          severity: warning\n          component: memory':
        ('ALERT_MEMORY_USAGE_WARNING_PERCENT', '85'),

    r'time() - container_last_seen{name=~"lia.*"} > 60':
        ('ALERT_CONTAINER_DOWN_SECONDS', '60'),

    r'rate(container_start_time_seconds{name=~"lia.*"}[15m]) > 0.1':
        ('ALERT_CONTAINER_RESTART_RATE', '0.1'),

    # Redis
    r'(redis_memory_used_bytes / redis_memory_max_bytes) * 100 > 80':
        ('ALERT_REDIS_MEMORY_WARNING_PERCENT', '80'),

    r'redis_connected_clients > 100':
        ('ALERT_REDIS_CONNECTIONS_WARNING', '100'),

    # Agents
    r') * 1000 > 1000\n        for: 5m\n        labels:\n          severity: warning\n          component: agents\n          sla: ttft':
        ('ALERT_AGENTS_TTFT_P95_MS', '1000'),

    r') < 20\n        for: 5m\n        labels:\n          severity: warning\n          component: agents\n          sla: throughput':
        ('ALERT_AGENTS_TOKENS_PER_SECOND_MIN', '20'),

    r') * 1000 > 500\n        for: 5m\n        labels:\n          severity: critical\n          component: agents\n          sla: router':
        ('ALERT_AGENTS_ROUTER_LATENCY_P95_MS', '500'),

    r') * 100 > 5\n        for: 3m\n        labels:\n          severity: critical\n          component: agents\n          sla: reliability':
        ('ALERT_AGENTS_STREAMING_ERROR_RATE_PERCENT', '5'),

    r') * 100 > 10\n        for: 10m\n        labels:\n          severity: warning\n          component: agents\n          sla: quality':
        ('ALERT_AGENTS_ROUTER_LOW_CONFIDENCE_PERCENT', '10'),

    # Conversations
    r') > 2.0\n        for: 5m\n        labels:\n          severity: critical\n          component: conversations\n          type: performance':
        ('ALERT_CHECKPOINT_SAVE_P99_CRITICAL_SECONDS', '2.0'),

    r') > 1.0\n        for: 10m\n        labels:\n          severity: warning\n          component: conversations\n          type: performance':
        ('ALERT_CHECKPOINT_SAVE_P99_WARNING_SECONDS', '1.0'),

    r'sum(rate(conversation_resets_total[5m])) > 0.5':
        ('ALERT_CONVERSATION_RESET_RATE', '0.5'),

    r') > 50000\n        for: 30m\n        labels:\n          severity: info\n          component: conversations\n          type: capacity':
        ('ALERT_CHECKPOINT_SIZE_P95_BYTES', '50000'),

    r'rate(conversation_created_total[10m]) == 0 and conversation_active_users_total > 10':
        ('ALERT_CONVERSATION_CREATION_MIN_USERS', '10'),

    # LLM & Cost
    r'sum(rate(llm_api_calls_total[5m])) > 0.05':
        ('ALERT_LLM_API_FAILURE_RATE_PERCENT', '0.05'),

    r'sum(rate(llm_api_calls_total[5m])) < 0.95':
        ('ALERT_LLM_API_SUCCESS_RATE_PERCENT', '0.95'),

    r'llm_cost_last_24h > 100':
        ('ALERT_LLM_DAILY_BUDGET_EUR', '100'),

    r'sum(increase(llm_cost_lifetime[1h])) > 5':
        ('ALERT_LLM_HOURLY_BUDGET_EUR', '5'),

    r') > 10\n        for: 10m\n        labels:\n          severity: warning\n          component: llm\n          type: performance':
        ('ALERT_LLM_API_LATENCY_P99_SECONDS', '10'),

    r'llm_cost_by_model_last_24h > 50':
        ('ALERT_LLM_MODEL_DAILY_BUDGET_EUR', '50'),

    # Tokens
    r'sum(rate(llm_tokens_consumed_total[5m])) > 1000':
        ('ALERT_LLM_TOKEN_CONSUMPTION_RATE', '1000'),

    r') > 5\n        for: 30m\n        labels:\n          severity: warning\n          component: tokens\n          type: efficiency':
        ('ALERT_LLM_OUTPUT_INPUT_TOKEN_RATIO', '5'),

    # OAuth
    r') * 100 > 10\n        for: 5m\n        labels:\n          severity: warning\n          component: auth\n          security: true':
        ('ALERT_OAUTH_FAILURE_RATE_PERCENT', '10'),

    r'rate(oauth_pkce_validation_total{result="failed"}[5m]) > 0.1':
        ('ALERT_OAUTH_PKCE_FAILURE_RATE', '0.1'),

    r'rate(oauth_state_validation_total{result="failed"}[5m]) > 0.1':
        ('ALERT_OAUTH_STATE_FAILURE_RATE', '0.1'),

    r') > 5\n        for: 5m\n        labels:\n          severity: warning\n          component: auth\n        annotations:\n          summary: "Callbacks OAuth lents':
        ('ALERT_OAUTH_CALLBACK_LATENCY_P95_SECONDS', '5'),

    r'rate(oauth_provider_errors_total[5m]) > 0.5':
        ('ALERT_OAUTH_PROVIDER_ERROR_RATE', '0.5'),

    r'rate(oauth_callback_total[1m]) > 10':
        ('ALERT_OAUTH_CALLBACK_SPIKE_RATE', '10'),
}


def load_env_file(env_name: str = None, env_file: str = None) -> Dict[str, str]:
    """
    Load environment variables from .env.alerting.{environment} file.

    Args:
        env_name: Environment name (production, staging, development)
        env_file: Custom path to .env file

    Returns:
        Dictionary of environment variables
    """
    if env_file:
        env_path = Path(env_file)
    elif env_name:
        # Look for .env.alerting.{environment} in standard locations
        script_dir = Path(__file__).parent
        api_dir = script_dir.parent.parent.parent / "apps" / "api"

        env_path = api_dir / f".env.alerting.{env_name}"

        if not env_path.exists():
            # Try current directory
            env_path = Path(f".env.alerting.{env_name}")
    else:
        # Default to .env.alerting.example
        script_dir = Path(__file__).parent
        api_dir = script_dir.parent.parent.parent / "apps" / "api"
        env_path = api_dir / ".env.alerting.example"

    if not env_path.exists():
        print(f"ERROR: Environment file not found: {env_path}")
        print(f"Available files in {env_path.parent}:")
        for f in env_path.parent.glob(".env.alerting*"):
            print(f"  - {f.name}")
        sys.exit(1)

    print(f"Loading environment from: {env_path}")
    return dotenv_values(env_path)


def render_template(template_path: Path, env_vars: Dict[str, str], output_path: Path = None):
    """
    Render alerts.yml.template with environment variables.

    Args:
        template_path: Path to alerts.yml.template
        env_vars: Dictionary of environment variables
        output_path: Output path (default: alerts.yml in same directory)
    """
    if not template_path.exists():
        print(f"ERROR: Template file not found: {template_path}")
        sys.exit(1)

    # Set up Jinja2 environment with custom delimiters
    # Use <<< >>> instead of {{ }} to avoid conflict with Prometheus templates
    template_dir = template_path.parent
    env = Environment(
        loader=FileSystemLoader(template_dir),
        undefined=StrictUndefined,  # Fail on undefined variables
        trim_blocks=True,
        lstrip_blocks=True,
        variable_start_string='<<<',
        variable_end_string='>>>'
    )

    # Load template
    template = env.get_template(template_path.name)

    # Render with environment variables
    try:
        rendered = template.render(**env_vars)
    except Exception as e:
        print(f"ERROR: Failed to render template: {e}")
        print("\nMissing variables:")
        # Extract missing variable names from error message
        if "is undefined" in str(e):
            var_name = str(e).split("'")[1]
            print(f"  - {var_name}")
        sys.exit(1)

    # Validate YAML syntax
    try:
        yaml.safe_load(rendered)
        print("[OK] Generated YAML is valid")
    except yaml.YAMLError as e:
        print(f"ERROR: Generated YAML is invalid: {e}")
        sys.exit(1)

    # Write output
    if output_path is None:
        output_path = template_dir / "alerts.yml"

    output_path.write_text(rendered, encoding='utf-8')
    print(f"[SUCCESS] Rendered alerts written to: {output_path}")

    # Print statistics
    lines = rendered.count('\n')
    alerts = rendered.count('alert:')
    print(f"\nStatistics:")
    print(f"  Lines: {lines}")
    print(f"  Alerts: {alerts}")


def main():
    parser = argparse.ArgumentParser(
        description='Render alerts.yml from template with environment-specific thresholds'
    )
    parser.add_argument(
        '--env',
        choices=['production', 'staging', 'development'],
        help='Environment name (production, staging, development)'
    )
    parser.add_argument(
        '--env-file',
        help='Custom path to .env file'
    )
    parser.add_argument(
        '--template',
        help='Path to template file (default: alerts.yml.template)',
        default=None
    )
    parser.add_argument(
        '--output',
        help='Output file path (default: alerts.yml)',
        default=None
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate template without writing output'
    )

    args = parser.parse_args()

    if not args.env and not args.env_file:
        print("ERROR: Must specify either --env or --env-file")
        parser.print_help()
        sys.exit(1)

    # Determine paths
    script_dir = Path(__file__).parent

    if args.template:
        template_path = Path(args.template)
    else:
        template_path = script_dir / "alerts.yml.template"

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = script_dir / "alerts.yml" if not args.dry_run else None

    # Load environment variables
    env_vars = load_env_file(args.env, args.env_file)

    print(f"Loaded {len(env_vars)} environment variables")
    print("\nAlert thresholds:")
    for key, value in sorted(env_vars.items()):
        if key.startswith('ALERT_'):
            print(f"  {key} = {value}")

    # Render template
    if args.dry_run:
        print("\n[DRY-RUN] Validating template only")
        render_template(template_path, env_vars, output_path=None)
    else:
        render_template(template_path, env_vars, output_path)


if __name__ == "__main__":
    main()
