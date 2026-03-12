#!/usr/bin/env python3
"""
Generate environment-specific threshold .env files from inventory.

This script creates production.env, staging.env, and development.env files
with appropriate threshold values for each environment.

Strategy:
- Production: Use current values (strict monitoring)
- Staging: Relax thresholds by 2x (more permissive)
- Development: Relax thresholds by 5x (very permissive, reduce alert noise)

Author: Infrastructure Team
Date: 2025-11-23
"""

import json
from pathlib import Path
from typing import Dict, List

# Multipliers for each environment
# Higher value = more permissive threshold
ENVIRONMENT_MULTIPLIERS = {
    'production': 1.0,    # Strict
    'staging': 2.0,       # Moderate
    'development': 5.0,   # Permissive
}

def load_inventory(inventory_path: Path) -> Dict:
    """Load thresholds inventory JSON."""
    with open(inventory_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def adjust_threshold(base_value: float, multiplier: float, operator: str) -> float:
    """
    Adjust threshold value based on environment multiplier and operator.

    For "greater_than" operators (>): multiply to make less sensitive
    For "less_than" operators (<): divide to make less sensitive
    For percentages (0-1): ensure stays in valid range
    """
    if operator in ['greater_than', 'greater_equal']:
        # Example: error_rate > 0.05 (5%)
        # Production: 0.05, Staging: 0.10, Dev: 0.25
        adjusted = base_value * multiplier
    elif operator in ['less_than', 'less_equal']:
        # Example: tokens_per_sec < 20
        # Production: 20, Staging: 10, Dev: 4
        adjusted = base_value / multiplier if base_value > 0 else base_value
    else:  # equal
        adjusted = base_value

    # For percentage values (0-1 range), cap at 0.99
    if 0 < base_value < 1.0 and 0 < adjusted < 10:
        adjusted = min(adjusted, 0.99)

    return adjusted

def generate_env_file(inventory: Dict, environment: str, output_path: Path):
    """Generate .env file for specific environment."""
    multiplier = ENVIRONMENT_MULTIPLIERS[environment]
    env_mappings = inventory['env_mappings']
    categories = inventory['categories']

    # Group by category
    by_category = {}
    for mapping in env_mappings:
        cat = mapping['category']
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(mapping)

    # Generate file content
    lines = []
    lines.append("# " + "=" * 77)
    lines.append(f"# Prometheus Alert Thresholds - {environment.upper()} Environment")
    lines.append("# " + "=" * 77)
    lines.append("#")
    lines.append("# Auto-generated from thresholds_inventory.json")
    lines.append(f"# Environment: {environment}")
    lines.append(f"# Multiplier: {multiplier}x (vs production)")
    lines.append(f"# Total thresholds: {len(env_mappings)}")
    lines.append("#")
    lines.append("# DO NOT EDIT MANUALLY - Use generate_threshold_envs.py")
    lines.append("# " + "=" * 77)
    lines.append("")

    # Add thresholds by category
    for category, mappings in sorted(by_category.items(), key=lambda x: len(x[1]), reverse=True):
        lines.append("")
        lines.append(f"# ===== {category.upper().replace('_', ' ')} ({len(mappings)} thresholds) =====")
        lines.append("")

        for mapping in sorted(mappings, key=lambda x: x['env_var']):
            env_var = mapping['env_var']
            base_value = mapping['value']
            alert_name = mapping['alert']

            # Get operator from full threshold data
            threshold_data = next((t for t in inventory['thresholds']
                                 if t['alert'] == alert_name and t['value'] == base_value), None)
            operator = threshold_data['operator'] if threshold_data else 'greater_than'

            # Adjust for environment
            adjusted_value = adjust_threshold(base_value, multiplier, operator)

            # Format comment
            comment = f"# {alert_name}"
            if environment != 'production':
                comment += f" (base: {base_value})"

            # Write variable
            lines.append(comment)
            lines.append(f"{env_var}={adjusted_value}")
            lines.append("")

    # Add footer
    lines.append("# " + "=" * 77)
    lines.append("# End of thresholds")
    lines.append("# " + "=" * 77)

    # Write file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"[OK] Generated: {output_path} ({len(env_mappings)} thresholds, {multiplier}x)")

def main():
    """Main execution."""
    base_path = Path(__file__).parent
    inventory_path = base_path / 'thresholds_inventory.json'
    output_dir = base_path / 'thresholds'

    print("=" * 80)
    print("GENERATE THRESHOLD .ENV FILES")
    print("=" * 80)
    print()

    # Load inventory
    print(f"Loading inventory: {inventory_path}")
    inventory = load_inventory(inventory_path)
    print(f"  Total thresholds: {inventory['total_count']}")
    print(f"  Categories: {len(inventory['categories'])}")
    print()

    # Create output directory
    output_dir.mkdir(exist_ok=True)
    print(f"Output directory: {output_dir}")
    print()

    # Generate for each environment
    for environment in ['production', 'staging', 'development']:
        output_path = output_dir / f'{environment}.env'
        generate_env_file(inventory, environment, output_path)

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Files generated: 3")
    print(f"Thresholds per file: {inventory['total_count']}")
    print()
    print("Next Steps:")
    print("  1. Review generated .env files in thresholds/")
    print("  2. Modify alert_rules.yml and alerts.yml to use {{ env(...) }} templating")
    print("  3. Update docker-compose.yml to inject environment variables")
    print("  4. Test Prometheus reload")
    print()

if __name__ == '__main__':
    main()
