#!/usr/bin/env python3
"""
Detect Potentially Unused Python Files.

Strategy:
1. List all .py files in src/
2. For each file, extract module name
3. Search for imports across entire codebase
4. Flag files with 0 imports as potentially unused
5. Manual review required for:
   - Entry points (main.py, __init__.py)
   - Dynamic imports (importlib, __import__)
   - CLI commands
   - FastAPI routes (via decorators)

Usage:
    python scripts/optim/analyze_unused_files.py

Output:
    docs/optim/01_UNUSED_FILES.md

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-14
"""

import sys
from pathlib import Path

# Add utils to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "utils"))

from grep_helper import find_files_importing, extract_module_name_from_path
from report_generator import generate_finding_report


# Configuration
SRC_ROOT = Path("apps/api/src")
OUTPUT_FILE = Path("docs/optim/01_UNUSED_FILES.md")

# Files to exclude from analysis (always used)
EXCLUDE_FILES = [
    "__init__.py",  # Package initialization
    "__main__.py",  # Entry points
    "main.py",      # Application entry point
]

# Directories to exclude
EXCLUDE_DIRS = [
    "__pycache__",
    ".venv",
    ".git",
    "alembic/versions",  # Migration files (referenced by Alembic, not imported)
]


def is_excluded_file(file_path: Path) -> bool:
    """Check if file should be excluded from analysis."""
    return file_path.name in EXCLUDE_FILES


def analyze_unused_files():
    """
    Main analysis function.

    Returns:
        List of findings
    """
    print("[*] Analyzing unused files...")
    print(f"   Source root: {SRC_ROOT}")
    print(f"   Output: {OUTPUT_FILE}\n")

    if not SRC_ROOT.exists():
        print(f"[ERROR] Source root not found: {SRC_ROOT}")
        sys.exit(1)

    findings = []
    total_files = 0
    excluded_files = 0

    # Iterate through all Python files
    for py_file in SRC_ROOT.rglob("*.py"):
        total_files += 1

        # Skip excluded files
        if is_excluded_file(py_file):
            excluded_files += 1
            print(f"[SKIP] {py_file.relative_to(SRC_ROOT)} (excluded)")
            continue

        # Extract module name
        module_name = extract_module_name_from_path(py_file, SRC_ROOT)
        if not module_name:
            print(f"[WARN] Could not extract module name: {py_file}")
            continue

        # Search for imports
        print(f"[CHECK] {module_name} ({py_file.relative_to(SRC_ROOT)})")

        importers = find_files_importing(module_name, SRC_ROOT, EXCLUDE_DIRS)

        # Filter out self-imports (file importing itself)
        importers = [f for f in importers if f != py_file]

        if len(importers) == 0:
            # No imports found - potentially unused
            confidence = _determine_confidence(py_file, module_name)

            findings.append({
                'item': str(py_file.relative_to(SRC_ROOT)),
                'location': str(py_file.relative_to(SRC_ROOT)),
                'confidence': confidence,
                'reason': 'No imports found in codebase',
                'details': f"Module name: {module_name}"
            })

            print(f"   [WARN] No imports found (confidence: {confidence})")
        else:
            print(f"   [OK] Used by {len(importers)} file(s)")

    # Print summary
    print(f"\n[SUMMARY]")
    print(f"   Total files analyzed: {total_files}")
    print(f"   Excluded files: {excluded_files}")
    print(f"   Potentially unused: {len(findings)}")

    return findings, total_files, excluded_files


