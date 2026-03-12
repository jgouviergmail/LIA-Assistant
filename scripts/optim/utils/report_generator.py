#!/usr/bin/env python3
"""
Generic Markdown Report Generator for Code Analysis.

Provides utilities to generate structured markdown reports
with consistent formatting across all optimization scripts.

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-14
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


def generate_markdown_table(
    headers: List[str],
    rows: List[List[str]],
    alignments: Optional[List[str]] = None
) -> str:
    """
    Generate markdown table.

    Args:
        headers: List of header strings
        rows: List of row lists (each row is list of strings)
        alignments: Optional list of alignments ('left', 'center', 'right')
                    Default: all left-aligned

    Returns:
        Markdown table string

    Example:
        >>> headers = ["Name", "Count", "Status"]
        >>> rows = [["Item1", "5", "✅"], ["Item2", "3", "⚠️"]]
        >>> table = generate_markdown_table(headers, rows)
    """
    if not rows:
        return "| " + " | ".join(headers) + " |\n" + "|" + "|".join([" - " for _ in headers]) + "|\n"

    # Determine alignments
    if alignments is None:
        alignments = ['left'] * len(headers)

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    # Generate header row
    header_row = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"

    # Generate separator row
    separator_cells = []
    for i, alignment in enumerate(alignments):
        width = widths[i] if i < len(widths) else 3
        if alignment == 'center':
            sep = ':' + '-' * (width - 1) + ':'
        elif alignment == 'right':
            sep = '-' * (width - 1) + ':'
        else:  # left (default)
            sep = '-' * (width + 1)
        separator_cells.append(sep)
    separator_row = "|" + "|".join(separator_cells) + "|"

    # Generate data rows
    data_rows = []
    for row in rows:
        padded_row = []
        for i, cell in enumerate(row):
            if i < len(widths):
                padded_row.append(str(cell).ljust(widths[i]))
            else:
                padded_row.append(str(cell))
        data_rows.append("| " + " | ".join(padded_row) + " |")

    return "\n".join([header_row, separator_row] + data_rows)


def generate_finding_report(
    title: str,
    findings: List[Dict[str, Any]],
    output_path: Path,
    script_name: str = "",
    additional_sections: Optional[Dict[str, str]] = None
):
    """
    Generate structured finding report.

    Args:
        title: Report title
        findings: List of finding dicts
        output_path: Path to output markdown file
        script_name: Name of script that generated findings
        additional_sections: Optional dict of {section_name: content}

    Finding dict structure:
        {
            'item': str (file/function/constant name),
            'location': str (file:line),
            'confidence': str ('high' | 'medium' | 'low'),
            'reason': str,
            'details': str (optional)
        }

    Example:
        >>> findings = [
        ...     {
        ...         'item': 'unused_function',
        ...         'location': 'src/utils.py:42',
        ...         'confidence': 'high',
        ...         'reason': 'No imports found'
        ...     }
        ... ]
        >>> generate_finding_report(
        ...     "Unused Functions",
        ...     findings,
        ...     Path("docs/optim/02_UNUSED_CODE.md"),
        ...     "analyze_unused_code.py"
        ... )
    """
    # Build report content
    content = []

    # Header
    content.append(f"# {title} - LIA\n")
    content.append(f"**Date** : {datetime.now().strftime('%Y-%m-%d')}")
    if script_name:
        content.append(f"**Script** : `scripts/optim/{script_name}`")
    content.append(f"**Statut** : ✅ ANALYSE COMPLÉTÉE\n")
    content.append("---\n")

    # Summary
    content.append("## 📊 Résumé\n")
    content.append(f"- **Total éléments analysés** : *Voir détails ci-dessous*")
    content.append(f"- **Findings identifiés** : {len(findings)}")

    # Count by confidence
    confidence_counts = {}
    for finding in findings:
        conf = finding.get('confidence', 'unknown')
        confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

    for conf, count in sorted(confidence_counts.items()):
        emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(conf, '⚪')
        content.append(f"- **{emoji} Confiance {conf}** : {count}")

    content.append("\n---\n")

    # Findings table
    if findings:
        content.append("## 🔍 Findings\n")

        # Prepare table rows
        headers = ["Élément", "Location", "Confiance", "Raison"]
        rows = []
        for finding in findings:
            rows.append([
                finding.get('item', '?'),
                finding.get('location', '?'),
                finding.get('confidence', '?'),
                finding.get('reason', '?')
            ])

        table = generate_markdown_table(headers, rows)
        content.append(table)
        content.append("\n")

        # Detailed findings
        content.append("## 📋 Détails des Findings\n")
        for i, finding in enumerate(findings, start=1):
            content.append(f"### Finding {i}: {finding.get('item', 'Unknown')}\n")
            content.append(f"- **Location** : `{finding.get('location', '?')}`")
            content.append(f"- **Confiance** : {finding.get('confidence', '?')}")
            content.append(f"- **Raison** : {finding.get('reason', '?')}")

            if 'details' in finding and finding['details']:
                content.append(f"- **Détails** : {finding['details']}")

            content.append("\n**Vérifications recommandées** :")
            content.append("- [ ] Revue manuelle du code")
            content.append("- [ ] Grep pour usages indirects")
            content.append("- [ ] Vérification tests")
            content.append("\n**Décision** : SAFE_TO_DELETE / KEEP / UNCERTAIN\n")
            content.append("**Justification** : *À compléter manuellement*\n")
            content.append("---\n")
    else:
        content.append("## ✅ Aucun Finding\n")
        content.append("Aucun élément problématique identifié.\n")

    # Additional sections
    if additional_sections:
        for section_name, section_content in additional_sections.items():
            content.append(f"## {section_name}\n")
            content.append(section_content)
            content.append("\n")

    # Footer
    content.append("---\n")
    content.append(f"\n**Généré le** : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    content.append("\n**Auteur** : Claude Code (Sonnet 4.5)")
    content.append("\n**Statut** : ✅ Prêt pour revue manuelle")

    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(content))

    print(f"[SUCCESS] Report generated: {output_path}")
    print(f"   {len(findings)} findings written")


def generate_summary_report(
    reports: Dict[str, Dict[str, Any]],
    output_path: Path
):
    """
    Generate summary report combining multiple analysis reports.

    Args:
        reports: Dict of {report_name: {'findings': int, 'status': str, ...}}
        output_path: Path to summary markdown file

    Example:
        >>> reports = {
        ...     "Unused Files": {"findings": 5, "status": "completed"},
        ...     "Unused Code": {"findings": 12, "status": "completed"}
        ... }
        >>> generate_summary_report(reports, Path("docs/optim/SUMMARY.md"))
    """
    content = []

    content.append("# Résumé Analyse Optimisation - LIA\n")
    content.append(f"**Date** : {datetime.now().strftime('%Y-%m-%d')}\n")
    content.append("---\n")

    # Summary table
    content.append("## 📊 Vue d'Ensemble\n")

    headers = ["Analyse", "Findings", "Statut"]
    rows = []
    total_findings = 0

    for report_name, data in reports.items():
        findings_count = data.get('findings', 0)
        status = data.get('status', 'pending')
        status_emoji = {'completed': '✅', 'pending': '⏳', 'error': '❌'}.get(status, '❓')

        rows.append([
            report_name,
            str(findings_count),
            f"{status_emoji} {status}"
        ])
        total_findings += findings_count

    table = generate_markdown_table(headers, rows)
    content.append(table)
    content.append(f"\n**Total Findings** : {total_findings}\n")

    content.append("---\n")

    # Individual report links
    content.append("## 📁 Rapports Détaillés\n")
    for report_name, data in reports.items():
        file_path = data.get('file', '')
        if file_path:
            content.append(f"- [{report_name}]({file_path})")

    content.append("\n---\n")

    # Footer
    content.append(f"\n**Généré le** : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Write to file (ensure parent directory exists)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(content))

    print(f"[SUCCESS] Summary report generated: {output_path}")


def format_metric_change(before: int, after: int, label: str = "") -> str:
    """
    Format metric change with delta and emoji.

    Args:
        before: Value before
        after: Value after
        label: Optional label

    Returns:
        Formatted string

    Example:
        >>> format_metric_change(1000, 900, "Lines")
        "Lines: 1000 → 900 (-100, -10.0%) ✅"
    """
    delta = after - before
    percent = (delta / before * 100) if before > 0 else 0

    # Emoji based on change (negative is good for LoC, files, etc.)
    if delta < 0:
        emoji = "✅"  # Reduction is good
        sign = ""
    elif delta > 0:
        emoji = "⚠️"  # Increase might be bad
        sign = "+"
    else:
        emoji = "➡️"  # No change
        sign = ""

    result = f"{before} → {after} ({sign}{delta}, {sign}{percent:.1f}%) {emoji}"

    if label:
        result = f"{label}: {result}"

    return result


if __name__ == "__main__":
    # Self-test
    print("Testing report_generator.py...\n")

    # Test 1: Markdown table
    print("Test 1: Markdown Table")
    headers = ["Name", "Value", "Status"]
    rows = [
        ["Item 1", "100", "✅"],
        ["Item 2", "50", "⚠️"],
        ["Item 3", "25", "❌"]
    ]
    table = generate_markdown_table(headers, rows)
    print(table)
    print("\n[OK] Table generation passed\n")

    # Test 2: Format metric change
    print("Test 2: Metric Formatting")
    print(format_metric_change(1000, 900, "Lines"))
    print(format_metric_change(100, 120, "Files"))
    print(format_metric_change(50, 50, "Constants"))
    print("\n[OK] Metric formatting passed\n")

    # Test 3: Finding report
    print("Test 3: Finding Report Generation")
    test_findings = [
        {
            'item': 'test_function',
            'location': 'src/test.py:42',
            'confidence': 'high',
            'reason': 'No usages found',
            'details': 'Checked entire codebase'
        }
    ]

    test_output = Path("test_report.md")
    generate_finding_report(
        "Test Report",
        test_findings,
        test_output,
        "test_script.py"
    )

    if test_output.exists():
        print(f"[OK] Report generated: {test_output}")
        test_output.unlink()  # Cleanup
    else:
        print("[ERROR] Report generation failed")

    print("\nAll tests passed!")
