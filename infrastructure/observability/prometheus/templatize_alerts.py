#!/usr/bin/env python3
"""
Templatize Prometheus alert files with Jinja2 environment variables.

This script replaces all hardcoded threshold values in alert_rules.yml and alerts.yml
with Jinja2 template syntax {{ env "ALERT_*_THRESHOLD" | default "value" }}.

Uses thresholds_inventory.json to map alert names to environment variable names.

Author: Infrastructure Team
Date: 2025-11-23
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple
import shutil


def load_inventory(inventory_path: Path) -> Dict:
    """Load thresholds inventory JSON."""
    with open(inventory_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_threshold_map(inventory: Dict) -> Dict[str, Dict]:
    """
    Create mapping from alert name to threshold details.

    Returns:
        Dict[alert_name, Dict[value, env_var, operator]]
    """
    threshold_map = {}

    for threshold in inventory['thresholds']:
        alert = threshold['alert']
        value = threshold['value']
        operator = threshold['operator']

        # Find corresponding env variable
        env_mapping = next((m for m in inventory['env_mappings']
                           if m['alert'] == alert and m['value'] == value), None)

        if env_mapping:
            env_var = env_mapping['env_var']

            # Store with composite key (alert + value) to handle duplicates
            key = f"{alert}_{value}"
            threshold_map[key] = {
                'alert': alert,
                'value': value,
                'env_var': env_var,
                'operator': operator,
            }

    return threshold_map


def escape_for_regex(value: float) -> str:
    """Escape a threshold value for use in regex."""
    # Convert to string, escape dots
    value_str = str(value)
    return value_str.replace('.', r'\.')


def templatize_yaml_file(
    input_path: Path,
    output_path: Path,
    threshold_map: Dict[str, Dict],
    dry_run: bool = False
) -> Tuple[int, List[str]]:
    """
    Replace hardcoded thresholds with Jinja2 templates in YAML file.

    Args:
        input_path: Source YAML file
        output_path: Destination YAML file
        threshold_map: Mapping from alert to threshold details
        dry_run: If True, only show what would be changed

    Returns:
        (replacement_count, list of changes)
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    changes = []
    replacement_count = 0

    # Track current alert context
    current_alert = None

    # Process line by line to maintain context
    lines = content.split('\n')
    new_lines = []

    for i, line in enumerate(lines):
        # Detect alert name
        alert_match = re.search(r'^\s*-?\s*alert:\s*(\w+)', line)
        if alert_match:
            current_alert = alert_match.group(1)
            new_lines.append(line)
            continue

        # Look for threshold comparisons in expr
        if current_alert and ('expr:' in line or i > 0 and 'expr:' in lines[i-1]):
            # Try to find and replace thresholds
            modified_line = line

            # Search for matching thresholds in our inventory
            for key, threshold_data in threshold_map.items():
                alert_name = threshold_data['alert']
                value = threshold_data['value']
                env_var = threshold_data['env_var']
                operator = threshold_data['operator']

                # Only process if we're in the correct alert context
                if current_alert != alert_name:
                    continue

                # Build regex pattern based on operator
                if operator == 'greater_than':
                    pattern = rf'>\s*{escape_for_regex(value)}\b'
                    replacement = f'> {{{{ env "{env_var}" | default "{value}" }}}}'
                elif operator == 'greater_equal':
                    pattern = rf'>=\s*{escape_for_regex(value)}\b'
                    replacement = f'>= {{{{ env "{env_var}" | default "{value}" }}}}'
                elif operator == 'less_than':
                    pattern = rf'<\s*{escape_for_regex(value)}\b'
                    replacement = f'< {{{{ env "{env_var}" | default "{value}" }}}}'
                elif operator == 'less_equal':
                    pattern = rf'<=\s*{escape_for_regex(value)}\b'
                    replacement = f'<= {{{{ env "{env_var}" | default "{value}" }}}}'
                elif operator == 'equal':
                    pattern = rf'==\s*{escape_for_regex(value)}\b'
                    replacement = f'== {{{{ env "{env_var}" | default "{value}" }}}}'
                else:
                    continue

                # Try to replace
                if re.search(pattern, modified_line):
                    old_line = modified_line
                    modified_line = re.sub(pattern, replacement, modified_line)

                    if old_line != modified_line:
                        replacement_count += 1
                        changes.append(
                            f"[{current_alert}] Line {i+1}:\n"
                            f"  BEFORE: {old_line.strip()}\n"
                            f"  AFTER:  {modified_line.strip()}\n"
                            f"  ENV_VAR: {env_var}"
                        )

            new_lines.append(modified_line)
        else:
            new_lines.append(line)

    # Join back
    new_content = '\n'.join(new_lines)

    # Write output
    if not dry_run:
        # Backup original
        backup_path = input_path.with_suffix(input_path.suffix + '.backup')
        shutil.copy2(input_path, backup_path)

        # Write templatized version
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

    return replacement_count, changes


def main():
    """Main execution."""
    base_path = Path(__file__).parent
    inventory_path = base_path / 'thresholds_inventory.json'

    # Alert files to process
    alert_files = [
        base_path / 'alert_rules.yml',
        base_path / 'alerts.yml',
    ]

    print("=" * 80)
    print("TEMPLATIZE PROMETHEUS ALERT FILES")
    print("=" * 80)
    print()

    # Load inventory
    print(f"Loading inventory: {inventory_path}")
    inventory = load_inventory(inventory_path)
    threshold_map = create_threshold_map(inventory)
    print(f"  Loaded {len(threshold_map)} threshold mappings")
    print()

    # Process each file
    total_replacements = 0

    for alert_file in alert_files:
        if not alert_file.exists():
            print(f"[SKIP] File not found: {alert_file}")
            continue

        print(f"Processing: {alert_file.name}")
        print("-" * 80)

        # Create output path
        output_file = alert_file.with_suffix('.yml.template')

        # Templatize
        count, changes = templatize_yaml_file(
            input_path=alert_file,
            output_path=output_file,
            threshold_map=threshold_map,
            dry_run=False
        )

        total_replacements += count

        print(f"  Replacements: {count}")

        if changes:
            print(f"  Sample changes (first 3):")
            for change in changes[:3]:
                print(f"    {change}")

        # File info
        backup_file = alert_file.with_suffix(alert_file.suffix + '.backup')
        print(f"  Backup created: {backup_file.name}")
        print(f"  Template created: {output_file.name}")
        print()

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total replacements: {total_replacements}")
    print(f"Files processed: {len([f for f in alert_files if f.exists()])}")
    print()
    print("Next Steps:")
    print("  1. Review generated .yml.template files")
    print("  2. Compare with .backup files to verify changes")
    print("  3. Rename .yml.template to .yml when satisfied")
    print("  4. Update docker-compose.yml to inject environment variables")
    print("  5. Test Prometheus reload with new templates")
    print()


if __name__ == '__main__':
    main()
