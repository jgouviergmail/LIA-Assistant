#!/usr/bin/env python3
"""
Detect Magic Strings/Numbers That Should Be Constants.

Strategy:
1. Grep for string literals: "..."
2. Grep for numeric literals: \\b[0-9]{2,}\\b
3. Filter:
   - Exclude tests/
   - Exclude comments
   - Keep only repeated values (3+ occurrences)
4. Check if already in constants.py
5. Recommend centralization

Usage:
    python scripts/optim/analyze_magic_values.py

Output:
    docs/optim/08_MISSING_CONSTANTS.md

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-14
"""

import sys
import re
from pathlib import Path
from collections import Counter

# Add utils to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "utils"))

from grep_helper import grep_in_directory
from report_generator import generate_finding_report


# Configuration
SRC_ROOT = Path("apps/api/src")
CONSTANTS_FILE = Path("apps/api/src/core/constants.py")
OUTPUT_FILE = Path("docs/optim/08_MISSING_CONSTANTS.md")

# Minimum occurrences to flag
MIN_OCCURRENCES = 3

# Trivial numbers to exclude
TRIVIAL_NUMBERS = [0, 1, 2, 10, 100, 1000]

EXCLUDE_DIRS = ["__pycache__", ".venv", ".git", "alembic/versions"]


def analyze_magic_strings():
    """Find repeated string literals."""
    print("[*] Analyzing magic strings...")

    # Find all string literals
    # Pattern: "..." or '...' but not docstrings
    results = grep_in_directory(
        r'["\'][^"\']{3,}["\']',  # Strings with 3+ chars
        SRC_ROOT,
        extensions=['.py'],
        exclude_dirs=EXCLUDE_DIRS + ['tests'],  # Exclude tests
        regex=True
    )

    # Extract and count strings
    string_counter = Counter()
    string_locations = {}

    for result in results:
        # Extract string value (remove quotes)
        match = re.search(r'["\']([^"\']+)["\']', result['context'])
        if match:
            string_value = match.group(1)

            # Filter out:
            # 1. Very long strings (> 50 chars, likely messages/queries)
            if len(string_value) > 50:
                continue

            # 2. URLs, paths with /
            if '://' in string_value or string_value.count('/') > 2:
                continue

            # 3. SQL queries
            if 'SELECT' in string_value.upper() or 'INSERT' in string_value.upper():
                continue

            # 4. Log messages (start with uppercase + space)
            if re.match(r'^[A-Z][a-z]+\s', string_value):
                continue

            string_counter[string_value] += 1

            if string_value not in string_locations:
                string_locations[string_value] = []
            string_locations[string_value].append(f"{result['file']}:{result['line']}")

    # Filter by minimum occurrences
    repeated_strings = {k: v for k, v in string_counter.items() if v >= MIN_OCCURRENCES}

    print(f"   Found {len(repeated_strings)} repeated strings (>={MIN_OCCURRENCES} occurrences)")

    return repeated_strings, string_locations


def analyze_magic_numbers():
    """Find repeated numeric literals."""
    print("[*] Analyzing magic numbers...")

    # Find all numeric literals (2+ digits)
    results = grep_in_directory(
        r'\b[0-9]{2,}\b',
        SRC_ROOT,
        extensions=['.py'],
        exclude_dirs=EXCLUDE_DIRS + ['tests'],
        regex=True
    )

    # Extract and count numbers
    number_counter = Counter()
    number_locations = {}

    for result in results:
        # Extract number
        match = re.search(r'\b([0-9]+)\b', result['context'])
        if match:
            number_value = int(match.group(1))

            # Filter trivial numbers
            if number_value in TRIVIAL_NUMBERS:
                continue

            number_counter[number_value] += 1

            if number_value not in number_locations:
                number_locations[number_value] = []
            number_locations[number_value].append(f"{result['file']}:{result['line']}")

    # Filter by minimum occurrences
    repeated_numbers = {k: v for k, v in number_counter.items() if v >= MIN_OCCURRENCES}

    print(f"   Found {len(repeated_numbers)} repeated numbers (>={MIN_OCCURRENCES} occurrences)")

    return repeated_numbers, number_locations


