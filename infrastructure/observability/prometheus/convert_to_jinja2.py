#!/usr/bin/env python3
"""
Convert Prometheus alert files to Jinja2 templates with environment variable placeholders.

This script replaces all hardcoded threshold values with Jinja2 template syntax
using the delimiter convention <<< >>> to avoid conflicts with Prometheus {{ }}.

Uses thresholds_inventory.json to systematically replace all 80 thresholds.

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


def build_replacement_patterns(inventory: Dict) -> List[Tuple[str, str, str, Dict]]:
    """
    Build list of (pattern, replacement, alert_name, threshold_data) tuples.

    Returns list sorted by:
    1. Alert name
    2. Value (descending) - to replace larger values first (avoid partial matches)
    """
    patterns = []

    for threshold in inventory['thresholds']:
        alert_name = threshold['alert']
        value = threshold['value']
        operator = threshold['operator']
        source_file = threshold.get('source_file', '')

        # Find corresponding env variable
        env_mapping = next((m for m in inventory['env_mappings']
                           if m['alert'] == alert_name and m['value'] == value), None)

        if not env_mapping:
            continue

        env_var = env_mapping['env_var']

        # Build regex pattern and replacement for each operator type
        # Escape dots in numbers for regex
        value_escaped = str(value).replace('.', r'\.')

        if operator == 'greater_than':
            pattern = rf'>\s*{value_escaped}\b'
            replacement = f'> <<<{{ env "{env_var}" | default "{value}" }}>>>'
        elif operator == 'greater_equal':
            pattern = rf'>=\s*{value_escaped}\b'
            replacement = f'>= <<<{{ env "{env_var}" | default "{value}" }}>>>'
        elif operator == 'less_than':
            pattern = rf'<\s*{value_escaped}\b'
            replacement = f'< <<<{{ env "{env_var}" | default "{value}" }}>>>'
        elif operator == 'less_equal':
            pattern = rf'<=\s*{value_escaped}\b'
            replacement = f'<= <<<{{ env "{env_var}" | default "{value}" }}>>>'
        elif operator == 'equal':
            pattern = rf'==\s*{value_escaped}\b'
            replacement = f'== <<<{{ env "{env_var}" | default "{value}" }}>>>'
        else:
            continue

        patterns.append((pattern, replacement, alert_name, threshold))

    # Sort: by alert name, then by value descending (to replace 142.5 before 142)
    patterns.sort(key=lambda x: (x[2], -x[3]['value']))

    return patterns


def convert_file_to_jinja2(
    input_path: Path,
    output_path: Path,
    patterns: List[Tuple[str, str, str, Dict]],
    dry_run: bool = False
) -> Tuple[int, List[str]]:
    """
    Convert YAML file to Jinja2 template by replacing hardcoded thresholds.

    Args:
        input_path: Source YAML file
        output_path: Destination template file
        patterns: List of (regex_pattern, replacement, alert_name, threshold_data)
        dry_run: If True, only show what would be changed

    Returns:
        (replacement_count, list of changes)
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    changes = []
    replacement_count = 0
    current_alert = None

    # Track which patterns have been applied to avoid duplicate replacements
    applied_replacements = set()

    # Process line by line to maintain alert context
    lines = content.split('\n')
    new_lines = []

    for line_num, line in enumerate(lines, start=1):
        # Detect alert name
        alert_match = re.search(r'^\s*-?\s*alert:\s*(\w+)', line)
        if alert_match:
            current_alert = alert_match.group(1)
            new_lines.append(line)
            continue

        # Try to replace thresholds in this line
        modified_line = line

        # Only process expr lines and their continuations
        if current_alert and (
            'expr:' in line or
            (line_num > 1 and any(keyword in lines[line_num - 2] for keyword in ['expr:', 'expr: |']))
        ):
            # Try each pattern for this alert
            for pattern, replacement, alert_name, threshold_data in patterns:
                # Only apply if we're in the correct alert context
                if current_alert != alert_name:
                    continue

                # Check if pattern matches
                if re.search(pattern, modified_line):
                    # Create unique key to track this replacement
                    replacement_key = f"{alert_name}_{threshold_data['value']}_{line_num}"

                    if replacement_key not in applied_replacements:
                        old_line = modified_line
                        modified_line = re.sub(pattern, replacement, modified_line, count=1)

                        if old_line != modified_line:
                            replacement_count += 1
                            applied_replacements.add(replacement_key)

                            changes.append({
                                'alert': alert_name,
                                'line': line_num,
                                'before': old_line.strip(),
                                'after': modified_line.strip(),
                                'env_var': threshold_data.get('env_var', 'UNKNOWN'),
                                'value': threshold_data['value'],
                            })

                            # Break after first successful replacement on this line
                            # to avoid multiple replacements
                            break

        new_lines.append(modified_line)

    # Join back
    new_content = '\n'.join(new_lines)

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
        report.append(f"       ENV_VAR: {change['env_var']}")
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
    print("CONVERT PROMETHEUS ALERTS TO JINJA2 TEMPLATES")
    print("=" * 80)
    print()

    # Load inventory
    print(f"Loading inventory: {inventory_path}")
    inventory = load_inventory(inventory_path)
    print(f"  Total thresholds: {inventory['total_count']}")
    print(f"  Categories: {len(inventory['categories'])}")
    print()

    # Build replacement patterns
    print("Building replacement patterns...")
    patterns = build_replacement_patterns(inventory)
    print(f"  Patterns generated: {len(patterns)}")
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
        count, changes = convert_file_to_jinja2(
            input_path=input_path,
            output_path=output_path,
            patterns=patterns,
            dry_run=False
        )

        total_replacements += count
        all_changes.extend(changes)

        print(format_change_report(changes, max_display=3))

        # File info
        backup_path = input_path.with_suffix(input_path.suffix + '.original')
        print(f"\n  Backup created: {backup_path.name}")
        print(f"  Template created: {output_path.name}")
        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total replacements: {total_replacements} / {inventory['total_count']} thresholds")
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

    print()
    print("Next Steps:")
    print("  1. Review generated .jinja2 files")
    print("  2. Test with render_alerts.py:")
    print("     python render_alerts.py --env production --template alert_rules.yml.jinja2")
    print("  3. If satisfied, rename .jinja2 files to .yml.template")
    print("  4. Update render_alerts.py to handle alert_rules.yml.template")
    print("  5. Update docker-compose.yml to inject thresholds/ .env files")
    print()


if __name__ == '__main__':
    main()
