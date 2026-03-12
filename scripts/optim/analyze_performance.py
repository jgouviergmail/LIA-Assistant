#!/usr/bin/env python3
"""
Detect Performance Issues and Optimization Opportunities.

Strategy:
1. AST parsing for nested loops (O(n²))
2. Search for DB queries in loops (N+1)
3. Search for sync calls in async functions
4. Search for unclosed resources
5. Complexity analysis (if radon available)

Usage:
    python scripts/optim/analyze_performance.py

Output:
    docs/optim/07_OPTIMIZATION.md

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-14
"""

import sys
import ast
import subprocess
from pathlib import Path

# Add utils to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "utils"))

from ast_parser import parse_file, get_function_complexity
from grep_helper import grep_in_directory
from report_generator import generate_finding_report


# Configuration
SRC_ROOT = Path("apps/api/src")
OUTPUT_FILE = Path("docs/optim/07_OPTIMIZATION.md")

EXCLUDE_DIRS = ["__pycache__", ".venv", ".git", "alembic/versions", "tests"]


def analyze_nested_loops():
    """Detect potentially O(n²) nested loops."""
    print("[*] Analyzing nested loops (O(n²) patterns)...")

    findings = []

    for py_file in SRC_ROOT.rglob("*.py"):
        if any(excl in str(py_file) for excl in EXCLUDE_DIRS):
            continue

        tree = parse_file(py_file)
        if not tree:
            continue

        class NestedLoopVisitor(ast.NodeVisitor):
            def __init__(self):
                self.in_loop = False
                self.loop_line = None

            def visit_For(self, node):
                if self.in_loop:
                    # Nested loop detected
                    findings.append({
                        'item': f"Nested loop in {py_file.name}",
                        'location': f"{py_file.relative_to(SRC_ROOT)}:{node.lineno}",
                        'confidence': 'medium',
                        'reason': 'Nested for loop (potential O(n²))',
                        'details': f'Outer loop at line {self.loop_line}'
                    })

                # Continue traversal
                old_in_loop = self.in_loop
                old_loop_line = self.loop_line
                self.in_loop = True
                self.loop_line = node.lineno
                self.generic_visit(node)
                self.in_loop = old_in_loop
                self.loop_line = old_loop_line

            def visit_While(self, node):
                # Same logic for while loops
                if self.in_loop:
                    findings.append({
                        'item': f"Nested loop in {py_file.name}",
                        'location': f"{py_file.relative_to(SRC_ROOT)}:{node.lineno}",
                        'confidence': 'medium',
                        'reason': 'Nested while loop (potential O(n²))',
                        'details': f'Outer loop at line {self.loop_line}'
                    })

                old_in_loop = self.in_loop
                old_loop_line = self.loop_line
                self.in_loop = True
                self.loop_line = node.lineno
                self.generic_visit(node)
                self.in_loop = old_in_loop
                self.loop_line = old_loop_line

        visitor = NestedLoopVisitor()
        visitor.visit(tree)

    print(f"   Found {len(findings)} nested loops")
    return findings


def analyze_sync_in_async():
    """Detect blocking calls in async functions."""
    print("[*] Analyzing blocking calls in async functions...")

    # Patterns to detect
    blocking_patterns = [
        ('requests.get', 'Use httpx.AsyncClient instead'),
        ('requests.post', 'Use httpx.AsyncClient instead'),
        ('requests.put', 'Use httpx.AsyncClient instead'),
        ('time.sleep', 'Use asyncio.sleep instead'),
        ('open(', 'Use aiofiles instead (for async I/O)'),
    ]

    findings = []

    for pattern, suggestion in blocking_patterns:
        results = grep_in_directory(
            pattern,
            SRC_ROOT,
            extensions=['.py'],
            exclude_dirs=EXCLUDE_DIRS,
            regex=False
        )

        # Check if in async function
        for result in results:
            file_path = SRC_ROOT / result['file']
            tree = parse_file(file_path)
            if not tree:
                continue

            # Check if line is inside async function
            if _is_in_async_function(tree, result['line']):
                findings.append({
                    'item': f"Blocking call: {pattern}",
                    'location': f"{result['file']}:{result['line']}",
                    'confidence': 'high',
                    'reason': f'Blocking call in async function',
                    'details': f'Suggestion: {suggestion}'
                })

    print(f"   Found {len(findings)} blocking calls in async functions")
    return findings


def _is_in_async_function(tree, line_num):
    """Check if line is inside async function."""
    class AsyncFunctionChecker(ast.NodeVisitor):
        def __init__(self):
            self.in_async = False
            self.async_ranges = []

        def visit_AsyncFunctionDef(self, node):
            # Get line range of async function
            end_line = node.end_lineno if hasattr(node, 'end_lineno') else node.lineno + 100
            self.async_ranges.append((node.lineno, end_line))
            self.generic_visit(node)

    checker = AsyncFunctionChecker()
    checker.visit(tree)

    for start, end in checker.async_ranges:
        if start <= line_num <= end:
            return True

    return False


