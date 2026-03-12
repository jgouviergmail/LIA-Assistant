#!/usr/bin/env python3
"""
Run All Optimization Analysis Scripts.

Orchestrates execution of all optimization analysis scripts in sequence:
1. analyze_unused_files.py
2. analyze_unused_code.py
3. analyze_constants.py
4. analyze_magic_values.py
5. analyze_code_duplication.py
6. analyze_env.py
7. analyze_performance.py
8. analyze_complexity_advanced.py

Creates a summary report with all findings.

Usage:
    python scripts/optim/run_all_analysis.py
    python scripts/optim/run_all_analysis.py --skip-slow  # Skip time-intensive analyses

Output:
    docs/optim/SUMMARY.md (consolidated report)
    docs/optim/iterations/YYYY-MM-DD_run.log (execution log)

Author: Claude Code (Opus 4.5)
Date: 2025-12-24
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure output directories exist
DOCS_OPTIM = Path("docs/optim")
DOCS_OPTIM.mkdir(parents=True, exist_ok=True)
ITERATIONS_DIR = DOCS_OPTIM / "iterations"
ITERATIONS_DIR.mkdir(parents=True, exist_ok=True)

# Script definitions: (script_name, description, is_slow)
ANALYSIS_SCRIPTS: List[Tuple[str, str, bool]] = [
    ("analyze_unused_files.py", "Unused Files Detection", False),
    ("analyze_unused_code.py", "Unused Code Detection", False),
    ("analyze_constants.py", "Constants Analysis", False),
    ("analyze_magic_values.py", "Magic Values Detection", False),
    ("analyze_code_duplication.py", "Code Duplication", True),
    ("analyze_env.py", "Environment Variables", False),
    ("analyze_performance.py", "Performance Issues", False),
    ("analyze_complexity_advanced.py", "Code Complexity", True),
]

# Map script to output file
SCRIPT_OUTPUT_MAP = {
    "analyze_unused_files.py": "01_UNUSED_FILES.md",
    "analyze_unused_code.py": "02_UNUSED_CODE.md",
    "analyze_constants.py": "03_CONSTANTS.md",
    "analyze_magic_values.py": "04_MAGIC_VALUES.md",
    "analyze_code_duplication.py": "05_CODE_DUPLICATION.md",
    "analyze_env.py": "06_ENV_ANALYSIS.md",
    "analyze_performance.py": "07_PERFORMANCE.md",
    "analyze_complexity_advanced.py": "08_COMPLEXITY.md",
}


def run_script(script_name: str, script_dir: Path) -> Tuple[bool, str]:
    """
    Run a single analysis script.

    Args:
        script_name: Name of script file
        script_dir: Directory containing scripts

    Returns:
        Tuple of (success, output)
    """
    script_path = script_dir / script_name

    if not script_path.exists():
        return False, f"Script not found: {script_path}"

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=Path.cwd(),
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]: {result.stderr}"

        return result.returncode == 0, output

    except subprocess.TimeoutExpired:
        return False, "Script timed out (5 minutes)"
    except Exception as e:
        return False, f"Error running script: {e}"


def count_findings_in_report(report_path: Path) -> int:
    """
    Count findings in a report file.

    Args:
        report_path: Path to markdown report

    Returns:
        Number of findings (extracted from summary or 0 if not found)
    """
    if not report_path.exists():
        return 0

    try:
        content = report_path.read_text(encoding="utf-8")
        # Look for "Findings identified: X" or legacy French pattern
        import re
        match = re.search(r"Findings (?:identifi[eé]s|identified)[^\d]*(\d+)", content)
        if match:
            return int(match.group(1))
    except Exception:
        pass

    return 0


def generate_summary(results: Dict[str, Dict]) -> None:
    """
    Generate consolidated summary report.

    Args:
        results: Dict of {script_name: {'success': bool, 'findings': int, ...}}
    """
    sys.path.insert(0, str(Path(__file__).parent / "utils"))
    from report_generator import generate_summary_report

    reports = {}
    for script_name, data in results.items():
        report_name = script_name.replace("analyze_", "").replace(".py", "").replace("_", " ").title()
        output_file = SCRIPT_OUTPUT_MAP.get(script_name, "")

        reports[report_name] = {
            "findings": data.get("findings", 0),
            "status": "completed" if data.get("success") else "error",
            "file": output_file,
        }

    generate_summary_report(reports, DOCS_OPTIM / "SUMMARY.md")


def main():
    """Main orchestration function."""
    parser = argparse.ArgumentParser(
        description="Run all optimization analysis scripts"
    )
    parser.add_argument(
        "--skip-slow",
        action="store_true",
        help="Skip time-intensive analyses (duplication, complexity)"
    )
    parser.add_argument(
        "--only",
        nargs="+",
        help="Run only specific scripts (e.g., --only analyze_unused_files.py)"
    )
    args = parser.parse_args()

    # Setup
    script_dir = Path(__file__).parent
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = ITERATIONS_DIR / f"{timestamp}_run.log"

    log_lines = [
        f"# Optimization Analysis Run - {timestamp}",
        f"Arguments: {' '.join(sys.argv[1:])}",
        "",
    ]

    print("=" * 60)
    print("  LIA OPTIMIZATION ANALYSIS")
    print(f"  Started: {timestamp}")
    print("=" * 60)
    print()

    # Determine which scripts to run
    scripts_to_run = []
    for script_name, description, is_slow in ANALYSIS_SCRIPTS:
        if args.only and script_name not in args.only:
            continue
        if args.skip_slow and is_slow:
            print(f"[SKIP] {script_name} (--skip-slow enabled)")
            log_lines.append(f"[SKIP] {script_name} - slow analysis skipped")
            continue
        scripts_to_run.append((script_name, description))

    if not scripts_to_run:
        print("[ERROR] No scripts to run. Check arguments.")
        return 1

    # Run scripts
    results = {}
    total_scripts = len(scripts_to_run)

    for i, (script_name, description) in enumerate(scripts_to_run, 1):
        print(f"\n[{i}/{total_scripts}] Running: {description}")
        print(f"    Script: {script_name}")
        print("    " + "-" * 40)

        success, output = run_script(script_name, script_dir)

        # Count findings from output file
        output_file = SCRIPT_OUTPUT_MAP.get(script_name, "")
        findings = 0
        if output_file:
            findings = count_findings_in_report(DOCS_OPTIM / output_file)

        results[script_name] = {
            "success": success,
            "findings": findings,
            "output": output[:500] if output else "",
        }

        # Log and display result
        status_emoji = "✅" if success else "❌"
        status_text = "SUCCESS" if success else "FAILED"
        print(f"    {status_emoji} {status_text} - {findings} findings")

        log_lines.append(f"\n## {script_name}")
        log_lines.append(f"Status: {status_text}")
        log_lines.append(f"Findings: {findings}")
        if not success:
            log_lines.append(f"Output:\n{output[:1000]}")

    # Generate summary
    print("\n" + "=" * 60)
    print("  GENERATING SUMMARY REPORT")
    print("=" * 60)

    try:
        generate_summary(results)
        print(f"✅ Summary report: docs/optim/SUMMARY.md")
        log_lines.append("\n## Summary")
        log_lines.append("Summary report generated: docs/optim/SUMMARY.md")
    except Exception as e:
        print(f"❌ Failed to generate summary: {e}")
        log_lines.append(f"\n## Summary\nFailed: {e}")

    # Write log file
    log_file.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"📋 Log file: {log_file}")

    # Final statistics
    print("\n" + "=" * 60)
    print("  FINAL STATISTICS")
    print("=" * 60)
    successful = sum(1 for r in results.values() if r["success"])
    failed = len(results) - successful
    total_findings = sum(r["findings"] for r in results.values())

    print(f"  Scripts run: {len(results)}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Total findings: {total_findings}")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
