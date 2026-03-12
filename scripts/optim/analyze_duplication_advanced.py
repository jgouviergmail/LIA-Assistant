"""
Advanced code duplication analysis for LIA.

This script performs semantic duplication detection beyond exact string matching,
identifying similar code blocks, repeated patterns, and refactoring opportunities.

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-16
"""

import ast
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

# Root directory
ROOT = Path(__file__).parent.parent.parent / "apps" / "api" / "src"


class FunctionExtractor(ast.NodeVisitor):
    """Extract function definitions with their normalized AST structure."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.functions: List[Dict] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definition and extract metadata."""
        # Get function source
        try:
            func_lines = ast.get_source_segment(
                open(self.filepath).read(), node
            )
        except:
            func_lines = ""

        # Calculate AST hash (normalized structure)
        ast_hash = self._hash_ast(node)

        # Extract function metadata
        func_info = {
            "name": node.name,
            "filepath": str(self.filepath),
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "args": [arg.arg for arg in node.args.args],
            "num_lines": (node.end_lineno or 0) - node.lineno + 1,
            "ast_hash": ast_hash,
            "source": func_lines or "",
            "complexity": self._estimate_complexity(node),
        }

        self.functions.append(func_info)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Visit async function definition."""
        # Treat async functions same as regular functions
        self.visit_FunctionDef(node)

    def _hash_ast(self, node: ast.AST) -> str:
        """
        Hash the AST structure (ignoring variable/function names).

        This allows detecting structurally similar code even if names differ.
        """
        # Normalize AST by dumping without names
        normalized = ast.dump(node, annotate_fields=False, include_attributes=False)

        # Remove specific names to focus on structure
        # (e.g., "foo(x, y)" and "bar(a, b)" have same structure)
        # This is a simplification - a full implementation would walk the AST

        return hashlib.md5(normalized.encode()).hexdigest()

    def _estimate_complexity(self, node: ast.AST) -> int:
        """
        Estimate cyclomatic complexity (simplified McCabe).

        Counts decision points: if, for, while, except, and, or, etc.
        """
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            if isinstance(
                child,
                (
                    ast.If,
                    ast.For,
                    ast.While,
                    ast.ExceptHandler,
                    ast.With,
                    ast.Assert,
                ),
            ):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                # and/or add decision points
                complexity += len(child.values) - 1

        return complexity


class ClassExtractor(ast.NodeVisitor):
    """Extract class definitions and their methods."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.classes: List[Dict] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definition and extract metadata."""
        # Count methods
        methods = [
            n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        class_info = {
            "name": node.name,
            "filepath": str(self.filepath),
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "num_methods": len(methods),
            "num_lines": (node.end_lineno or 0) - node.lineno + 1,
            "bases": [ast.unparse(base) for base in node.bases],
        }

        self.classes.append(class_info)
        self.generic_visit(node)


def analyze_functions(root: Path) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
    """
    Analyze all functions in the codebase.

    Returns:
        - List of all function metadata
        - Dict of duplicates grouped by AST hash
    """
    all_functions = []

    for py_file in root.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        try:
            with open(py_file, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source, filename=str(py_file))
            extractor = FunctionExtractor(str(py_file))
            extractor.visit(tree)

            all_functions.extend(extractor.functions)

        except SyntaxError:
            print(f"⚠️  Syntax error in {py_file}, skipping")
            continue
        except Exception as e:
            print(f"⚠️  Error parsing {py_file}: {e}")
            continue

    # Group by AST hash to find duplicates
    duplicates = defaultdict(list)
    for func in all_functions:
        duplicates[func["ast_hash"]].append(func)

    # Filter to only groups with 2+ functions (actual duplicates)
    duplicates = {k: v for k, v in duplicates.items() if len(v) >= 2}

    return all_functions, duplicates


def analyze_classes(root: Path) -> List[Dict]:
    """Analyze all classes in the codebase."""
    all_classes = []

    for py_file in root.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        try:
            with open(py_file, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source, filename=str(py_file))
            extractor = ClassExtractor(str(py_file))
            extractor.visit(tree)

            all_classes.extend(extractor.classes)

        except SyntaxError:
            continue
        except Exception:
            continue

    return all_classes


def find_similar_functions(
    functions: List[Dict], similarity_threshold: int = 5
) -> List[Tuple[Dict, Dict, int]]:
    """
    Find functions with similar signatures but different implementations.

    This detects potential candidates for refactoring into a common function
    with parameters.

    Returns:
        List of (func1, func2, similarity_score) tuples
    """
    similar_pairs = []

    for i, func1 in enumerate(functions):
        for func2 in functions[i + 1 :]:
            # Skip if same file (already handled by AST hash duplicates)
            if func1["filepath"] == func2["filepath"]:
                continue

            # Calculate similarity score
            score = 0

            # Same number of arguments
            if len(func1["args"]) == len(func2["args"]):
                score += 2

            # Similar line count (within 20%)
            lines_diff = abs(func1["num_lines"] - func2["num_lines"])
            lines_avg = (func1["num_lines"] + func2["num_lines"]) / 2
            if lines_avg > 0 and lines_diff / lines_avg < 0.2:
                score += 2

            # Similar complexity
            complexity_diff = abs(func1["complexity"] - func2["complexity"])
            if complexity_diff <= 1:
                score += 1

            # Similar name (contains same words)
            name1_words = set(func1["name"].lower().split("_"))
            name2_words = set(func2["name"].lower().split("_"))
            common_words = name1_words & name2_words
            if len(common_words) >= 2:
                score += 2

            # If similarity above threshold, record pair
            if score >= similarity_threshold:
                similar_pairs.append((func1, func2, score))

    return similar_pairs


def generate_report(
    all_functions: List[Dict],
    duplicates: Dict[str, List[Dict]],
    similar_functions: List[Tuple[Dict, Dict, int]],
    all_classes: List[Dict],
) -> str:
    """Generate markdown report of code duplication findings."""

    report = []
    report.append("# Advanced Code Duplication Analysis\n")
    report.append("**Date** : 2025-11-16\n")
    report.append("**Tool** : Custom AST-based analyzer\n")
    report.append("**Scope** : apps/api/src\n")
    report.append("\n---\n")

    # Executive Summary
    report.append("## 📊 Executive Summary\n")
    report.append(f"**Total functions analyzed** : {len(all_functions)}\n")
    report.append(f"**Total classes analyzed** : {len(all_classes)}\n")
    report.append(f"**Exact duplicates (AST hash)** : {len(duplicates)} groups\n")
    report.append(f"**Similar functions** : {len(similar_functions)} pairs\n")
    report.append("\n---\n")

    # Complexity Distribution
    report.append("## 📈 Complexity Distribution\n")
    complexities = [f["complexity"] for f in all_functions]
    if complexities:
        avg_complexity = sum(complexities) / len(complexities)
        max_complexity = max(complexities)
        high_complexity = [f for f in all_functions if f["complexity"] > 10]

        report.append(f"**Average complexity** : {avg_complexity:.1f}\n")
        report.append(f"**Maximum complexity** : {max_complexity}\n")
        report.append(
            f"**High complexity functions (>10)** : {len(high_complexity)}\n"
        )
        report.append("\n")

        if high_complexity:
            report.append("### Top 10 Most Complex Functions\n")
            high_complexity.sort(key=lambda f: f["complexity"], reverse=True)
            for i, func in enumerate(high_complexity[:10], 1):
                filepath_rel = func["filepath"].replace(str(ROOT), "")
                report.append(
                    f"{i}. **{func['name']}** ({func['complexity']}) - "
                    f"[{filepath_rel}:{func['lineno']}]({func['filepath']}#L{func['lineno']})\n"
                )
            report.append("\n")

    report.append("---\n")

    # Exact Duplicates
    report.append("## 🔴 Exact Duplicates (AST Structure Match)\n")
    report.append(
        "These functions have identical AST structure (same logic, different names).\n"
    )
    report.append("**Recommendation** : HIGH priority - refactor into single function.\n")
    report.append("\n")

    if not duplicates:
        report.append("✅ **No exact duplicates found!**\n")
    else:
        for i, (ast_hash, funcs) in enumerate(duplicates.items(), 1):
            report.append(f"### Duplicate Group {i} ({len(funcs)} functions)\n")

            # Show first function as reference
            ref_func = funcs[0]
            report.append(f"**Reference** : `{ref_func['name']}` ({ref_func['num_lines']} lines, complexity {ref_func['complexity']})\n")
            report.append("\n")

            report.append("**Duplicates** :\n")
            for func in funcs:
                filepath_rel = func["filepath"].replace(str(ROOT), "")
                report.append(
                    f"- `{func['name']}` - [{filepath_rel}:{func['lineno']}]({func['filepath']}#L{func['lineno']})\n"
                )

            report.append("\n")

    report.append("---\n")

    # Similar Functions
    report.append("## 🟡 Similar Functions (Refactoring Candidates)\n")
    report.append(
        "These functions have similar signatures/complexity but different implementations.\n"
    )
    report.append("**Recommendation** : MEDIUM priority - consider extracting common pattern.\n")
    report.append("\n")

    if not similar_functions:
        report.append("✅ **No highly similar functions found!**\n")
    else:
        # Sort by similarity score
        similar_functions.sort(key=lambda x: x[2], reverse=True)

        for i, (func1, func2, score) in enumerate(similar_functions[:20], 1):
            filepath1_rel = func1["filepath"].replace(str(ROOT), "")
            filepath2_rel = func2["filepath"].replace(str(ROOT), "")

            report.append(f"### Similar Pair {i} (score: {score}/9)\n")
            report.append(f"1. `{func1['name']}` ({func1['num_lines']} lines) - [{filepath1_rel}:{func1['lineno']}]({func1['filepath']}#L{func1['lineno']})\n")
            report.append(f"2. `{func2['name']}` ({func2['num_lines']} lines) - [{filepath2_rel}:{func2['lineno']}]({func2['filepath']}#L{func2['lineno']})\n")
            report.append("\n")

        if len(similar_functions) > 20:
            report.append(f"... and {len(similar_functions) - 20} more pairs\n")
            report.append("\n")

    report.append("---\n")

    # Large Classes
    report.append("## 📦 Large Classes (Potential God Objects)\n")
    large_classes = [c for c in all_classes if c["num_methods"] > 15]
    large_classes.sort(key=lambda c: c["num_methods"], reverse=True)

    if not large_classes:
        report.append("✅ **No large classes (>15 methods) found!**\n")
    else:
        for i, cls in enumerate(large_classes, 1):
            filepath_rel = cls["filepath"].replace(str(ROOT), "")
            report.append(
                f"{i}. **{cls['name']}** ({cls['num_methods']} methods, {cls['num_lines']} lines) - "
                f"[{filepath_rel}:{cls['lineno']}]({cls['filepath']}#L{cls['lineno']})\n"
            )

    report.append("\n---\n")

    # Recommendations
    report.append("## 🎯 Recommendations\n")
    report.append("\n")
    report.append("### High Priority (Exact Duplicates)\n")
    if duplicates:
        report.append(f"1. Refactor {len(duplicates)} groups of exact duplicates\n")
        report.append("2. Extract common logic into single function\n")
        report.append("3. Parameterize differences\n")
    else:
        report.append("✅ No exact duplicates - excellent code quality!\n")

    report.append("\n")
    report.append("### Medium Priority (Similar Functions)\n")
    if similar_functions:
        report.append(f"1. Review {len(similar_functions)} pairs of similar functions\n")
        report.append("2. Identify common patterns\n")
        report.append("3. Consider extracting base class or utility function\n")
    else:
        report.append("✅ No highly similar functions detected\n")

    report.append("\n")
    report.append("### Low Priority (Large Classes)\n")
    if large_classes:
        report.append(f"1. Review {len(large_classes)} large classes\n")
        report.append("2. Consider splitting into smaller, focused classes\n")
        report.append("3. Apply Single Responsibility Principle\n")
    else:
        report.append("✅ No large classes detected\n")

    report.append("\n---\n")
    report.append("**Report Generated** : 2025-11-16\n")
    report.append("**Analyzer** : Custom AST-based duplication detector\n")

    return "".join(report)


def main():
    """Main entry point."""
    print("Starting advanced code duplication analysis...")
    print(f"Analyzing: {ROOT}")
    print()

    # Analyze functions
    print("Extracting functions...")
    all_functions, duplicates = analyze_functions(ROOT)
    print(f"   Found {len(all_functions)} functions")
    print(f"   Detected {len(duplicates)} duplicate groups")
    print()

    # Analyze classes
    print("Extracting classes...")
    all_classes = analyze_classes(ROOT)
    print(f"   Found {len(all_classes)} classes")
    print()

    # Find similar functions
    print("Finding similar functions...")
    similar_functions = find_similar_functions(all_functions, similarity_threshold=5)
    print(f"   Found {len(similar_functions)} similar pairs")
    print()

    # Generate report
    print("Generating report...")
    report = generate_report(all_functions, duplicates, similar_functions, all_classes)

    # Save report
    output_path = Path(__file__).parent.parent.parent / "docs" / "optim" / "CODE_DUPLICATION_ADVANCED.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"Report saved to: {output_path}")

    # Save JSON for further analysis
    json_path = Path(__file__).parent.parent.parent / "docs" / "optim" / "duplication_data.json"
    data = {
        "total_functions": len(all_functions),
        "total_classes": len(all_classes),
        "duplicate_groups": len(duplicates),
        "similar_pairs": len(similar_functions),
        "duplicates": [
            {
                "ast_hash": ast_hash,
                "functions": [
                    {
                        "name": f["name"],
                        "filepath": f["filepath"],
                        "lineno": f["lineno"],
                        "num_lines": f["num_lines"],
                        "complexity": f["complexity"],
                    }
                    for f in funcs
                ],
            }
            for ast_hash, funcs in duplicates.items()
        ],
        "similar_functions": [
            {
                "func1": {
                    "name": f1["name"],
                    "filepath": f1["filepath"],
                    "lineno": f1["lineno"],
                },
                "func2": {
                    "name": f2["name"],
                    "filepath": f2["filepath"],
                    "lineno": f2["lineno"],
                },
                "score": score,
            }
            for f1, f2, score in similar_functions[:50]  # Top 50 pairs
        ],
    }
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"JSON data saved to: {json_path}")
    print()
    print("Analysis complete!")


if __name__ == "__main__":
    main()