def _determine_confidence(file_path: Path, module_name: str) -> str:
    """
    Determine confidence level for unused file.

    High confidence: Clearly unused
    Medium confidence: Needs manual verification
    Low confidence: Likely used indirectly

    Args:
        file_path: Path to Python file
        module_name: Extracted module name

    Returns:
        'high' | 'medium' | 'low'
    """
    file_name = file_path.name
    file_content = None

    # Read file content for analysis
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
    except Exception as e:
        print(f"[WARN] Could not read {file_path}: {e}")
        return 'low'

    # Low confidence cases (likely used indirectly)

    # 1. Files in tests/ (may not be imported)
    if 'test' in str(file_path).lower():
        return 'low'

    # 2. Files with FastAPI routes (used via decorators)
    if '@router.' in file_content or '@app.' in file_content:
        return 'low'

    # 3. Files with CLI commands (argparse, click)
    if 'argparse' in file_content or 'click' in file_content:
        return 'low'

    # 4. Files that look like migrations or scripts
    if 'migration' in file_name or 'script' in file_name:
        return 'low'

    # 5. Files with __all__ export (package interface)
    if '__all__' in file_content:
        return 'medium'

    # Medium confidence cases (needs verification)

    # 1. Files in infrastructure/ (may be dynamically loaded)
    if 'infrastructure' in str(file_path):
        return 'medium'

    # 2. Files with classes (may be imported dynamically)
    if 'class ' in file_content:
        return 'medium'

    # 3. Files in domains/ with models (ORM models auto-discovered)
    if 'domains' in str(file_path) and 'models.py' in file_name:
        return 'medium'

    # High confidence cases (likely unused)

    # 1. Utility files with only functions
    if 'utils' in str(file_path) and 'def ' in file_content:
        return 'high'

    # 2. Files with very few lines (< 50)
    if file_content.count('\n') < 50:
        return 'high'

    # Default: medium confidence
    return 'medium'


def generate_report(findings, total_files, excluded_files):
    """Generate markdown report."""
    additional_sections = {
        "Statistics": f"""
- **Total Python files**: {total_files}
- **Excluded files**: {excluded_files} ({', '.join(EXCLUDE_FILES)})
- **Files analyzed**: {total_files - excluded_files}
- **Potentially unused**: {len(findings)}

### Breakdown by Confidence

""" + _generate_confidence_breakdown(findings) + """

---

## Manual Verifications Required

For each candidate file, check:

1. **Dynamic imports**: `importlib.import_module()`, `__import__()`
2. **Entry points**: Files run directly (scripts)
3. **Decorators**: `@router.get`, `@app.on_event`, etc.
4. **Auto-discovery**: Alembic migrations, SQLAlchemy models
5. **Documentation references**: Mentioned in docs/
6. **Configuration**: Referenced in settings, config files

### Special Cases

#### FastAPI Routes
```python
# File may appear unused but is used via decorator
@router.get("/endpoint")
async def handler():
    ...
```
-> **Do NOT delete**

#### Alembic Migrations
Files in `alembic/versions/` are referenced by Alembic, not imported directly.
-> **Do NOT delete**

#### SQLAlchemy Models
ORM models in `domains/*/models.py` may be auto-discovered.
-> **Verify carefully**

---

## Next Steps

1. [OK] Manual review of each finding
2. Pending - Classification: SAFE_TO_DELETE / KEEP / UNCERTAIN
3. Pending - For SAFE_TO_DELETE:
   - Create git branch
   - Delete file
   - Run full tests
   - Verify app starts
   - Commit if success, rollback if failure
""",
        "Notes": """
- `__init__.py` and `main.py` files are automatically excluded
- Alembic migrations are NOT imported (normal)
- FastAPI routes may appear unused (decorators)
- Always verify tests before deletion
"""
    }

    generate_finding_report(
        title="Potentially Unused Python Files",
        findings=findings,
        output_path=OUTPUT_FILE,
        script_name="analyze_unused_files.py",
        additional_sections=additional_sections
    )


def _generate_confidence_breakdown(findings):
    """Generate confidence breakdown table."""
    confidence_counts = {'high': 0, 'medium': 0, 'low': 0}
    for finding in findings:
        conf = finding.get('confidence', 'unknown')
        if conf in confidence_counts:
            confidence_counts[conf] += 1

    lines = []
    for conf, count in confidence_counts.items():
        emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(conf, '⚪')
        lines.append(f"- **{emoji} Confidence {conf}**: {count} file(s)")

    return "\n".join(lines)


if __name__ == "__main__":
    print("=" * 60)
    print("  Unused Python Files Analysis - LIA")
    print("=" * 60)
    print()

    try:
        findings, total_files, excluded_files = analyze_unused_files()
        generate_report(findings, total_files, excluded_files)

        print(f"\n[SUCCESS] Analysis complete!")
        print(f"   Report: {OUTPUT_FILE}")
        print(f"   Findings: {len(findings)}")
        print(f"\n[NEXT] Review findings manually in {OUTPUT_FILE}")

    except KeyboardInterrupt:
        print("\n\n[WARN] Analysis interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
