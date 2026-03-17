#!/usr/bin/env python3
"""
Extract ALL hardcoded thresholds from all Prometheus alert files.

This script:
1. Scans all alert YAML files (alerts.yml, alert_rules.yml, alerts/*.yml)
2. Extracts every numeric threshold using regex patterns
3. Generates environment variable names following naming convention
4. Creates complete .env.alerting.{environment} files
5. Outputs JSON mapping for template generation

Usage:
    python extract_all_thresholds.py --output thresholds.json
    python extract_all_thresholds.py --generate-env production
    python extract_all_thresholds.py --generate-env staging
    python extract_all_thresholds.py --generate-env development

Output:
    - thresholds.json: Complete threshold mapping
    - .env.alerting.{environment}: Environment-specific thresholds
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass

try:
    import yaml
except ImportError:
    print("ERROR: Missing required package: pyyaml")
    print("Install with: pip install pyyaml")
    sys.exit(1)


@dataclass
class Threshold:
    """Represents a single threshold extracted from an alert."""
    alert_name: str
    component: str
    severity: str
    threshold_value: float
    operator: str  # '>', '<', '>=', '<=', '=='
    unit: str  # 'percent', 'seconds', 'rate', 'bytes', etc.
    expression: str  # Original PromQL expression
    env_var_name: str
    file_source: str  # Which file this came from
    description: str  # Human-readable description


class ThresholdExtractor:
    """Extract thresholds from Prometheus alert YAML files."""

    # Regex patterns for extracting thresholds
    THRESHOLD_PATTERNS = [
        # Pattern 1: Standard comparison (> 5, < 10, etc.)
        r'(?P<operator>[><=!]+)\s*(?P<value>\d+\.?\d*)',

        # Pattern 2: Percentage comparison (* 100 > 50)
        r'\*\s*100\s*(?P<operator>[><=!]+)\s*(?P<value>\d+\.?\d*)',

        # Pattern 3: Inverse comparison for percentages
        r'(?P<operator>[><=!]+)\s*(?P<value>\d+\.?\d*)\s*#.*percent',
    ]

    # Unit detection patterns
    UNIT_PATTERNS = {
        'percent': [r'\*\s*100', r'percentage', r'percent', r'%'],
        'seconds': [r'_seconds\{', r'_seconds_bucket', r'_duration', r'_latency'],
        'bytes': [r'_bytes\{', r'_size_bytes'],
        'rate': [r'rate\(', r'irate\(', r'/s', r'per_second'],
        'milliseconds': [r'_ms\{', r'\*\s*1000'],
        'count': [r'_total\{', r'_count\{'],
    }

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.thresholds: List[Threshold] = []

    def log(self, message: str):
        """Print message if verbose mode enabled."""
        if self.verbose:
            print(f"[DEBUG] {message}")

    def detect_unit(self, expression: str) -> str:
        """Detect the unit of measurement from the PromQL expression."""
        expr_lower = expression.lower()

        for unit, patterns in self.UNIT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, expression, re.IGNORECASE):
                    return unit

        return 'unknown'

    def generate_env_var_name(self, alert_name: str, component: str, severity: str, unit: str) -> str:
        """
        Generate environment variable name following naming convention.

        Convention: ALERT_{COMPONENT}_{ALERT_NAME}_{SEVERITY}_{UNIT}

        Examples:
            - ALERT_API_ERROR_RATE_CRITICAL_PERCENT
            - ALERT_REDIS_MEMORY_WARNING_PERCENT
            - ALERT_LANGGRAPH_SUCCESS_RATE_CRITICAL_PERCENT
        """
        # Convert alert name from CamelCase to SNAKE_CASE
        snake_name = re.sub(r'(?<!^)(?=[A-Z])', '_', alert_name).upper()

        # Remove common suffixes
        snake_name = snake_name.replace('_ALERT', '').replace('_WARNING', '').replace('_CRITICAL', '')

        # Build env var name
        parts = ['ALERT', component.upper(), snake_name, severity.upper()]

        if unit and unit != 'unknown':
            parts.append(unit.upper())

        return '_'.join(parts)

    def extract_thresholds_from_alert(self, alert: Dict, file_source: str) -> List[Threshold]:
        """Extract all thresholds from a single alert rule."""
        thresholds = []

        alert_name = alert.get('alert', 'UnknownAlert')
        expression = alert.get('expr', '')
        labels = alert.get('labels', {})
        annotations = alert.get('annotations', {})

        component = labels.get('component', 'unknown')
        severity = labels.get('severity', 'warning')
        description = annotations.get('summary', annotations.get('description', ''))

        self.log(f"Processing alert: {alert_name} (component={component}, severity={severity})")

        # Try each threshold pattern
        for pattern in self.THRESHOLD_PATTERNS:
            matches = re.finditer(pattern, expression)

            for match in matches:
                try:
                    operator = match.group('operator')
                    value = float(match.group('value'))

                    # Detect unit
                    unit = self.detect_unit(expression)

                    # Generate env var name
                    env_var_name = self.generate_env_var_name(alert_name, component, severity, unit)

                    threshold = Threshold(
                        alert_name=alert_name,
                        component=component,
                        severity=severity,
                        threshold_value=value,
                        operator=operator,
                        unit=unit,
                        expression=expression.strip(),
                        env_var_name=env_var_name,
                        file_source=file_source,
                        description=description
                    )

                    thresholds.append(threshold)
                    self.log(f"  Found threshold: {env_var_name} = {value} ({operator}, {unit})")

                except Exception as e:
                    self.log(f"  Error extracting threshold: {e}")

        return thresholds

    def extract_from_file(self, file_path: Path) -> List[Threshold]:
        """Extract all thresholds from a YAML file."""
        if not file_path.exists():
            print(f"WARNING: File not found: {file_path}")
            return []

        self.log(f"\nProcessing file: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except Exception as e:
            print(f"ERROR: Failed to parse YAML file {file_path}: {e}")
            return []

        if not data or 'groups' not in data:
            print(f"WARNING: No alert groups found in {file_path}")
            return []

        file_thresholds = []

        for group in data['groups']:
            group_name = group.get('name', 'unknown')
            rules = group.get('rules', [])

            self.log(f"  Group: {group_name} ({len(rules)} rules)")

            for rule in rules:
                if 'alert' in rule:  # This is an alerting rule (not a recording rule)
                    thresholds = self.extract_thresholds_from_alert(rule, file_path.name)
                    file_thresholds.extend(thresholds)

        return file_thresholds

    def extract_all(self, alert_dir: Path) -> List[Threshold]:
        """Extract thresholds from all alert files in directory."""
        all_thresholds = []

        # Main alert files
        main_files = [
            alert_dir / 'alerts.yml',
            alert_dir / 'alert_rules.yml',
        ]

        # Subdirectory alerts
        alerts_subdir = alert_dir / 'alerts'
        if alerts_subdir.exists():
            main_files.extend(alerts_subdir.glob('*.yml'))

        for file_path in main_files:
            thresholds = self.extract_from_file(file_path)
            all_thresholds.extend(thresholds)

        self.thresholds = all_thresholds
        return all_thresholds

    def generate_env_file(self, environment: str, output_path: Path, adjust_factors: Dict[str, float] = None):
        """
        Generate .env.alerting.{environment} file with environment-specific thresholds.

        Args:
            environment: 'production', 'staging', or 'development'
            output_path: Path to write .env file
            adjust_factors: Optional dict of adjustment factors by environment
        """
        if adjust_factors is None:
            # Default adjustment factors
            adjust_factors = {
                'production': 1.0,  # Strict thresholds
                'staging': 1.2,     # 20% more lenient
                'development': 1.5  # 50% more lenient
            }

        factor = adjust_factors.get(environment, 1.0)

        # Group thresholds by component
        thresholds_by_component = {}
        for threshold in self.thresholds:
            component = threshold.component
            if component not in thresholds_by_component:
                thresholds_by_component[component] = []
            thresholds_by_component[component].append(threshold)

        # Generate .env content
        lines = [
            f"# Prometheus Alert Thresholds - {environment.upper()}",
            f"# Generated automatically from alert YAML files",
            f"# Adjustment factor: {factor}x (relative to production)",
            "",
            f"# Total thresholds: {len(self.thresholds)}",
            "",
        ]

        for component in sorted(thresholds_by_component.keys()):
            lines.append(f"# ===== {component.upper()} ALERTS =====")
            lines.append("")

            thresholds = thresholds_by_component[component]

            for threshold in sorted(thresholds, key=lambda t: t.alert_name):
                # Adjust threshold based on environment
                adjusted_value = threshold.threshold_value

                # For "greater than" comparisons, increase threshold in dev/staging
                # For "less than" comparisons, decrease threshold in dev/staging
                if threshold.operator in ['>', '>=']:
                    adjusted_value = threshold.threshold_value * factor
                elif threshold.operator in ['<', '<=']:
                    adjusted_value = threshold.threshold_value / factor

                # Format value
                if threshold.unit == 'percent':
                    value_str = f"{adjusted_value:.1f}"
                elif threshold.unit in ['seconds', 'milliseconds']:
                    value_str = f"{adjusted_value:.2f}"
                else:
                    value_str = f"{adjusted_value:.0f}" if adjusted_value >= 1 else f"{adjusted_value:.2f}"

                # Add comment with description
                if threshold.description:
                    desc_clean = threshold.description.replace('\n', ' ').replace('{{', '').replace('}}', '')[:80]
                    lines.append(f"# {threshold.alert_name}: {desc_clean}")

                lines.append(f"{threshold.env_var_name}={value_str}")
                lines.append("")

        # Write file
        output_path.write_text('\n'.join(lines), encoding='utf-8')
        print(f"[SUCCESS] Generated {output_path}")
        print(f"  Environment: {environment}")
        print(f"  Thresholds: {len(self.thresholds)}")
        print(f"  Adjustment factor: {factor}x")

    def export_json(self, output_path: Path):
        """Export thresholds as JSON for template generation."""
        data = {
            'total_thresholds': len(self.thresholds),
            'thresholds': [
                {
                    'alert_name': t.alert_name,
                    'component': t.component,
                    'severity': t.severity,
                    'threshold_value': t.threshold_value,
                    'operator': t.operator,
                    'unit': t.unit,
                    'env_var_name': t.env_var_name,
                    'file_source': t.file_source,
                    'description': t.description,
                }
                for t in self.thresholds
            ]
        }

        output_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
        print(f"[SUCCESS] Exported JSON to {output_path}")

    def print_summary(self):
        """Print extraction summary."""
        print("\n" + "="*80)
        print("THRESHOLD EXTRACTION SUMMARY")
        print("="*80)
        print(f"\nTotal thresholds extracted: {len(self.thresholds)}")

        # Group by component
        by_component = {}
        for t in self.thresholds:
            by_component[t.component] = by_component.get(t.component, 0) + 1

        print(f"\nThresholds by component:")
        for component in sorted(by_component.keys()):
            print(f"  {component:20s}: {by_component[component]:3d} thresholds")

        # Group by severity
        by_severity = {}
        for t in self.thresholds:
            by_severity[t.severity] = by_severity.get(t.severity, 0) + 1

        print(f"\nThresholds by severity:")
        for severity in sorted(by_severity.keys()):
            print(f"  {severity:20s}: {by_severity[severity]:3d} thresholds")

        # Group by file
        by_file = {}
        for t in self.thresholds:
            by_file[t.file_source] = by_file.get(t.file_source, 0) + 1

        print(f"\nThresholds by file:")
        for file_name in sorted(by_file.keys()):
            print(f"  {file_name:40s}: {by_file[file_name]:3d} thresholds")

        print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Extract hardcoded thresholds from Prometheus alert files'
    )
    parser.add_argument(
        '--alert-dir',
        type=Path,
        default=Path(__file__).parent,
        help='Directory containing alert YAML files'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output JSON file path'
    )
    parser.add_argument(
        '--generate-env',
        choices=['production', 'staging', 'development'],
        help='Generate .env.alerting.{environment} file'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Initialize extractor
    extractor = ThresholdExtractor(verbose=args.verbose)

    # Extract thresholds
    print(f"Scanning directory: {args.alert_dir}")
    thresholds = extractor.extract_all(args.alert_dir)

    if not thresholds:
        print("ERROR: No thresholds extracted!")
        sys.exit(1)

    # Print summary
    extractor.print_summary()

    # Export JSON if requested
    if args.output:
        extractor.export_json(args.output)

    # Generate env file if requested
    if args.generate_env:
        # Determine output path
        api_dir = args.alert_dir.parent.parent.parent / "apps" / "api"
        env_file = api_dir / f".env.alerting.{args.generate_env}"

        extractor.generate_env_file(args.generate_env, env_file)

    return 0


if __name__ == "__main__":
    sys.exit(main())
