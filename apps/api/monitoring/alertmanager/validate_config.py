#!/usr/bin/env python3
"""
Validate AlertManager Configuration Template

This script validates the alertmanager.yml.template file by:
1. Substituting dummy environment variables
2. Parsing the resulting YAML
3. Checking for common configuration errors

Usage:
    python validate_config.py
"""

import re
import sys
from pathlib import Path

import yaml

# Dummy environment variables for validation
DUMMY_ENV_VARS = {
    "ALERTMANAGER_SMTP_SMARTHOST": "smtp.example.com:587",
    "ALERTMANAGER_SMTP_FROM": "alertmanager@example.com",
    "ALERTMANAGER_SMTP_AUTH_USERNAME": "test@example.com",
    "ALERTMANAGER_SMTP_AUTH_PASSWORD": "test-password",
    "ALERTMANAGER_BACKEND_TEAM_EMAIL": "backend@example.com",
    "ALERTMANAGER_FINANCE_TEAM_EMAIL": "finance@example.com",
    "ALERTMANAGER_SECURITY_TEAM_EMAIL": "security@example.com",
    "ALERTMANAGER_ML_TEAM_EMAIL": "ml@example.com",
    "ALERTMANAGER_SLACK_WEBHOOK_CRITICAL": "https://hooks.slack.com/services/T00/B00/xxx",
    "ALERTMANAGER_SLACK_WEBHOOK_WARNING": "https://hooks.slack.com/services/T00/B00/yyy",
    "ALERTMANAGER_SLACK_WEBHOOK_SECURITY": "https://hooks.slack.com/services/T00/B00/zzz",
    "ALERTMANAGER_PAGERDUTY_ROUTING_KEY": "test-routing-key-12345678",
}


def substitute_variables(template_content: str, env_vars: dict) -> str:
    """Substitute ${VAR} placeholders with values from env_vars."""
    result = template_content
    for var_name, var_value in env_vars.items():
        pattern = rf"\$\{{{var_name}\}}"
        result = re.sub(pattern, var_value, result)
    return result


def validate_alertmanager_config(config_path: Path) -> tuple[bool, list[str]]:
    """
    Validate AlertManager configuration template.

    Returns:
        (is_valid, errors) tuple where is_valid is bool and errors is list of error messages
    """
    errors = []

    # Read template
    print(f"[1/4] Reading template: {config_path}")
    try:
        with open(config_path, encoding="utf-8") as f:
            template_content = f.read()
    except Exception as e:
        errors.append(f"Failed to read template: {e}")
        return False, errors

    # Substitute variables
    print("[2/4] Substituting environment variables...")
    try:
        config_content = substitute_variables(template_content, DUMMY_ENV_VARS)
    except Exception as e:
        errors.append(f"Failed to substitute variables: {e}")
        return False, errors

    # Check for unsubstituted variables
    unsubstituted = re.findall(r"\$\{([A-Z_]+)\}", config_content)
    if unsubstituted:
        errors.append(f"Unsubstituted variables found: {', '.join(set(unsubstituted))}")

    # Parse YAML
    print("[3/4] Parsing YAML...")
    try:
        config = yaml.safe_load(config_content)
    except yaml.YAMLError as e:
        errors.append(f"YAML parsing error: {e}")
        return False, errors

    # Validate structure
    print("[4/4] Validating AlertManager structure...")

    # Check required top-level keys
    required_keys = ["global", "route", "receivers"]
    for key in required_keys:
        if key not in config:
            errors.append(f"Missing required top-level key: {key}")

    # Validate global config
    if "global" in config:
        required_global = ["smtp_from", "smtp_smarthost"]
        for key in required_global:
            if key not in config["global"]:
                errors.append(f"Missing required global config: {key}")

    # Validate route
    if "route" in config:
        route = config["route"]

        # Check required route fields
        if "receiver" not in route:
            errors.append("Route missing required 'receiver' field")

        # Check receiver exists
        if "receivers" in config:
            receiver_names = {r["name"] for r in config["receivers"]}
            if route.get("receiver") and route["receiver"] not in receiver_names:
                errors.append(f"Route references undefined receiver: {route['receiver']}")

            # Check all child routes reference valid receivers
            if "routes" in route:
                for i, child_route in enumerate(route["routes"]):
                    child_receiver = child_route.get("receiver")
                    if child_receiver and child_receiver not in receiver_names:
                        errors.append(f"Route[{i}] references undefined receiver: {child_receiver}")

    # Validate receivers
    if "receivers" in config:
        receiver_names_seen = set()
        for receiver in config["receivers"]:
            # Check duplicate names
            name = receiver.get("name")
            if not name:
                errors.append("Receiver missing 'name' field")
                continue

            if name in receiver_names_seen:
                errors.append(f"Duplicate receiver name: {name}")
            receiver_names_seen.add(name)

            # Check receiver has at least one notification config
            notification_types = [
                "email_configs",
                "slack_configs",
                "pagerduty_configs",
                "webhook_configs",
            ]
            has_notification = any(nt in receiver for nt in notification_types)
            if not has_notification:
                errors.append(f"Receiver '{name}' has no notification configurations")

    # Validate inhibit_rules
    if "inhibit_rules" in config:
        for i, rule in enumerate(config["inhibit_rules"]):
            # Check required fields
            if "source_match" not in rule and "source_match_re" not in rule:
                errors.append(f"Inhibit rule[{i}] missing source_match or source_match_re")
            if "target_match" not in rule and "target_match_re" not in rule:
                errors.append(f"Inhibit rule[{i}] missing target_match or target_match_re")

    # Count configuration elements
    print("\n" + "=" * 80)
    print("CONFIGURATION SUMMARY")
    print("=" * 80)
    print(f"Receivers:       {len(config.get('receivers', []))}")
    print(
        f"Routes:          {len(config.get('route', {}).get('routes', [])) + 1}"
    )  # +1 for root route
    print(f"Inhibit Rules:   {len(config.get('inhibit_rules', []))}")
    print(f"Templates:       {len(config.get('templates', []))}")

    # List receivers
    if "receivers" in config:
        print("\nReceivers configured:")
        for receiver in config["receivers"]:
            name = receiver.get("name", "unnamed")
            channels = []
            if "email_configs" in receiver:
                channels.append("Email")
            if "slack_configs" in receiver:
                channels.append("Slack")
            if "pagerduty_configs" in receiver:
                channels.append("PagerDuty")
            print(f"  - {name}: {', '.join(channels) if channels else 'No channels'}")

    is_valid = len(errors) == 0
    return is_valid, errors


def main():
    """Main validation execution."""
    print("=" * 80)
    print("ALERTMANAGER CONFIGURATION VALIDATION")
    print("=" * 80)
    print()

    # Locate template file
    script_dir = Path(__file__).parent
    template_path = script_dir / "alertmanager.yml.template"

    if not template_path.exists():
        print(f"ERROR: Template file not found: {template_path}")
        sys.exit(1)

    # Validate
    is_valid, errors = validate_alertmanager_config(template_path)

    # Report results
    print("\n" + "=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)

    if is_valid:
        print("[OK] VALID - Configuration is correct")
        print()
        print("Next steps:")
        print("  1. Set environment variables in .env file")
        print("  2. Start AlertManager: docker-compose up -d alertmanager")
        print("  3. Verify UI: http://localhost:9094")
        print()
        sys.exit(0)
    else:
        print(f"[ERROR] INVALID - Found {len(errors)} error(s):")
        print()
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
        print()
        print("Please fix errors and run validation again.")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
