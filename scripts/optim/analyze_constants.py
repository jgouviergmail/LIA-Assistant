#!/usr/bin/env python3
"""
Audit Constants Usage.

Strategy:
1. Parse src/core/constants.py
2. Extract all UPPER_CASE constants
3. For each constant, grep in src/ (exclude constants.py)
4. Count usages
5. Flag:
   - 0 usages: UNUSED
   - 1 usage: BARELY_USED
   - 2+ usages: OK

Usage:
    python scripts/optim/analyze_constants.py

Output:
    docs/optim/03_UNUSED_CONSTANTS.md

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-14
"""

import sys
from pathlib import Path

# Add utils to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "utils"))

from ast_parser import parse_file, extract_constants
from grep_helper import grep_in_directory
from report_generator import generate_finding_report


# Configuration
CONSTANTS_FILE = Path("apps/api/src/core/constants.py")
SRC_ROOT = Path("apps/api/src")
OUTPUT_FILE = Path("docs/optim/03_UNUSED_CONSTANTS.md")

EXCLUDE_DIRS = ["__pycache__", ".venv", ".git"]


def analyze_constants():
    """
    Main analysis function.

    Returns:
        Tuple of (findings, stats)
    """
    print("[*] Analyzing constants usage...")
    print(f"   Constants file: {CONSTANTS_FILE}")
    print(f"   Output: {OUTPUT_FILE}\n")

    if not CONSTANTS_FILE.exists():
        print(f"[ERROR] Constants file not found: {CONSTANTS_FILE}")
        sys.exit(1)

    findings = []
    stats = {
        'total_constants': 0,
        'unused': 0,
        'barely_used': 0,
        'well_used': 0,
    }

    # Parse constants file
    tree = parse_file(CONSTANTS_FILE)
    if not tree:
        print("[ERROR] Failed to parse constants file")
        sys.exit(1)

    # Extract constants
    constants = extract_constants(tree, str(CONSTANTS_FILE))
    stats['total_constants'] = len(constants)

    print(f"[SUMMARY] Found {len(constants)} constants\n")

    # Analyze each constant
    for const in constants:
        const_name = const['name']
        print(f"[CHECK] Checking: {const_name}")

        # Search for usages (exclude constants.py itself)
        usages = grep_in_directory(
            const_name,
            SRC_ROOT,
            extensions=['.py'],
            exclude_dirs=EXCLUDE_DIRS,
            case_sensitive=True,
            regex=False
        )

        # Filter out definition in constants.py
        usages_filtered = [
            u for u in usages
            if not (u['file'].endswith('constants.py') and u['line'] == const['line'])
        ]

        usage_count = len(usages_filtered)

        # Classify
        if usage_count == 0:
            # UNUSED
            stats['unused'] += 1
            findings.append({
                'item': const_name,
                'location': f"constants.py:{const['line']}",
                'confidence': 'high',
                'reason': f'0 usages found',
                'details': f"Value: {const['value']}"
            })
            print(f"   [WARN]  UNUSED (0 usages)")

        elif usage_count == 1:
            # BARELY_USED
            stats['barely_used'] += 1
            usage_file = usages_filtered[0]['file']
            findings.append({
                'item': const_name,
                'location': f"constants.py:{const['line']}",
                'confidence': 'medium',
                'reason': f'Only 1 usage found',
                'details': f"Used in: {usage_file}. Consider inlining."
            })
            print(f"   [WARN]  BARELY_USED (1 usage in {usage_file})")

        else:
            # WELL_USED
            stats['well_used'] += 1
            print(f"   [OK] OK ({usage_count} usages)")

    # Print summary
    print(f"\n[SUMMARY] Summary:")
    print(f"   Total constants: {stats['total_constants']}")
    print(f"   Unused (0 usages): {stats['unused']}")
    print(f"   Barely used (1 usage): {stats['barely_used']}")
    print(f"   Well used (2+ usages): {stats['well_used']}")
    print(f"   Findings: {len(findings)}")

    return findings, stats


def generate_report(findings, stats):
    """Generate markdown report."""
    additional_sections = {
        "[SUMMARY] Statistics": f"""
- **Total constants**: {stats['total_constants']}
- **Unused (0 usages)**: {stats['unused']}
- **Barely used (1 usage)**: {stats['barely_used']}
- **Well used (2+ usages)**: {stats['well_used']}

### Recommendations

#### Unused Constants (0 usages)
-> **DELETE** after manual verification

#### Barely Used Constants (1 usage)
-> **Consider inlining**:
- If simple value (string, number) -> Replace with literal
- If complex or semantic value -> Keep as constant

---

## [WARN] Manual Verifications

For each candidate constant:

### 1. Check Usage in config.py
```python
# Constant may be used as a default
setting: str = Field(default=MY_CONSTANT)
```
→ Grep for usage in `Field(default=`

### 2. Check Usage as Dict Key
```python
# Constant may be a dictionary key
config[MY_CONSTANT] = value
```
→ Grep for `[MY_CONSTANT]`

### 3. Check Usage via String
```python
# Reference by variable name (rare)
getattr(obj, "MY_CONSTANT")
```
→ Grep for `"MY_CONSTANT"` (with quotes)

### 4. Check Export __init__.py
```python
# Constant exported in public API
from .constants import MY_CONSTANT
__all__ = ["MY_CONSTANT"]
```
→ Check if in `__all__`

### 5. Check Documentation References
- Mentioned in README.md
- Mentioned in docstrings
- Used in examples

---

## Decision: Keep or Delete?

### [OK] KEEP if:
- Used 2+ times (reusability)
- Exported in __all__ (public API)
- Semantically important (avoids magic number/string)
- Referenced in documentation

### [ERROR] DELETE if:
- 0 usages AND manual verifications pass
- 1 usage AND simple value (inline it)

### [WARN] IF IN DOUBT -> KEEP

---

## Next Steps

1. [OK] Manual review of each finding
2. Pending - For unused constants:
   - Check indirect usages (above)
   - If truly unused -> Delete
   - Run tests
   - Commit
3. Pending - For barely used constants:
   - Evaluate if inlining is appropriate
   - If yes -> Inline
   - If no -> Keep
""",
        "Notes": """
- Constants with 0 usages are candidates for deletion
- Constants with 1 usage can be inlined (depending on context)
- Always check indirect usages before deletion
- Semantic constants (avoiding magic values) should be kept even with 1 usage
"""
    }

    generate_finding_report(
        title="Constants Audit",
        findings=findings,
        output_path=OUTPUT_FILE,
        script_name="analyze_constants.py",
        additional_sections=additional_sections
    )


if __name__ == "__main__":
    print("=" * 60)
    print("  Constants Audit - LIA")
    print("=" * 60)
    print()

    try:
        findings, stats = analyze_constants()
        generate_report(findings, stats)

        print(f"\n[OK] Analysis complete!")
        print(f"   Report: {OUTPUT_FILE}")
        print(f"   Findings: {len(findings)}")
        print(f"\n[NEXT] Next: Review findings manually in {OUTPUT_FILE}")

    except KeyboardInterrupt:
        print("\n\n[WARN]  Analysis interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
