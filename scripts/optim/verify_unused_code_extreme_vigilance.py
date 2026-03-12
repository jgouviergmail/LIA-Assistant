"""
Extreme Vigilance - Unused Code Verification

This script performs EXTREME vigilance verification of potentially unused code,
with multiple safeguards to prevent accidental deletion of critical code.

Verification layers:
1. FastAPI route detection (decorators)
2. FastAPI dependency detection (Depends)
3. Middleware detection (dispatch methods)
4. Callback detection (LangChain, custom frameworks)
5. Magic method detection (__init__, __call__, etc.)
6. Test usage detection
7. Dynamic import detection (importlib, __import__)
8. Decorator usage detection

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-16
Session: 15 (Phase 5 - Extreme Vigilance)
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).parent.parent.parent / "apps" / "api" / "src"
TESTS_ROOT = Path(__file__).parent.parent.parent / "apps" / "api" / "tests"


# ============================================================================
# Safeguard Patterns
# ============================================================================

SAFEGUARD_PATTERNS = {
    "fastapi_routes": [
        r"@app\.(get|post|put|delete|patch)",
        r"@router\.(get|post|put|delete|patch)",
        r"APIRouter\(",
    ],
    "fastapi_dependencies": [
        r"Depends\(",
        r"Security\(",
        r"get_db\b",
        r"get_current_user",
        r"get_session",
    ],
    "middleware": [
        r"class.*Middleware",
        r"def dispatch\(",
        r"@middleware",
    ],
    "callbacks": [
        r"on_llm_",
        r"on_chain_",
        r"on_tool_",
        r"CallbackHandler",
        r"BaseCallbackHandler",
    ],
    "magic_methods": [
        r"def __init__\(",
        r"def __call__\(",
        r"def __enter__\(",
        r"def __exit__\(",
        r"def __getattr__\(",
        r"def __setattr__\(",
    ],
    "decorators": [
        r"@property",
        r"@classmethod",
        r"@staticmethod",
        r"@cached_property",
        r"@profile_",
        r"@trace_",
        r"@track_metrics",
    ],
}


class ExtremeVigilanceChecker:
    """Checks if a function is safe to delete with EXTREME vigilance."""

    def __init__(self, function_name: str, file_path: str):
        self.function_name = function_name
        self.file_path = file_path
        self.full_path = ROOT / file_path
        self.reasons_to_keep: List[str] = []
        self.file_content = ""

        if self.full_path.exists():
            self.file_content = self.full_path.read_text(encoding="utf-8")

    def check(self) -> tuple[bool, List[str]]:
        """
        Check if function is safe to delete.

        Returns:
            (is_safe_to_delete, reasons_to_keep)
        """
        # Run all safeguard checks
        self._check_fastapi_route()
        self._check_fastapi_dependency()
        self._check_middleware()
        self._check_callback()
        self._check_magic_method()
        self._check_decorator_usage()
        self._check_test_usage()
        self._check_dynamic_import()

        is_safe = len(self.reasons_to_keep) == 0
        return is_safe, self.reasons_to_keep

    def _check_fastapi_route(self):
        """Check if function is a FastAPI route."""
        for pattern in SAFEGUARD_PATTERNS["fastapi_routes"]:
            # Check 10 lines before function definition
            lines = self.file_content.split("\n")
            for i, line in enumerate(lines):
                if f"def {self.function_name}(" in line or f"async def {self.function_name}(" in line:
                    # Check previous 10 lines for route decorator
                    start = max(0, i - 10)
                    context = "\n".join(lines[start:i+1])
                    if re.search(pattern, context):
                        self.reasons_to_keep.append(f"FastAPI route: {pattern}")
                        return

    def _check_fastapi_dependency(self):
        """Check if function is used as FastAPI dependency."""
        for pattern in SAFEGUARD_PATTERNS["fastapi_dependencies"]:
            if self.function_name in pattern or re.search(pattern, self.file_content):
                # Check if function name appears in Depends()
                if f"Depends({self.function_name})" in self.file_content:
                    self.reasons_to_keep.append(f"FastAPI dependency: Depends({self.function_name})")
                    return

    def _check_middleware(self):
        """Check if function is middleware dispatch method."""
        for pattern in SAFEGUARD_PATTERNS["middleware"]:
            if re.search(pattern, self.file_content):
                if self.function_name == "dispatch":
                    self.reasons_to_keep.append("Middleware dispatch method")
                    return

    def _check_callback(self):
        """Check if function is a callback (LangChain, etc.)."""
        for pattern in SAFEGUARD_PATTERNS["callbacks"]:
            if re.search(pattern, self.function_name) or re.search(pattern, self.file_content):
                if "on_" in self.function_name or "Handler" in self.file_path:
                    self.reasons_to_keep.append(f"Callback function: {pattern}")
                    return

    def _check_magic_method(self):
        """Check if function is a magic method."""
        if self.function_name.startswith("__") and self.function_name.endswith("__"):
            self.reasons_to_keep.append(f"Magic method: {self.function_name}")

    def _check_decorator_usage(self):
        """Check if function has decorators that indicate usage."""
        for pattern in SAFEGUARD_PATTERNS["decorators"]:
            # Check lines before function definition
            lines = self.file_content.split("\n")
            for i, line in enumerate(lines):
                if f"def {self.function_name}(" in line or f"async def {self.function_name}(" in line:
                    # Check previous 5 lines for decorators
                    start = max(0, i - 5)
                    context = "\n".join(lines[start:i])
                    if re.search(pattern, context):
                        self.reasons_to_keep.append(f"Has decorator: {pattern}")
                        return

    def _check_test_usage(self):
        """Check if function is used in tests."""
        if not TESTS_ROOT.exists():
            return

        # Search for function name in test files
        for test_file in TESTS_ROOT.rglob("*.py"):
            try:
                content = test_file.read_text(encoding="utf-8")
                if self.function_name in content:
                    # Check if it's actually calling the function (not just a string)
                    if f"{self.function_name}(" in content or f".{self.function_name}" in content:
                        self.reasons_to_keep.append(f"Used in test: {test_file.name}")
                        return
            except:
                pass

    def _check_dynamic_import(self):
        """Check if function might be imported dynamically."""
        # Check if file has dynamic imports
        if "importlib" in self.file_content or "__import__" in self.file_content:
            self.reasons_to_keep.append("File has dynamic imports - may be used dynamically")


def analyze_unused_code_with_extreme_vigilance():
    """
    Analyze all 152 potentially unused functions with EXTREME vigilance.

    Returns:
        Dict with categorized results
    """
    # Read unused code report
    unused_code_path = Path(__file__).parent.parent.parent / "docs" / "optim" / "02_UNUSED_CODE.md"

    if not unused_code_path.exists():
        print(f"ERROR: {unused_code_path} not found")
        return

    content = unused_code_path.read_text(encoding="utf-8")

    # Parse table (skip header, parse rows)
    lines = content.split("\n")
    table_start = None
    for i, line in enumerate(lines):
        if "| Élément" in line and "| Location" in line:
            table_start = i + 2  # Skip header + separator
            break

    if not table_start:
        print("ERROR: Could not find table in report")
        return

    results = {
        "KEEP - FastAPI route": [],
        "KEEP - FastAPI dependency": [],
        "KEEP - Middleware": [],
        "KEEP - Callback": [],
        "KEEP - Magic method": [],
        "KEEP - Decorator": [],
        "KEEP - Test usage": [],
        "KEEP - Dynamic import": [],
        "MAYBE SAFE - Manual review required": [],
        "SAFE - Can delete": [],
    }

    # Parse each row
    for line in lines[table_start:]:
        if not line.strip() or not line.startswith("|"):
            continue

        parts = [p.strip() for p in line.split("|")[1:-1]]  # Remove empty first/last
        if len(parts) < 3:
            continue

        function_name = parts[0].strip()
        location = parts[1].strip()
        confidence = parts[2].strip()

        # Skip class definitions for now (need different analysis)
        if function_name.startswith("class "):
            continue

        # Extract file path and line number
        if ":" in location:
            file_path, line_num = location.rsplit(":", 1)
        else:
            file_path = location
            line_num = "?"

        # Run extreme vigilance check
        checker = ExtremeVigilanceChecker(
            function_name.replace("()", ""),
            file_path.replace("\\", "/")
        )
        is_safe, reasons = checker.check()

        # Categorize based on reasons
        if not is_safe:
            for reason in reasons:
                if "FastAPI route" in reason:
                    results["KEEP - FastAPI route"].append((function_name, location, reason))
                elif "FastAPI dependency" in reason:
                    results["KEEP - FastAPI dependency"].append((function_name, location, reason))
                elif "Middleware" in reason:
                    results["KEEP - Middleware"].append((function_name, location, reason))
                elif "Callback" in reason:
                    results["KEEP - Callback"].append((function_name, location, reason))
                elif "Magic method" in reason:
                    results["KEEP - Magic method"].append((function_name, location, reason))
                elif "decorator" in reason:
                    results["KEEP - Decorator"].append((function_name, location, reason))
                elif "test" in reason:
                    results["KEEP - Test usage"].append((function_name, location, reason))
                elif "dynamic" in reason:
                    results["KEEP - Dynamic import"].append((function_name, location, reason))
                break  # Only need first reason
        else:
            # Still require manual review for "safe" items
            results["MAYBE SAFE - Manual review required"].append((function_name, location, confidence))

    return results


def generate_report(results: Dict):
    """Generate markdown report of extreme vigilance analysis."""
    report = []
    report.append("# Unused Code - Extreme Vigilance Analysis\n")
    report.append("**Date** : 2025-11-16\n")
    report.append("**Analyzer** : Extreme Vigilance Checker\n")
    report.append("**Scope** : 152 potentially unused functions\n")
    report.append("\n---\n")

    report.append("## 🛡️ Safeguard Summary\n\n")

    total_keep = 0
    for category, items in results.items():
        if category.startswith("KEEP"):
            total_keep += len(items)

    report.append(f"**Total analyzed** : 152 functions\n")
    report.append(f"**KEEP (safeguarded)** : {total_keep}\n")
    report.append(f"**MAYBE SAFE (manual review)** : {len(results.get('MAYBE SAFE - Manual review required', []))}\n")
    report.append(f"**SAFE (can delete)** : {len(results.get('SAFE - Can delete', []))}\n")
    report.append("\n")

    report.append("**Recommendation** : 🔴 **DO NOT DELETE ANY CODE** without manual review\n")
    report.append("\n---\n")

    # Detail each category
    for category, items in sorted(results.items()):
        if not items:
            continue

        report.append(f"## {category} ({len(items)} items)\n\n")

        for item in items:
            if len(item) == 3:
                func, loc, reason = item
                report.append(f"- `{func}` - {loc}\n")
                report.append(f"  - Reason: {reason}\n")
            elif len(item) == 3:
                func, loc, conf = item
                report.append(f"- `{func}` - {loc} (confidence: {conf})\n")

        report.append("\n")

    report.append("---\n")
    report.append("**Report Generated** : 2025-11-16\n")
    report.append("**Status** : ✅ EXTREME VIGILANCE ANALYSIS COMPLETE\n")
    report.append("**Recommendation** : Manual review required for ALL items\n")

    return "".join(report)


def main():
    """Main entry point."""
    print("Starting Extreme Vigilance Analysis...")
    print()

    results = analyze_unused_code_with_extreme_vigilance()

    if results:
        print("Analysis complete!")
        print()
        print("Summary:")
        for category, items in results.items():
            print(f"  {category}: {len(items)} items")

        # Generate report
        report = generate_report(results)
        output_path = Path(__file__).parent.parent.parent / "docs" / "optim" / "UNUSED_CODE_EXTREME_VIGILANCE.md"
        output_path.write_text(report, encoding="utf-8")
        print()
        print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    main()
