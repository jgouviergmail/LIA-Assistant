#!/usr/bin/env python3
"""
Extract all hardcoded thresholds from Prometheus alert files.

This script analyzes alert_rules.yml and alerts.yml to identify all numeric
thresholds that should be externalized to environment-specific configuration files.

Usage:
    python extract_thresholds.py

Output:
    - thresholds_inventory.json: Complete inventory of all thresholds
    - Console output: Summary and categorization

Author: Infrastructure Team
Date: 2025-11-23
"""

import re
import yaml
import json
from pathlib import Path
from typing import Dict, List
from collections import defaultdict

# Threshold patterns to extract
THRESHOLD_PATTERNS = [
    # Direct comparisons: > 100, < 50, >= 0.5
    (r'>\s*([0-9]+\.?[0-9]*)', 'greater_than'),
    (r'<\s*([0-9]+\.?[0-9]*)', 'less_than'),
    (r'>=\s*([0-9]+\.?[0-9]*)', 'greater_equal'),
    (r'<=\s*([0-9]+\.?[0-9]*)', 'less_equal'),
    (r'==\s*([0-9]+\.?[0-9]*)', 'equal'),
]

def extract_thresholds_from_file(filepath: Path) -> List[Dict]:
    """Extract all thresholds from a YAML alert file."""
    thresholds = []

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')

    # Load YAML to get structure
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        print(f"Warning: Could not parse YAML from {filepath}: {e}")
        data = {}

    # Extract thresholds from each alert rule
    if 'groups' in data:
        for group_idx, group in enumerate(data['groups']):
            group_name = group.get('name', f'group_{group_idx}')

            for rule_idx, rule in enumerate(group.get('rules', [])):
                alert_name = rule.get('alert', f'rule_{rule_idx}')
                expr = rule.get('expr', '')

                # Convert multi-line expr to single line for pattern matching
                expr_single = ' '.join(str(expr).split())

                # Extract all thresholds from expression
                for pattern, operator in THRESHOLD_PATTERNS:
                    matches = re.finditer(pattern, expr_single)
                    for match in matches:
                        threshold_value = float(match.group(1))

                        # Get context (surrounding text)
                        start = max(0, match.start() - 50)
                        end = min(len(expr_single), match.end() + 50)
                        context = expr_single[start:end]

                        thresholds.append({
                            'file': filepath.name,
                            'group': group_name,
                            'alert': alert_name,
                            'value': threshold_value,
                            'operator': operator,
                            'context': context.strip(),
                            'severity': rule.get('labels', {}).get('severity', 'unknown'),
                            'component': rule.get('labels', {}).get('component', 'unknown'),
                        })

    return thresholds

def categorize_thresholds(thresholds: List[Dict]) -> Dict[str, List[Dict]]:
    """Categorize thresholds by type for .env file organization."""
    categories = defaultdict(list)

    for t in thresholds:
        component = t['component']
        alert = t['alert']

        # Categorize by component or alert pattern
        if 'cost' in alert.lower() or 'budget' in alert.lower():
            category = 'llm_costs'
        elif 'hitl' in component.lower() or 'hitl' in alert.lower():
            category = 'hitl_quality'
        elif 'checkpoint' in alert.lower():
            category = 'checkpoint_persistence'
        elif 'business' in alert.lower() or 'abandonment' in alert.lower():
            category = 'business_metrics'
        elif 'oauth' in component.lower() or 'security' in component.lower():
            category = 'security'
        elif 'database' in alert.lower() or 'redis' in alert.lower():
            category = 'infrastructure'
        elif 'latency' in alert.lower() or 'duration' in alert.lower():
            category = 'performance'
        elif 'error' in alert.lower() or 'failure' in alert.lower():
            category = 'reliability'
        else:
            category = 'other'

        categories[category].append(t)

    return dict(categories)

def generate_env_variable_name(threshold: Dict) -> str:
    """Generate standardized .env variable name from threshold context."""
    alert = threshold['alert']
    operator = threshold['operator']

    # Convert CamelCase to SCREAMING_SNAKE_CASE
    # Example: HITLClarificationFallbackHigh -> HITL_CLARIFICATION_FALLBACK_HIGH
    parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+', alert)
    snake_case = '_'.join(parts).upper()

    # Add ALERT_ prefix
    env_var = f"ALERT_{snake_case}_THRESHOLD"

    return env_var

def main():
    """Main execution."""
    base_path = Path(__file__).parent

    # Files to analyze
    files = [
        base_path / 'alert_rules.yml',
        base_path / 'alerts.yml',
    ]

    all_thresholds = []

    print("=" * 80)
    print("THRESHOLD EXTRACTION - Prometheus Alert Files")
    print("=" * 80)
    print()

    # Extract from all files
    for filepath in files:
        if not filepath.exists():
            print(f"⚠️  File not found: {filepath}")
            continue

        print(f"Analyzing: {filepath.name}")
        thresholds = extract_thresholds_from_file(filepath)
        all_thresholds.extend(thresholds)
        print(f"  Found: {len(thresholds)} thresholds")

    print()
    print(f"TOTAL THRESHOLDS FOUND: {len(all_thresholds)}")
    print()

    # Categorize
    categories = categorize_thresholds(all_thresholds)

    print("THRESHOLDS BY CATEGORY:")
    print()
    for category, items in sorted(categories.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {category:25s} {len(items):3d} thresholds")

    print()

    # Generate .env variable names
    print("SAMPLE .ENV VARIABLE MAPPINGS:")
    print()
    sample_count = 0
    for threshold in all_thresholds[:10]:  # Show first 10
        env_var = generate_env_variable_name(threshold)
        print(f"  {env_var:60s} = {threshold['value']}")
        sample_count += 1

    if len(all_thresholds) > 10:
        print(f"  ... and {len(all_thresholds) - 10} more")

    print()

    # Save complete inventory
    inventory_file = base_path / 'thresholds_inventory.json'
    with open(inventory_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_count': len(all_thresholds),
            'categories': {k: len(v) for k, v in categories.items()},
            'thresholds': all_thresholds,
            'env_mappings': [
                {
                    'env_var': generate_env_variable_name(t),
                    'value': t['value'],
                    'alert': t['alert'],
                    'category': next(cat for cat, items in categories.items() if t in items),
                }
                for t in all_thresholds
            ],
        }, f, indent=2, ensure_ascii=False)

    print(f"[OK] Complete inventory saved to: {inventory_file}")
    print()

    # Summary statistics
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total Thresholds:    {len(all_thresholds)}")
    print(f"Unique Alerts:       {len(set(t['alert'] for t in all_thresholds))}")
    print(f"Files Analyzed:      {len(files)}")
    print(f"Categories:          {len(categories)}")
    print()
    print("Next Steps:")
    print("  1. Review thresholds_inventory.json")
    print("  2. Create production.env with strict values")
    print("  3. Create staging.env with permissive values")
    print("  4. Create development.env with very permissive values")
    print("  5. Template alert files with {{ env(...) }} syntax")
    print()

if __name__ == '__main__':
    main()
