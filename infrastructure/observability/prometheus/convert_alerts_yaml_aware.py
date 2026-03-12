#!/usr/bin/env python3
"""
Convert Prometheus alert files to Jinja2 templates with YAML-aware parsing.

This script:
1. Parses YAML structure to identify alert blocks
2. Replaces hardcoded thresholds with Jinja2 templates
3. Preserves formatting, comments, and structure
4. Uses <<< >>> delimiters (Jinja2 custom, compatible with render_alerts.py)

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


def find_alert_blocks(content: str) -> List[Dict]:
    """
    Find all alert blocks in content with their line ranges.

    Returns list of:
    {
        'name': 'AlertName',
        'start_line': 46,
        'end_line': 73,
        'content_start': line_num_of_expr,
    }
    """
    lines = content.split('\n')
    blocks = []
    current_block = None

    for i, line in enumerate(lines, start=1):
        # Detect start of alert block
        alert_match = re.search(r'^\s*-?\s*alert:\s*(\w+)', line)
        if alert_match:
            # Save previous block if exists
            if current_block:
                current_block['end_line'] = i - 1
                blocks.append(current_block)

            # Start new block
            current_block = {
                'name': alert_match.group(1),
                'start_line': i,
                'end_line': None,
            }

        # Detect start of next alert or end of file
        elif current_block and i == len(lines):
            current_block['end_line'] = i
            blocks.append(current_block)

    # Close last block
    if current_block and current_block['end_line'] is None:
        current_block['end_line'] = len(lines)
        blocks.append(current_block)

    return blocks


def build_threshold_map(inventory: Dict) -> Dict[str, List[Dict]]:
    """
    Build mapping from alert name to list of threshold replacements.

    Returns:
    {
        'AlertName': [
            {
                'value': 0.30,
                'env_var': 'ALERT_..._THRESHOLD',
                'operator': 'greater_than',
                'pattern': r'> 0\.30\b',
                'replacement': '> <<<{{ env "..." | default "0.30" }}>>>',
            },
            ...
        ],
        ...
    }
    """
    threshold_map = {}

    for threshold in inventory['thresholds']:
        alert_name = threshold['alert']
        value = threshold['value']
        operator = threshold['operator']

        # Find corresponding env variable
        env_mapping = next((m for m in inventory['env_mappings']
                           if m['alert'] == alert_name and m['value'] == value), None)

        if not env_mapping:
            continue

        env_var = env_mapping['env_var']

        # Build regex pattern and replacement
        # Handle both integer and float representations (e.g., 4500 and 4500.0)
        # Also handle trailing zeros (e.g., 0.3 matches 0.30, 0.300, etc.)
        if value == int(value):
            # Integer value: match both "4500" and "4500.0", "4500.00", etc.
            value_int = int(value)
            pattern_base = rf'({value_int}(?:\.0+)?)'
        else:
            # Float value: match with optional trailing zeros
            # Convert 0.3 to pattern that matches 0.3, 0.30, 0.300, etc.
            value_str = str(value)
            # Split on decimal point
            if '.' in value_str:
                int_part, dec_part = value_str.split('.')
                # Remove existing trailing zeros for canonical form
                dec_part_canonical = dec_part.rstrip('0') or '0'
                # Build pattern: int_part\.dec_part_canonical0*
                pattern_base = rf'{int_part}\.{dec_part_canonical}0*'
            else:
                # Should not happen for float, but handle anyway
                value_escaped = value_str.replace('.', r'\.')
                pattern_base = value_escaped

        if operator == 'greater_than':
            pattern = rf'>\s*{pattern_base}\b'
            replacement = f'> <<<{env_var}>>>'
        elif operator == 'greater_equal':
            pattern = rf'>=\s*{pattern_base}\b'
            replacement = f'>= <<<{env_var}>>>'
        elif operator == 'less_than':
            pattern = rf'<\s*{pattern_base}\b'
            replacement = f'< <<<{env_var}>>>'
        elif operator == 'less_equal':
            pattern = rf'<=\s*{pattern_base}\b'
            replacement = f'<= <<<{env_var}>>>'
        elif operator == 'equal':
            pattern = rf'==\s*{pattern_base}\b'
            replacement = f'== <<<{env_var}>>>'
        else:
            continue

        if alert_name not in threshold_map:
            threshold_map[alert_name] = []

        threshold_map[alert_name].append({
            'value': value,
            'env_var': env_var,
            'operator': operator,
            'pattern': pattern,
            'replacement': replacement,
        })

    # Sort thresholds by value descending (replace larger values first)
    for alert_name in threshold_map:
        threshold_map[alert_name].sort(key=lambda x: -x['value'])

    return threshold_map


def convert_file_yaml_aware(
    input_path: Path,
    output_path: Path,
    threshold_map: Dict[str, List[Dict]],
    dry_run: bool = False
) -> Tuple[int, List[Dict]]:
    """
    Convert YAML file to Jinja2 template with YAML-aware parsing.

    Args:
        input_path: Source YAML file
        output_path: Destination template file
        threshold_map: Mapping from alert name to threshold replacements
        dry_run: If True, only show what would be changed

    Returns:
        (replacement_count, list of changes)
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all alert blocks
    alert_blocks = find_alert_blocks(content)

    lines = content.split('\n')
    changes = []
    replacement_count = 0

    # Process each alert block
    for block in alert_blocks:
        alert_name = block['name']

        # Skip if no thresholds for this alert
        if alert_name not in threshold_map:
            continue

        # Process lines in this alert block
        for line_num in range(block['start_line'], block['end_line'] + 1):
            if line_num > len(lines):
                break

            line = lines[line_num - 1]  # Convert to 0-indexed

            # Try each threshold replacement for this alert
            for threshold_def in threshold_map[alert_name]:
                pattern = threshold_def['pattern']
                replacement = threshold_def['replacement']

                if re.search(pattern, line):
                    old_line = line
                    new_line = re.sub(pattern, replacement, line, count=1)

                    if old_line != new_line:
                        lines[line_num - 1] = new_line
                        replacement_count += 1

                        changes.append({
                            'alert': alert_name,
                            'line': line_num,
                            'before': old_line.strip(),
                            'after': new_line.strip(),
                            'env_var': threshold_def['env_var'],
                            'value': threshold_def['value'],
                        })

                        # Break to avoid multiple replacements on same line
                        break

    # Join back
    new_content = '\n'.join(lines)

    # Write output
    if not dry_run:
        # Backup original (if not already backed up)
        backup_path = input_path.with_suffix(input_path.suffix + '.original')
        if not backup_path.exists():
            shutil.copy2(input_path, backup_path)

        # Write template
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

    return replacement_count, changes