def check_if_constant_exists(value):
    """Check if value already defined in constants.py."""
    if not CONSTANTS_FILE.exists():
        return False

    try:
        with open(CONSTANTS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            # Check for value (as string representation)
            return repr(value) in content or str(value) in content
    except:
        return False


def analyze_magic_values():
    """Main analysis."""
    print("[*] Analyzing magic values (strings & numbers)...")
    print(f"   Source root: {SRC_ROOT}")
    print(f"   Output: {OUTPUT_FILE}\n")

    findings = []
    stats = {
        'magic_strings': 0,
        'magic_numbers': 0,
        'already_constant': 0,
        'to_centralize': 0,
    }

    # Analyze strings
    repeated_strings, string_locations = analyze_magic_strings()
    stats['magic_strings'] = len(repeated_strings)

    for string_value, count in sorted(repeated_strings.items(), key=lambda x: -x[1]):
        in_constants = check_if_constant_exists(string_value)

        if in_constants:
            stats['already_constant'] += 1
        else:
            stats['to_centralize'] += 1
            locations_str = ', '.join(string_locations[string_value][:3])
            if len(string_locations[string_value]) > 3:
                locations_str += f" (+{len(string_locations[string_value]) - 3} more)"

            findings.append({
                'item': f'"{string_value}"',
                'location': locations_str,
                'confidence': 'high' if count >= 5 else 'medium',
                'reason': f'{count} occurrences (magic string)',
                'details': f'Proposed constant name: {_suggest_constant_name(string_value)}'
            })

    # Analyze numbers
    repeated_numbers, number_locations = analyze_magic_numbers()
    stats['magic_numbers'] = len(repeated_numbers)

    for number_value, count in sorted(repeated_numbers.items(), key=lambda x: -x[1]):
        in_constants = check_if_constant_exists(number_value)

        if in_constants:
            stats['already_constant'] += 1
        else:
            stats['to_centralize'] += 1
            locations_str = ', '.join(number_locations[number_value][:3])
            if len(number_locations[number_value]) > 3:
                locations_str += f" (+{len(number_locations[number_value]) - 3} more)"

            findings.append({
                'item': str(number_value),
                'location': locations_str,
                'confidence': 'high' if count >= 5 else 'medium',
                'reason': f'{count} occurrences (magic number)',
                'details': f'Consider creating constant with semantic name'
            })

    print(f"\n[SUMMARY] Summary:")
    print(f"   Magic strings found: {stats['magic_strings']}")
    print(f"   Magic numbers found: {stats['magic_numbers']}")
    print(f"   Already constants: {stats['already_constant']}")
    print(f"   To centralize: {stats['to_centralize']}")
    print(f"   Findings: {len(findings)}")

    return findings, stats


def _suggest_constant_name(value):
    """Suggest a constant name for a value."""
    # Simple heuristic
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', value.upper())
    clean = re.sub(r'_+', '_', clean).strip('_')

    if len(clean) > 30:
        clean = clean[:30]

    return clean or "CONSTANT_NAME"


def generate_report(findings, stats):
    """Generate markdown report."""
    additional_sections = {
        "[SUMMARY] Statistics": f"""
- **Magic strings detected**: {stats['magic_strings']}
- **Magic numbers detected**: {stats['magic_numbers']}
- **Already in constants.py**: {stats['already_constant']}
- **To centralize**: {stats['to_centralize']}

### Detection Criteria

- **Threshold**: Values repeated >= {MIN_OCCURRENCES} times
- **Exclusions**:
  - Strings > 50 characters (messages, queries)
  - URLs and paths
  - SQL queries
  - Log messages
  - Trivial numbers: {TRIVIAL_NUMBERS}
  - Test files

---

## Recommendations

### Magic Strings
For each repeated string, create a constant with a semantic name:

```python
# Before
if status == "completed":
    ...
if result == "completed":
    ...

# After
STATUS_COMPLETED = "completed"

if status == STATUS_COMPLETED:
    ...
if result == STATUS_COMPLETED:
    ...
```

### Magic Numbers
For each repeated number, create an explicit constant:

```python
# Before
timeout = 300
cache_ttl = 300

# After
DEFAULT_TIMEOUT_SECONDS = 300

timeout = DEFAULT_TIMEOUT_SECONDS
cache_ttl = DEFAULT_TIMEOUT_SECONDS
```

---

## [WARN] Manual Evaluation

For each magic value candidate:

### 1. Is It Semantically Significant?
- **Yes** -> Create constant (e.g.: "admin", "default", status codes)
- **No** -> Keep literal (e.g.: "id", "name", obvious values)

### 2. Is It Truly Duplicated?
- **Same value, same meaning** -> Centralize
- **Same value, different meanings** -> Keep separate

### 3. Usage Context
- **Configuration** -> Centralize in constants.py
- **Business logic** -> Centralize with business-domain name
- **Pure technical** -> Can remain local if obvious

---

## Next Steps

1. [OK] Manual review of each finding
2. Pending - For each magic value to centralize:
   - Choose appropriate semantic name
   - Add constant in `src/core/constants.py`
   - Replace all usages
   - Run tests
   - Commit
3. Pending - For magic values to keep local:
   - Document why (comment)
   - Mark as acceptable
""",
        "Notes": """
- Strings > 50 characters are excluded (messages, queries)
- Trivial numbers (0, 1, 2, 10, 100, 1000) are excluded
- Tests are excluded from the analysis
- Some repeated values may be intentional (e.g.: "id" appears everywhere but doesn't need to be a constant)
"""
    }

    generate_finding_report(
        title="Magic Strings/Numbers to Centralize",
        findings=findings,
        output_path=OUTPUT_FILE,
        script_name="analyze_magic_values.py",
        additional_sections=additional_sections
    )


if __name__ == "__main__":
    print("=" * 60)
    print("  Magic Values Analysis - LIA")
    print("=" * 60)
    print()

    try:
        findings, stats = analyze_magic_values()
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