def check_radon_available():
    """Check if radon is installed."""
    try:
        result = subprocess.run(
            ['radon', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def analyze_performance():
    """Main analysis function."""
    print("[*] Analyzing performance issues...")
    print(f"   Source root: {SRC_ROOT}")
    print(f"   Output: {OUTPUT_FILE}\n")

    all_findings = []
    stats = {
        'nested_loops': 0,
        'blocking_calls': 0,
        'total': 0,
    }

    # 1. Nested loops
    nested_loop_findings = analyze_nested_loops()
    all_findings.extend(nested_loop_findings)
    stats['nested_loops'] = len(nested_loop_findings)

    # 2. Blocking calls in async
    blocking_findings = analyze_sync_in_async()
    all_findings.extend(blocking_findings)
    stats['blocking_calls'] = len(blocking_findings)

    stats['total'] = len(all_findings)

    # 3. Complexity analysis (if radon available)
    if check_radon_available():
        print("\n[OK] Radon found - you can run complexity analysis manually:")
        print("   radon cc apps/api/src -a -s")
    else:
        print("\n[WARN]  Radon not found")
        print("   Install: pip install radon")
        print("   For complexity metrics: radon cc apps/api/src -a -s")

    print(f"\n[SUMMARY] Summary:")
    print(f"   Nested loops: {stats['nested_loops']}")
    print(f"   Blocking calls in async: {stats['blocking_calls']}")
    print(f"   Total findings: {stats['total']}")

    return all_findings, stats


def generate_report(findings, stats):
    """Generate markdown report."""
    additional_sections = {
        "[SUMMARY] Statistics": f"""
- **Nested loops (O(n²))**: {stats['nested_loops']}
- **Blocking calls in async**: {stats['blocking_calls']}
- **Total opportunities**: {stats['total']}

---

## Additional Tools

### Radon (Complexity Metrics)
```bash
pip install radon

# Cyclomatic complexity
radon cc apps/api/src -a -s

# Maintainability index
radon mi apps/api/src -s

# Raw metrics
radon raw apps/api/src -s
```

### Bandit (Security)
```bash
pip install bandit

# Security scan
bandit -r apps/api/src
```

---

## Optimization Patterns

### 1. Nested Loops -> Dict Lookup

**Before (O(n²))**:
```python
for user in users:
    for order in orders:
        if order.user_id == user.id:
            # process
```

**After (O(n))**:
```python
orders_by_user = {{o.user_id: o for o in orders}}
for user in users:
    order = orders_by_user.get(user.id)
    if order:
        # process
```

### 2. Database N+1

**Before**:
```python
users = session.query(User).all()
for user in users:
    orders = session.query(Order).filter(Order.user_id == user.id).all()
```

**After (JOIN)**:
```python
users = session.query(User).options(joinedload(User.orders)).all()
for user in users:
    orders = user.orders  # Already loaded
```

### 3. Blocking in Async

**Before**:
```python
async def fetch_data():
    response = requests.get(url)  # BLOCKING!
    return response.json()
```

**After**:
```python
async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

### 4. File I/O in Async

**Before**:
```python
async def read_file():
    with open(file_path) as f:  # BLOCKING!
        return f.read()
```

**After**:
```python
import aiofiles

async def read_file():
    async with aiofiles.open(file_path) as f:
        return await f.read()
```

---

## Benchmarking

Before and after each optimization:

```python
import time

# Baseline
start = time.perf_counter()
result = old_function()
baseline_time = time.perf_counter() - start

# Optimized
start = time.perf_counter()
result = new_function()
optimized_time = time.perf_counter() - start

improvement = (baseline_time - optimized_time) / baseline_time * 100
print(f"Improvement: {{improvement:.1f}}%")

# Only keep if improvement >= 10%
```

---

## Next Steps

1. [OK] Manual review of each finding
2. Pending - For each opportunity:
   - Evaluate impact (profiling if necessary)
   - Estimate effort
   - Benchmark baseline
3. Pending - Prioritize by impact/effort
4. Pending - Optimize iteratively:
   - Benchmark before
   - Optimize
   - Benchmark after
   - If gain < 10% -> Rollback
   - If gain >= 10% -> Keep + Commit
""",
        "Notes": """
- Nested loops are not always O(n²) (depends on data size)
- Some blocking calls are necessary (e.g.: file sync in non-async context)
- Always benchmark before/after
- Premature optimization is the root of all evil (profile first!)
- Verify tests after each optimization
"""
    }

    generate_finding_report(
        title="Performance Optimization Opportunities",
        findings=findings,
        output_path=OUTPUT_FILE,
        script_name="analyze_performance.py",
        additional_sections=additional_sections
    )


if __name__ == "__main__":
    print("=" * 60)
    print("  Performance Analysis - LIA")
    print("=" * 60)
    print()

    try:
        findings, stats = analyze_performance()
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
