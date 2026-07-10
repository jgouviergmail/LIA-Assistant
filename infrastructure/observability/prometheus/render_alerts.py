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
import sys
from pathlib import Path
from typing import Dict

try:
    import yaml
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    from dotenv import dotenv_values
except ImportError as e:
    print(f"ERROR: Missing required package: {e}")
    print("Install with: pip install jinja2 pyyaml python-dotenv")
    sys.exit(1)


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
