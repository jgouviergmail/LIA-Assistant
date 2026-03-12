#!/usr/bin/env python3
"""
Validate PromQL syntax in recording_rules.yml

This script performs basic syntax validation on PromQL expressions:
- Parentheses balance
- Curly braces balance
- Square brackets balance
- histogram_quantile percentile range (0.0-1.0)
- rate() time range format [Xm/h/d]
- by() clause syntax

Usage:
    python validate_promql.py recording_rules.yml
"""

import yaml
import re
import sys
from pathlib import Path


def validate_promql_expr(expr: str, record_name: str) -> tuple[list[str], list[str]]:
    """
    Validate a single PromQL expression.

    Returns:
        tuple: (errors, warnings)
    """
    errors = []
    warnings = []

    # Remove whitespace and newlines
    expr_clean = ' '.join(expr.split())

    # Check parentheses balance
    open_paren = expr_clean.count('(')
    close_paren = expr_clean.count(')')
    if open_paren != close_paren:
        errors.append(f'  [ERROR] {record_name}: Unbalanced parentheses ({open_paren} open, {close_paren} close)')
        return errors, warnings

    # Check curly braces balance
    open_curly = expr_clean.count('{')
    close_curly = expr_clean.count('}')
    if open_curly != close_curly:
        errors.append(f'  [ERROR] {record_name}: Unbalanced curly braces ({open_curly} open, {close_curly} close)')
        return errors, warnings

    # Check square brackets balance
    open_square = expr_clean.count('[')
    close_square = expr_clean.count(']')
    if open_square != close_square:
        errors.append(f'  [ERROR] {record_name}: Unbalanced square brackets ({open_square} open, {close_square} close)')
        return errors, warnings

    # Validate histogram_quantile percentile
    if 'histogram_quantile' in expr_clean:
        percentile_match = re.search(r'histogram_quantile\((0\.\d+|1\.0)', expr_clean)
        if not percentile_match:
            warnings.append(f'  [WARN] {record_name}: histogram_quantile percentile may be invalid (should be 0.0-1.0)')

    # Validate rate() time range
    if 'rate(' in expr_clean:
        time_range_match = re.search(r'\[\d+[smhd]\]', expr_clean)
        if not time_range_match:
            warnings.append(f'  [WARN] {record_name}: rate() missing or invalid time range [Xm/h/d]')

    # Validate 'by' clause
    if ' by ' in expr_clean:
        by_match = re.search(r'by\s*\([^)]+\)', expr_clean)
        if not by_match:
            warnings.append(f'  [WARN] {record_name}: "by" clause may be malformed')

    return errors, warnings


def main():
    # Load recording rules
    rules_path = Path('recording_rules.yml')

    if not rules_path.exists():
        print(f'[ERROR] File not found: {rules_path}')
        sys.exit(1)

    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f'[ERROR] YAML parsing failed: {e}')
        sys.exit(1)

    # Target groups for Phase 2.1
    optimized_groups = [
        'oauth_security_optimized',
        'hitl_quality_optimized',
        'redis_rate_limiting_optimized',
        'langgraph_framework_optimized',
        'llm_performance_optimized'
    ]

    all_errors = []
    all_warnings = []
    validated_count = 0

    print('Validating PromQL expressions in Phase 2.1 optimized rules...')
    print()

    for group in data.get('groups', []):
        group_name = group.get('name', 'unnamed')

        # Only validate Phase 2.1 optimized groups
        if group_name not in optimized_groups:
            continue

        print(f'Group: {group_name}')

        for rule in group.get('rules', []):
            record_name = rule.get('record', 'unnamed')
            expr = rule.get('expr', '')

            errors, warnings = validate_promql_expr(expr, record_name)

            all_errors.extend(errors)
            all_warnings.extend(warnings)

            if not errors:
                print(f'  [PASS] {record_name}')
                validated_count += 1
            else:
                print(f'  [FAIL] {record_name}')

    print()
    print('Validation Summary:')
    print(f'  - Validated expressions: {validated_count}')
    print(f'  - Errors: {len(all_errors)}')
    print(f'  - Warnings: {len(all_warnings)}')

    if all_errors:
        print()
        print('Errors:')
        for err in all_errors:
            print(err)

    if all_warnings:
        print()
        print('Warnings:')
        for warn in all_warnings:
            print(warn)

    if all_errors:
        print()
        print('[FAILED] PromQL syntax validation failed with {} errors'.format(len(all_errors)))
        sys.exit(1)

    print()
    print('[SUCCESS] PromQL syntax validation PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
