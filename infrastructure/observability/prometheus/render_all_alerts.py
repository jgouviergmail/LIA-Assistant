#!/usr/bin/env python3
"""
Render ALL alert templates for a given environment.

This script:
1. Loads environment-specific thresholds from .env.alerting.{environment}
2. Renders ALL alert templates (alerts.yml, alert_rules.yml, langgraph_framework_alerts.yml)
3. Validates generated YAML syntax
4. Writes output files

Usage:
    # Production
    python render_all_alerts.py --env production

    # Staging
    python render_all_alerts.py --env staging

    # Development
    python render_all_alerts.py --env development

Output:
    - alerts.yml (from alerts.yml.template)
    - alert_rules.yml (from alert_rules.yml.template)
    - alerts/langgraph_framework_alerts.yml (from langgraph_framework_alerts.yml.template)

Requirements:
    pip install jinja2 pyyaml python-dotenv
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, Tuple

try:
    import yaml
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    from dotenv import dotenv_values
except ImportError as e:
    print(f"ERROR: Missing required package: {e}")
    print("Install with: pip install jinja2 pyyaml python-dotenv")
    sys.exit(1)


# Template -> Output mapping
ALERT_FILES = [
    ('alerts.yml.template', 'alerts.yml'),
    ('alert_rules.yml.template', 'alert_rules.yml'),
    ('alerts/langgraph_framework_alerts.yml.template', 'alerts/langgraph_framework_alerts.yml'),
]


def load_env_file(env_name: str, api_dir: Path) -> Dict[str, str]:
    """
    Load environment variables from .env.alerting.{environment} file.

    Args:
        env_name: Environment name (production, staging, development)
        api_dir: Path to apps/api directory

    Returns:
        Dictionary of environment variables
    """
    env_path = api_dir / f".env.alerting.{env_name}"

    if not env_path.exists():
        print(f"ERROR: Environment file not found: {env_path}")
        print(f"\nAvailable files in {env_path.parent}:")
        for f in env_path.parent.glob(".env.alerting*"):
            print(f"  - {f.name}")
        sys.exit(1)

    print(f"Loading environment from: {env_path}")
    env_vars = dotenv_values(env_path)

    # Filter to only ALERT_* variables
    alert_vars = {k: v for k, v in env_vars.items() if k.startswith('ALERT_')}

    print(f"Loaded {len(alert_vars)} alert threshold variables")
    return alert_vars


def render_template(
    template_path: Path,
    env_vars: Dict[str, str],
    output_path: Path,
    dry_run: bool = False
) -> bool:
    """
    Render alert template with environment variables.

    Args:
        template_path: Path to .template file
        env_vars: Dictionary of environment variables
        output_path: Output file path
        dry_run: If True, validate only (don't write)

    Returns:
        True if successful, False otherwise
    """
    if not template_path.exists():
        print(f"ERROR: Template file not found: {template_path}")
        return False

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
    try:
        template = env.get_template(template_path.name)
    except Exception as e:
        print(f"ERROR: Failed to load template {template_path.name}: {e}")
        return False

    # Render with environment variables
    try:
        rendered = template.render(**env_vars)
    except Exception as e:
        print(f"ERROR: Failed to render template {template_path.name}: {e}")

        # Extract missing variable names
        if "is undefined" in str(e):
            var_name = str(e).split("'")[1]
            print(f"\nMissing variable: {var_name}")
            print("\nHint: Check .env.alerting.{environment} file for this variable")

        return False

    # Validate YAML syntax
    try:
        yaml.safe_load(rendered)
        print(f"  [OK] Valid YAML: {output_path.name}")
    except yaml.YAMLError as e:
        print(f"  [ERROR] Invalid YAML in {output_path.name}: {e}")
        return False

    # Write output (if not dry run)
    if not dry_run:
        # Create output directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(rendered, encoding='utf-8')
        print(f"  [SUCCESS] Generated: {output_path}")

        # Print statistics
        lines = rendered.count('\n')
        alerts = rendered.count('alert:')
        print(f"    Lines: {lines}, Alerts: {alerts}")

    return True


def render_all_files(
    env_name: str,
    alert_dir: Path,
    api_dir: Path,
    dry_run: bool = False
) -> Tuple[int, int]:
    """
    Render all alert template files for environment.

    Args:
        env_name: Environment name
        alert_dir: Directory containing alert templates
        api_dir: Path to apps/api directory
        dry_run: If True, validate only (don't write)

    Returns:
        Tuple of (success_count, total_count)
    """
    # Load environment variables
    env_vars = load_env_file(env_name, api_dir)

    print(f"\nRendering {len(ALERT_FILES)} alert files for environment: {env_name}")
    print("="*80)

    success_count = 0

    for template_name, output_name in ALERT_FILES:
        template_path = alert_dir / template_name
        output_path = alert_dir / output_name

        print(f"\n[{success_count + 1}/{len(ALERT_FILES)}] {template_name} -> {output_name}")

        if render_template(template_path, env_vars, output_path, dry_run):
            success_count += 1
        else:
            print(f"  [FAILED] Could not render {template_name}")

    return success_count, len(ALERT_FILES)


def main():
    parser = argparse.ArgumentParser(
        description='Render all alert templates for a given environment'
    )
    parser.add_argument(
        '--env',
        required=True,
        choices=['production', 'staging', 'development'],
        help='Environment name (production, staging, development)'
    )
    parser.add_argument(
        '--alert-dir',
        type=Path,
        default=Path(__file__).parent,
        help='Directory containing alert templates (default: script directory)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate templates without writing output files'
    )

    args = parser.parse_args()

    # Determine API directory (contains .env.alerting.* files)
    alert_dir = args.alert_dir
    api_dir = alert_dir.parent.parent.parent / "apps" / "api"

    if not api_dir.exists():
        print(f"ERROR: API directory not found: {api_dir}")
        sys.exit(1)

    # Render all files
    success_count, total_count = render_all_files(
        args.env,
        alert_dir,
        api_dir,
        args.dry_run
    )

    # Print summary
    print("\n" + "="*80)
    if args.dry_run:
        print(f"[DRY-RUN] Validation complete: {success_count}/{total_count} templates valid")
    else:
        print(f"[SUMMARY] Successfully rendered: {success_count}/{total_count} files")

    if success_count < total_count:
        print(f"[WARNING] {total_count - success_count} file(s) failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
