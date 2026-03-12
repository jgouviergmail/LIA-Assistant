#!/usr/bin/env python3
"""
Convert Prometheus alert YAML files to Jinja2 templates.

This script:
1. Loads threshold mapping from thresholds_complete.json
2. Replaces hardcoded values with Jinja2 variables <<<VAR>>>
3. Generates .template files for all alert YAMLs
4. Preserves YAML formatting and comments

Usage:
    python convert_to_template.py --input alerts.yml --output alerts.yml.template
    python convert_to_template.py --all  # Convert all files

Requirements:
    pip install pyyaml
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

try:
    import yaml
except ImportError:
    print("ERROR: Missing required package: pyyaml")
    print("Install with: pip install pyyaml")
    sys.exit(1)


class AlertTemplateConverter:
    """Convert alert YAML files to Jinja2 templates."""

    def __init__(self, thresholds_json: Path, verbose: bool = False):
        self.verbose = verbose
        self.thresholds_data = self.load_thresholds(thresholds_json)

        # Build replacement mapping: {(file, alert_name, value): env_var_name}
        self.replacements = self.build_replacement_map()

    def log(self, message: str):
        """Print message if verbose mode enabled."""
        if self.verbose:
            print(f"[DEBUG] {message}")

    def load_thresholds(self, json_path: Path) -> Dict:
        """Load thresholds from JSON."""
        if not json_path.exists():
            print(f"ERROR: Threshold JSON not found: {json_path}")
            sys.exit(1)

        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def build_replacement_map(self) -> Dict:
        """
        Build mapping for value replacement.

        Returns:
            Dict[(file_source, alert_name, value, operator): env_var_name]
        """
        replacements = {}

        for threshold in self.thresholds_data['thresholds']:
            key = (
                threshold['file_source'],
                threshold['alert_name'],
                threshold['threshold_value'],
                threshold['operator']
            )

            replacements[key] = threshold['env_var_name']

        self.log(f"Built replacement map with {len(replacements)} entries")
        return replacements

    def convert_file(self, input_path: Path, output_path: Path):
        """
        Convert alert YAML to Jinja2 template.

        Strategy:
        1. Read file as text (preserve formatting)
        2. Use YAML parser to find alert contexts
        3. Replace hardcoded values with <<<VAR>>> in text
        4. Write template file
        """
        if not input_path.exists():
            print(f"ERROR: Input file not found: {input_path}")
            return False

        self.log(f"\nConverting {input_path.name} -> {output_path.name}")

        # Read original content
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse YAML to get alert structure
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            print(f"ERROR: Failed to parse YAML: {e}")
            return False

        if not data or 'groups' not in data:
            print(f"WARNING: No alert groups found in {input_path.name}")
            return False

        # Extract alerts and their thresholds
        alerts_info = {}  # {alert_name: [(value, operator, env_var)]}

        for group in data['groups']:
            for rule in group.get('rules', []):
                if 'alert' in rule:
                    alert_name = rule['alert']
                    expr = rule.get('expr', '')

                    # Find matching thresholds for this alert
                    matches = []
                    for (file_src, alt_name, value, operator), env_var in self.replacements.items():
                        if file_src == input_path.name and alt_name == alert_name:
                            matches.append((value, operator, env_var))

                    if matches:
                        alerts_info[alert_name] = matches
                        self.log(f"  Alert '{alert_name}': {len(matches)} threshold(s)")

        # Perform replacements in text
        template_content = content
        replacements_made = 0

        for alert_name, thresholds in alerts_info.items():
            for value, operator, env_var in thresholds:
                # Build regex patterns for replacement
                # Pattern 1: Standard comparison (> 5.0, < 10, etc.)
                value_str = str(value)
                if '.' in value_str:
                    # Float: try both with/without trailing zeros
                    patterns = [
                        rf'{re.escape(operator)}\s*{re.escape(value_str)}',
                        rf'{re.escape(operator)}\s*{re.escape(str(int(value) if value.is_integer() else value))}'
                    ]
                else:
                    patterns = [rf'{re.escape(operator)}\s*{value_str}']

                # Try each pattern
                for pattern in patterns:
                    replacement = f'{operator} <<<{env_var}>>>'

                    # Count matches before replacement
                    matches_count = len(re.findall(pattern, template_content))

                    if matches_count > 0:
                        template_content = re.sub(pattern, replacement, template_content)
                        replacements_made += matches_count
                        self.log(f"    Replaced '{operator} {value}' -> '<<<{env_var}>>>' ({matches_count} occurrences)")
                        break  # Stop after first successful pattern

        # Write template file
        with open(output_path, 'w', encoding='utf-8') as f:
            # Add template header
            header = f"""# Alerting rules for LIA (TEMPLATE)
#
# This file is a Jinja2 template. Thresholds are externalized in .env.alerting.{{environment}}
#
# To generate {input_path.name}:
#   python render_alerts.py --env production --template {output_path.name} --output {input_path.name}
#   python render_alerts.py --env staging --template {output_path.name} --output {input_path.name}
#   python render_alerts.py --env development --template {output_path.name} --output {input_path.name}
#
# Available variables: {len(self.replacements)} thresholds (see .env.alerting.example)
#
"""
            f.write(header)
            f.write(template_content)

        print(f"[SUCCESS] Created {output_path}")
        print(f"  Replacements made: {replacements_made}")
        print(f"  Alerts templated: {len(alerts_info)}")

        return True

    def convert_all(self, alert_dir: Path):
        """Convert all alert files in directory."""
        files_to_convert = [
            ('alerts.yml', 'alerts.yml.template'),
            ('alert_rules.yml', 'alert_rules.yml.template'),
            ('alerts/langgraph_framework_alerts.yml', 'alerts/langgraph_framework_alerts.yml.template'),
        ]

        success_count = 0

        for input_name, output_name in files_to_convert:
            input_path = alert_dir / input_name
            output_path = alert_dir / output_name

            if input_path.exists():
                if self.convert_file(input_path, output_path):
                    success_count += 1
            else:
                print(f"WARNING: File not found, skipping: {input_path}")

        print(f"\n[SUMMARY] Successfully converted {success_count}/{len(files_to_convert)} files")


def main():
    parser = argparse.ArgumentParser(
        description='Convert Prometheus alert YAML files to Jinja2 templates'
    )
    parser.add_argument(
        '--alert-dir',
        type=Path,
        default=Path(__file__).parent,
        help='Directory containing alert YAML files'
    )
    parser.add_argument(
        '--thresholds-json',
        type=Path,
        help='Path to thresholds_complete.json (default: same dir as script)'
    )
    parser.add_argument(
        '--input',
        type=Path,
        help='Input YAML file to convert'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output template file'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Convert all alert files (alerts.yml, alert_rules.yml, langgraph)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Determine thresholds JSON path
    if args.thresholds_json:
        thresholds_json = args.thresholds_json
    else:
        thresholds_json = args.alert_dir / 'thresholds_complete.json'

    # Initialize converter
    converter = AlertTemplateConverter(thresholds_json, verbose=args.verbose)

    # Convert files
    if args.all:
        converter.convert_all(args.alert_dir)
    elif args.input and args.output:
        converter.convert_file(args.input, args.output)
    else:
        print("ERROR: Must specify either --all or both --input and --output")
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
