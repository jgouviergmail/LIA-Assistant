#!/usr/bin/env python3
"""
Detect Potentially Unused Code (Functions & Classes).

Strategy:
1. Parse all .py files with AST
2. Extract all function/class definitions
3. For each definition, grep for usages
4. Exclude self-reference (the definition itself)
5. Flag if only 1 occurrence (the definition)
6. Manual review for:
   - Decorators (@router.get, @tool, @validator)
   - Abstract methods
   - Callbacks (string references)
   - Reflection/metaclasses

Usage:
    python scripts/optim/analyze_unused_code.py

Output:
    docs/optim/02_UNUSED_CODE.md

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-14
"""

import sys
from pathlib import Path

# Add utils to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "utils"))

from ast_parser import parse_file, extract_functions, extract_classes
from grep_helper import grep_in_directory, find_function_usages
from report_generator import generate_finding_report


# Configuration
SRC_ROOT = Path("apps/api/src")
OUTPUT_FILE = Path("docs/optim/02_UNUSED_CODE.md")

# Exclude directories
EXCLUDE_DIRS = ["__pycache__", ".venv", ".git", "alembic/versions"]

# Special method names to exclude (always used)
SPECIAL_METHODS = [
    '__init__', '__str__', '__repr__', '__eq__', '__hash__',
    '__call__', '__enter__', '__exit__', '__aenter__', '__aexit__',
    '__iter__', '__next__', '__len__', '__getitem__', '__setitem__',
    '__delitem__', '__contains__', '__get__', '__set__', '__delete__',
]


def analyze_unused_code():
    """
    Main analysis function.

    Returns:
        Tuple of (findings, stats)
    """
    print("[*] Analyzing unused code (functions & classes)...")
    print(f"   Source root: {SRC_ROOT}")
    print(f"   Output: {OUTPUT_FILE}\n")

    if not SRC_ROOT.exists():
        print(f"[ERROR] Source root not found: {SRC_ROOT}")
        sys.exit(1)

    findings = []
    stats = {
        'files_analyzed': 0,
        'functions_found': 0,
        'classes_found': 0,
        'functions_unused': 0,
        'classes_unused': 0,
    }

    # Iterate through all Python files
    for py_file in SRC_ROOT.rglob("*.py"):
        # Skip if in excluded directory
        if any(excl in str(py_file) for excl in EXCLUDE_DIRS):
            continue

        stats['files_analyzed'] += 1

        print(f"[CHECK] Analyzing: {py_file.relative_to(SRC_ROOT)}")

        # Parse file
        tree = parse_file(py_file)
        if not tree:
            continue

        # Extract functions
        functions = extract_functions(tree, str(py_file.relative_to(SRC_ROOT)))
        stats['functions_found'] += len(functions)

        for func in functions:
            # Skip special methods
            if func['name'] in SPECIAL_METHODS:
                continue

            # Skip if decorated (likely used via decorator)
            if _has_special_decorator(func['decorators']):
                continue

            # Search for usages
            usages = find_function_usages(func['name'], SRC_ROOT, exclude_definition=True, exclude_dirs=EXCLUDE_DIRS)

            if len(usages) == 0:
                # No usages found
                confidence = _determine_function_confidence(func, py_file)

                findings.append({
                    'item': f"{func['name']}()",
                    'location': f"{func['file']}:{func['line']}",
                    'confidence': confidence,
                    'reason': 'No usages found (excluding definition)',
                    'details': f"Decorators: {', '.join(func['decorators']) if func['decorators'] else 'None'}"
                })

                stats['functions_unused'] += 1
                print(f"   [WARN]  Unused function: {func['name']}() at line {func['line']} (confidence: {confidence})")

        # Extract classes
        classes = extract_classes(tree, str(py_file.relative_to(SRC_ROOT)))
        stats['classes_found'] += len(classes)

        for cls in classes:
            # Skip if decorated (e.g., Pydantic models with decorators)
            if _has_special_decorator(cls['decorators']):
                continue

            # Search for usages (class instantiation or inheritance)
            usages = grep_in_directory(
                cls['name'],
                SRC_ROOT,
                extensions=['.py'],
                exclude_dirs=EXCLUDE_DIRS,
                case_sensitive=True,
                regex=False
            )

            # Filter out the definition itself
            usages_filtered = [u for u in usages if u['line'] != cls['line'] or u['file'] != cls['file']]

            if len(usages_filtered) == 0:
                # No usages found
                confidence = _determine_class_confidence(cls, py_file)

                findings.append({
                    'item': f"class {cls['name']}",
                    'location': f"{cls['file']}:{cls['line']}",
                    'confidence': confidence,
                    'reason': 'No usages found (excluding definition)',
                    'details': f"Bases: {', '.join(cls['bases']) if cls['bases'] else 'None'}, Methods: {len(cls['methods'])}"
                })

                stats['classes_unused'] += 1
                print(f"   [WARN]  Unused class: {cls['name']} at line {cls['line']} (confidence: {confidence})")

    # Print summary
    print(f"\n[SUMMARY] Summary:")
    print(f"   Files analyzed: {stats['files_analyzed']}")
    print(f"   Functions found: {stats['functions_found']}")
    print(f"   Classes found: {stats['classes_found']}")
    print(f"   Potentially unused functions: {stats['functions_unused']}")
    print(f"   Potentially unused classes: {stats['classes_unused']}")
    print(f"   Total findings: {len(findings)}")

    return findings, stats


