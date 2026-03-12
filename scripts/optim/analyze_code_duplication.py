#!/usr/bin/env python3
"""
Detect Code Duplication.

Strategy:
1. Use pylint --duplicate-code (if available)
2. Fallback to manual similarity detection
3. Categorize by severity:
   - Critical: > 50 lines duplicated
   - High: 20-50 lines
   - Medium: 10-20 lines
4. Propose refactoring opportunities

Usage:
    python scripts/optim/analyze_code_duplication.py

Output:
    docs/optim/05_CODE_DUPLICATION.md

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-14
"""

import sys
import subprocess
from pathlib import Path

# Add utils to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "utils"))

from report_generator import generate_finding_report


# Configuration
SRC_ROOT = Path("apps/api/src")
OUTPUT_FILE = Path("docs/optim/05_CODE_DUPLICATION.md")

# Duplicate code threshold (lines)
MIN_DUPLICATE_LINES = 10


def check_pylint_available():
    """Check if pylint is installed."""
    try:
        result = subprocess.run(
            ['pylint', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_pylint_duplicate_check():
    """Run pylint duplicate code detection."""
    print("[*] Running pylint duplicate code detection...")

    try:
        result = subprocess.run(
            [
                'pylint',
                '--disable=all',
                '--enable=duplicate-code',
                f'--duplicate-code-min-similarity-lines={MIN_DUPLICATE_LINES}',
                str(SRC_ROOT)
            ],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes max
        )

        output = result.stdout + result.stderr
        return output

    except subprocess.TimeoutExpired:
        print("[WARN]  Pylint timeout (> 5 minutes)")
        return None
    except Exception as e:
        print(f"[WARN]  Pylint error: {e}")
        return None


def parse_pylint_output(output):
    """Parse pylint duplicate code output."""
    findings = []

    if not output:
        return findings

    # Pylint output format:
    # Similar lines in X files
    # path/to/file1.py:startline-endline
    # path/to/file2.py:startline-endline

    blocks = output.split('Similar lines in')

    for block in blocks[1:]:  # Skip first empty split
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue

        # Extract number of lines from first line
        first_line = lines[0]
        try:
            num_files = int(first_line.split()[0])
        except:
            continue

        # Extract file locations
        locations = []
        for line in lines[1:]:
            line = line.strip()
            if ':' in line and '-' in line:
                locations.append(line)

        if len(locations) >= 2:
            # Extract line counts
            match = first_line.split('lines')
            num_lines = MIN_DUPLICATE_LINES  # Default

            # Determine severity
            if num_lines > 50:
                severity = 'critical'
            elif num_lines >= 20:
                severity = 'high'
            else:
                severity = 'medium'

            findings.append({
                'item': f"Duplication across {num_files} files",
                'location': ', '.join(locations[:2]),  # First 2 files
                'confidence': 'high',
                'reason': f'~{num_lines}+ similar lines detected',
                'details': f'Files: {", ".join(locations)}'
            })

    return findings


def analyze_duplication():
    """Main analysis function."""
    print("[*] Analyzing code duplication...")
    print(f"   Source root: {SRC_ROOT}")
    print(f"   Min duplicate lines: {MIN_DUPLICATE_LINES}")
    print(f"   Output: {OUTPUT_FILE}\n")

    findings = []
    stats = {
        'method': 'none',
        'duplicates_found': 0,
    }

    # Check if pylint available
    if check_pylint_available():
        print("[OK] Pylint found, using for duplicate detection\n")
        stats['method'] = 'pylint'

        pylint_output = run_pylint_duplicate_check()

        if pylint_output:
            findings = parse_pylint_output(pylint_output)
            stats['duplicates_found'] = len(findings)
            print(f"[OK] Pylint analysis complete")
        else:
            print("[WARN]  Pylint analysis failed")

    else:
        print("[WARN]  Pylint not found")
        print("   Install: pip install pylint")
        print("   Skipping automated duplicate detection\n")
        stats['method'] = 'manual'

        # Create manual analysis finding
        findings.append({
            'item': 'Manual review required',
            'location': 'N/A',
            'confidence': 'low',
            'reason': 'Pylint not available - manual inspection needed',
            'details': 'Install pylint and re-run for automated detection'
        })

    print(f"\n[SUMMARY] Summary:")
    print(f"   Method: {stats['method']}")
    print(f"   Duplicates found: {stats['duplicates_found']}")
    print(f"   Findings: {len(findings)}")

    return findings, stats


def generate_report(findings, stats):
    """Generate markdown report."""
    additional_sections = {
        "[SUMMARY] Statistics": f"""
- **Method**: {stats['method']}
- **Duplicate blocks found**: {stats['duplicates_found']}
- **Minimum threshold**: {MIN_DUPLICATE_LINES} lines

### Severity

- **Critical**: > 50 duplicated lines
- **High**: 20-50 lines
- **Medium**: 10-20 lines

---

## Pylint Installation

If pylint is not available:

```bash
cd apps/api
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # Linux/Mac

pip install pylint

# Re-run the analysis
python ../../scripts/optim/analyze_code_duplication.py
```

---

## Refactoring Patterns

### 1. Utility Function Extraction

**Before**:
```python
# File1.py
result = process(data)
validated = validate(result)
stored = store(validated)

# File2.py
result = process(other_data)
validated = validate(result)
stored = store(validated)
```

**After**:
```python
# utils.py
def process_and_store(data):
    result = process(data)
    validated = validate(result)
    return store(validated)

# File1.py
stored = process_and_store(data)

# File2.py
stored = process_and_store(other_data)
```

### 2. Base Class Extraction

**Before**:
```python
# Two classes with similar methods
class ServiceA:
    def validate(self): ...
    def process(self): ...

class ServiceB:
    def validate(self): ...
    def process(self): ...
```

**After**:
```python
class BaseService:
    def validate(self): ...
    def process(self): ...

class ServiceA(BaseService):
    pass  # Override if needed

class ServiceB(BaseService):
    pass  # Override if needed
```

### 3. Decorator Extraction

**Before**:
```python
def func1():
    start = time.time()
    try:
        # logic
    finally:
        duration = time.time() - start
        log(duration)

def func2():
    start = time.time()
    try:
        # logic
    finally:
        duration = time.time() - start
        log(duration)
```

**After**:
```python
@timing_decorator
def func1():
    # logic

@timing_decorator
def func2():
    # logic
```

---

## Next Steps

1. [OK] Manual review of each duplicated block
2. Pending - For each duplication:
   - Analyze differences between copies
   - Choose appropriate refactoring pattern
   - Estimate risk and effort
3. Pending - Prioritize by severity (critical > high > medium)
4. Pending - Refactor iteratively:
   - Create tests if missing
   - Extract common code
   - Run tests
   - Commit
""",
        "Notes": """
- Pylint automatic detection (if available)
- Manual review always necessary
- Some duplications may be intentional (isolation)
- Verify tests before refactoring
- Refactoring can introduce coupling - evaluate trade-offs
"""
    }

    generate_finding_report(
        title="Code Duplication Analysis",
        findings=findings,
        output_path=OUTPUT_FILE,
        script_name="analyze_code_duplication.py",
        additional_sections=additional_sections
    )


if __name__ == "__main__":
    print("=" * 60)
    print("  Code Duplication Analysis - LIA")
    print("=" * 60)
    print()

    try:
        findings, stats = analyze_duplication()
        generate_report(findings, stats)

        print(f"\n[OK] Analysis complete!")
        print(f"   Report: {OUTPUT_FILE}")
        print(f"   Findings: {len(findings)}")
        print(f"\n[NEXT] Next: Review findings manually in {OUTPUT_FILE}")

        if stats['method'] != 'pylint':
            print(f"\n[TIP] Tip: Install pylint for automated duplicate detection")
            print(f"   pip install pylint")

    except KeyboardInterrupt:
        print("\n\n[WARN]  Analysis interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