def format_change_report(changes: List[Dict], max_display: int = 5) -> str:
    """Format change report for display."""
    if not changes:
        return "  No changes"

    report = []
    report.append(f"  Total changes: {len(changes)}")
    report.append("")
    report.append(f"  Sample changes (first {min(max_display, len(changes))}):")

    for i, change in enumerate(changes[:max_display], 1):
        report.append(f"    {i}. [{change['alert']}] Line {change['line']}:")
        report.append(f"       BEFORE: {change['before']}")
        report.append(f"       AFTER:  {change['after']}")
        report.append(f"       ENV: {change['env_var']} = {change['value']}")
        report.append("")

    if len(changes) > max_display:
        report.append(f"    ... and {len(changes) - max_display} more changes")

    return '\n'.join(report)


def main():
    """Main execution."""
    base_path = Path(__file__).parent
    inventory_path = base_path / 'thresholds_inventory.json'

    # Alert files to process
    files_to_process = [
        {
            'input': base_path / 'alert_rules.yml',
            'output': base_path / 'alert_rules.yml.jinja2',
        },
        {
            'input': base_path / 'alerts.yml',
            'output': base_path / 'alerts.yml.jinja2',
        },
    ]

    print("=" * 80)
    print("CONVERT PROMETHEUS ALERTS TO JINJA2 TEMPLATES (YAML-AWARE)")
    print("=" * 80)
    print()

    # Load inventory
    print(f"Loading inventory: {inventory_path}")
    inventory = load_inventory(inventory_path)
    print(f"  Total thresholds: {inventory['total_count']}")
    print(f"  Unique alerts: {len(set(t['alert'] for t in inventory['thresholds']))}")
    print()

    # Build threshold map
    print("Building threshold map...")
    threshold_map = build_threshold_map(inventory)
    print(f"  Alerts with thresholds: {len(threshold_map)}")
    total_thresholds = sum(len(thresholds) for thresholds in threshold_map.values())
    print(f"  Total threshold replacements: {total_thresholds}")
    print()

    # Process each file
    total_replacements = 0
    all_changes = []

    for file_config in files_to_process:
        input_path = file_config['input']
        output_path = file_config['output']

        if not input_path.exists():
            print(f"[SKIP] File not found: {input_path}")
            continue

        print(f"Processing: {input_path.name}")
        print("-" * 80)

        # Convert to Jinja2
        count, changes = convert_file_yaml_aware(
            input_path=input_path,
            output_path=output_path,
            threshold_map=threshold_map,
            dry_run=False
        )

        total_replacements += count
        all_changes.extend(changes)

        print(format_change_report(changes, max_display=5))

        # File info
        backup_path = input_path.with_suffix(input_path.suffix + '.original')
        if backup_path.exists():
            print(f"\n  Backup: {backup_path.name}")
        print(f"  Template: {output_path.name}")
        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total replacements: {total_replacements} / {inventory['total_count']} thresholds")
    print(f"Coverage: {100 * total_replacements / inventory['total_count']:.1f}%")
    print(f"Files processed: {len([f for f in files_to_process if f['input'].exists()])}")
    print()

    # Breakdown by alert
    alerts_modified = {}
    for change in all_changes:
        alert = change['alert']
        alerts_modified[alert] = alerts_modified.get(alert, 0) + 1

    print(f"Alerts modified: {len(alerts_modified)}")
    print("\nTop 10 alerts by replacements:")
    for alert, count in sorted(alerts_modified.items(), key=lambda x: -x[1])[:10]:
        print(f"  {alert}: {count} replacements")

    # Alerts NOT modified
    expected_alerts = set(threshold_map.keys())
    modified_alerts = set(alerts_modified.keys())
    missing_alerts = expected_alerts - modified_alerts

    if missing_alerts:
        print(f"\nAlerts NOT modified ({len(missing_alerts)}):")
        for alert in sorted(missing_alerts)[:10]:
            print(f"  - {alert}")
        if len(missing_alerts) > 10:
            print(f"  ... and {len(missing_alerts) - 10} more")

    print()
    print("Next Steps:")
    print("  1. Review generated .jinja2 files")
    print("  2. Compare with .original files to verify replacements")
    print("  3. Test with render_alerts.py:")
    print("     python render_alerts.py --env production --template alert_rules.yml.jinja2")
    print("  4. If satisfied, rename .jinja2 to .yml.template")
    print("  5. Update docker-compose.yml to inject environment variables")
    print()


if __name__ == '__main__':
    main()