def _has_special_decorator(decorators):
    """
    Check if decorators indicate special usage.

    Returns True for:
    - FastAPI: @router.get, @app.on_event
    - LangChain: @tool
    - Pydantic: @field_validator, @model_validator
    - Property: @property, @setter, @classmethod, @staticmethod
    """
    special_decorators = [
        'router', 'app',  # FastAPI
        'tool',  # LangChain
        'field_validator', 'model_validator', 'validator',  # Pydantic
        'property', 'setter', 'getter', 'deleter',
        'classmethod', 'staticmethod', 'abstractmethod',
        'cached_property', 'lru_cache',
    ]

    for decorator in decorators:
        # Check if decorator name or prefix matches
        for special in special_decorators:
            if decorator.startswith(special):
                return True

    return False


def _determine_function_confidence(func, file_path):
    """
    Determine confidence level for unused function.

    Args:
        func: Function metadata dict
        file_path: Path to file

    Returns:
        'high' | 'medium' | 'low'
    """
    # Low confidence (likely used indirectly)

    # 1. Test functions (pytest discovers them)
    if func['name'].startswith('test_'):
        return 'low'

    # 2. Private functions starting with _ (may be internal)
    if func['name'].startswith('_') and not func['name'].startswith('__'):
        return 'medium'

    # 3. Async functions (may be callbacks)
    if func['is_async']:
        return 'medium'

    # 4. Functions with decorators (even if not special)
    if len(func['decorators']) > 0:
        return 'low'

    # 5. Functions in test files
    if 'test' in str(file_path).lower():
        return 'low'

    # High confidence (likely unused)

    # 1. Short functions (< 5 lines)
    # Can't determine from AST easily, use medium as default

    # 2. Utility functions with simple names
    if func['name'] in ['helper', 'util', 'format', 'parse']:
        return 'high'

    # Default: medium confidence
    return 'medium'


def _determine_class_confidence(cls, file_path):
    """
    Determine confidence level for unused class.

    Args:
        cls: Class metadata dict
        file_path: Path to file

    Returns:
        'high' | 'medium' | 'low'
    """
    # Low confidence (likely used indirectly)

    # 1. Test classes (pytest discovers them)
    if cls['name'].startswith('Test'):
        return 'low'

    # 2. SQLAlchemy models (auto-discovered)
    if 'Base' in cls['bases'] or 'Model' in cls['bases']:
        return 'low'

    # 3. Pydantic models (may be used in type hints)
    if 'BaseModel' in cls['bases'] or 'Settings' in cls['bases']:
        return 'low'

    # 4. Exception classes
    if 'Exception' in cls['bases'] or 'Error' in cls['bases']:
        return 'medium'

    # 5. Abstract classes
    if 'ABC' in cls['bases'] or 'Abstract' in cls['name']:
        return 'medium'

    # 6. Classes in models.py (ORM)
    if 'models.py' in str(file_path):
        return 'low'

    # High confidence (likely unused)

    # 1. Classes with no methods
    if len(cls['methods']) == 0:
        return 'high'

    # 2. Utility classes
    if cls['name'].endswith('Helper') or cls['name'].endswith('Util'):
        return 'high'

    # Default: medium confidence
    return 'medium'


def generate_report(findings, stats):
    """Generate markdown report."""
    additional_sections = {
        "[SUMMARY] Statistics": f"""
- **Files analyzed**: {stats['files_analyzed']}
- **Functions found**: {stats['functions_found']}
- **Classes found**: {stats['classes_found']}
- **Potentially unused functions**: {stats['functions_unused']}
- **Potentially unused classes**: {stats['classes_unused']}
- **Total findings**: {len(findings)}

### Breakdown by Confidence

""" + _generate_confidence_breakdown(findings) + """

---

## [WARN] Special Cases to Check

### FastAPI Decorators
```python
@router.get("/endpoint")  # Function used via decorator
async def handler():
    ...
```
-> **Automatically excluded** (decorator detection)

### LangChain Decorators
```python
@tool  # Function used via @tool decorator
def my_tool(...):
    ...
```
-> **Automatically excluded**

### Pydantic Validators
```python
@field_validator("field_name")
@classmethod
def validate_field(cls, v):
    ...
```
-> **Automatically excluded**

### Abstract Methods
```python
class BaseClass(ABC):
    @abstractmethod
    def method(self):  # Overridden in subclasses
        ...
```
→ **Automatically excluded**

### String Callbacks
```python
# Referenced by string in config
callbacks = ["module.path.function_name"]
```
→ **Requires manual verification** (grep for string literal)

### SQLAlchemy Models
```python
class User(Base):  # Auto-discovered by ORM
    ...
```
→ **Automatic LOW confidence** (Base inheritance detected)

---

## Verification Checklist

For each candidate function/class:

- [ ] **Grep for name** across entire codebase (check string literals)
- [ ] **Check tests**: mock.patch, pytest fixtures
- [ ] **Check callbacks**: Passed as parameter (callable)
- [ ] **Check reflection**: getattr, setattr, __dict__
- [ ] **Check inheritance**: Parent class of subclasses
- [ ] **Check imports**: Imported but not called directly

If **all checks** pass -> SAFE_TO_DELETE

If **any doubt** -> KEEP

---

## Next Steps

1. [OK] Manual review of each finding
2. Pending - Classification: SAFE_TO_DELETE / KEEP / UNCERTAIN
3. Pending - For SAFE_TO_DELETE:
   - Create git branch
   - Delete code
   - Run full tests (`pytest --cov`)
   - Verify coverage maintained
   - Commit if success, rollback if failure
""",
        "Notes": """
- Special methods (`__init__`, `__str__`, etc.) are automatically excluded
- Special decorators are detected and excluded
- ORM models (SQLAlchemy) are automatically set to LOW confidence
- Pydantic models are automatically set to LOW confidence
- Always verify tests before deletion
"""
    }

    generate_finding_report(
        title="Dead Code (Unused Functions & Classes)",
        findings=findings,
        output_path=OUTPUT_FILE,
        script_name="analyze_unused_code.py",
        additional_sections=additional_sections
    )


def _generate_confidence_breakdown(findings):
    """Generate confidence breakdown."""
    confidence_counts = {'high': 0, 'medium': 0, 'low': 0}
    for finding in findings:
        conf = finding.get('confidence', 'unknown')
        if conf in confidence_counts:
            confidence_counts[conf] += 1

    lines = []
    for conf, count in confidence_counts.items():
        emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(conf, '⚪')
        lines.append(f"- **{emoji} Confidence {conf}**: {count} item(s)")

    return "\n".join(lines)


if __name__ == "__main__":
    print("=" * 60)
    print("  Dead Code Analysis - LIA")
    print("=" * 60)
    print()

    try:
        findings, stats = analyze_unused_code()
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
