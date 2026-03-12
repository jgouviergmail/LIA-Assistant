"""
Advanced code complexity and duplication analysis.

Analyzes:
1. Cyclomatic complexity (CC) - identifies complex functions
2. Maintainability index (MI) - identifies hard-to-maintain modules
3. Code duplication - identifies similar code blocks
4. Function length - identifies long functions
"""

import ast
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class FunctionMetrics:
    """Metrics for a single function."""

    name: str
    file: str
    line: int
    complexity: int
    length: int  # lines of code
    parameters: int
    returns: int  # number of return statements
    branches: int  # if/elif/else/for/while/with/try


@dataclass
class DuplicationBlock:
    """Represents a block of duplicated code."""

    hash: str
    locations: List[Tuple[str, int, int]]  # (file, start_line, end_line)
    lines: int
    code_sample: str


class ComplexityAnalyzer(ast.NodeVisitor):
    """AST-based complexity analyzer."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.functions: List[FunctionMetrics] = []
        self.current_function = None
        self.complexity = 0
        self.returns = 0
        self.branches = 0

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Save previous function context
        prev_function = self.current_function
        prev_complexity = self.complexity
        prev_returns = self.returns
        prev_branches = self.branches

        # Start new function
        self.current_function = node.name
        self.complexity = 1  # Base complexity
        self.returns = 0
        self.branches = 0

        # Visit function body
        self.generic_visit(node)

        # Calculate function length
        if node.body:
            start_line = node.lineno
            end_line = max(
                getattr(n, "lineno", start_line) for n in ast.walk(node) if hasattr(n, "lineno")
            )
            length = end_line - start_line + 1
        else:
            length = 1

        # Record metrics
        metrics = FunctionMetrics(
            name=node.name,
            file=self.filepath,
            line=node.lineno,
            complexity=self.complexity,
            length=length,
            parameters=len(node.args.args),
            returns=self.returns,
            branches=self.branches,
        )
        self.functions.append(metrics)

        # Restore previous context
        self.current_function = prev_function
        self.complexity = prev_complexity
        self.returns = prev_returns
        self.branches = prev_branches

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node: ast.If):
        self.complexity += 1
        self.branches += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        self.complexity += 1
        self.branches += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While):
        self.complexity += 1
        self.branches += 1
        self.generic_visit(node)

    def visit_With(self, node: ast.With):
        self.complexity += 1
        self.branches += 1
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try):
        self.complexity += 1
        self.branches += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        # Each and/or adds complexity
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return):
        self.returns += 1
        self.generic_visit(node)


class DuplicationDetector:
    """Detects code duplication using normalized AST hashing."""

    def __init__(self, min_lines: int = 10):
        self.min_lines = min_lines
        self.blocks: Dict[str, List[Tuple[str, int, int, str]]] = defaultdict(list)

    def normalize_code(self, code: str) -> str:
        """Normalize code by removing comments and extra whitespace."""
        lines = []
        for line in code.split("\n"):
            # Remove comments
            if "#" in line:
                line = line[: line.index("#")]
            # Strip whitespace
            line = line.strip()
            if line:
                lines.append(line)
        return "\n".join(lines)

    def analyze_file(self, filepath: str, content: str):
        """Analyze a file for duplicated blocks."""
        lines = content.split("\n")

        # Sliding window approach
        for start_idx in range(len(lines)):
            for window_size in range(self.min_lines, min(50, len(lines) - start_idx + 1)):
                end_idx = start_idx + window_size
                block = "\n".join(lines[start_idx:end_idx])

                # Normalize and hash
                normalized = self.normalize_code(block)
                if not normalized or normalized.count("\n") < self.min_lines - 1:
                    continue

                block_hash = hashlib.md5(normalized.encode()).hexdigest()

                # Store location
                self.blocks[block_hash].append(
                    (filepath, start_idx + 1, end_idx, block[:200])  # Sample
                )

    def get_duplications(self) -> List[DuplicationBlock]:
        """Get all duplicated blocks (appearing in 2+ locations)."""
        duplications = []

        for block_hash, locations in self.blocks.items():
            if len(locations) >= 2:
                # Remove duplicates (same file, overlapping lines)
                unique_locations = []
                seen_files = set()

                for filepath, start, end, sample in locations:
                    key = f"{filepath}:{start}-{end}"
                    if filepath not in seen_files:
                        unique_locations.append((filepath, start, end))
                        seen_files.add(filepath)

                if len(unique_locations) >= 2:
                    _, start, end, _ = locations[0]  # (filepath, start, end, sample)
                    lines = end - start

                    duplications.append(
                        DuplicationBlock(
                            hash=block_hash,
                            locations=unique_locations,
                            lines=lines,
                            code_sample=locations[0][3],
                        )
                    )

        # Sort by impact (lines * occurrences)
        duplications.sort(key=lambda d: d.lines * len(d.locations), reverse=True)
        return duplications


def analyze_directory(root_dir: Path) -> Tuple[List[FunctionMetrics], List[DuplicationBlock]]:
    """Analyze all Python files in directory."""
    all_functions = []
    duplication_detector = DuplicationDetector(min_lines=10)

    python_files = list(root_dir.rglob("*.py"))
    print(f"Analyzing {len(python_files)} Python files...")

    for filepath in python_files:
        try:
            content = filepath.read_text(encoding="utf-8")

            # Parse AST
            tree = ast.parse(content, filename=str(filepath))

            # Analyze complexity
            analyzer = ComplexityAnalyzer(str(filepath))
            analyzer.visit(tree)
            all_functions.extend(analyzer.functions)

            # Analyze duplication
            duplication_detector.analyze_file(str(filepath), content)

        except Exception as e:
            print(f"Error analyzing {filepath}: {e}", file=sys.stderr)

    duplications = duplication_detector.get_duplications()

    return all_functions, duplications


def generate_report(
    functions: List[FunctionMetrics], duplications: List[DuplicationBlock]
) -> Dict:
    """Generate analysis report."""

    # Complexity thresholds
    # CC 1-10: Low risk, simple
    # CC 11-20: Moderate risk, more complex
    # CC 21-50: High risk, very complex
    # CC 50+: Extremely high risk, unmaintainable

    complex_functions = [f for f in functions if f.complexity > 10]
    very_complex = [f for f in functions if f.complexity > 20]
    extremely_complex = [f for f in functions if f.complexity > 50]

    # Long functions (>50 lines)
    long_functions = [f for f in functions if f.length > 50]

    # High parameter count (>5 params)
    many_params = [f for f in functions if f.parameters > 5]

    report = {
        "summary": {
            "total_functions": len(functions),
            "complex_functions": len(complex_functions),
            "very_complex_functions": len(very_complex),
            "extremely_complex_functions": len(extremely_complex),
            "long_functions": len(long_functions),
            "high_parameter_functions": len(many_params),
            "duplication_blocks": len(duplications),
            "total_duplicated_lines": sum(d.lines * (len(d.locations) - 1) for d in duplications),
        },
        "top_complex_functions": [
            {
                "name": f.name,
                "file": f.file,
                "line": f.line,
                "complexity": f.complexity,
                "length": f.length,
                "parameters": f.parameters,
            }
            for f in sorted(functions, key=lambda x: x.complexity, reverse=True)[:20]
        ],
        "top_long_functions": [
            {
                "name": f.name,
                "file": f.file,
                "line": f.line,
                "length": f.length,
                "complexity": f.complexity,
            }
            for f in sorted(functions, key=lambda x: x.length, reverse=True)[:20]
        ],
        "top_duplications": [
            {
                "lines": d.lines,
                "occurrences": len(d.locations),
                "total_duplicated_lines": d.lines * (len(d.locations) - 1),
                "locations": [f"{loc[0]}:{loc[1]}-{loc[2]}" for loc in d.locations[:5]],
                "sample": d.code_sample,
            }
            for d in duplications[:20]
        ],
    }

    return report


def main():
    root_dir = Path("src")

    if not root_dir.exists():
        print(f"Directory {root_dir} not found", file=sys.stderr)
        sys.exit(1)

    print("Advanced Code Analysis")
    print("=" * 60)

    functions, duplications = analyze_directory(root_dir)

    report = generate_report(functions, duplications)

    # Save JSON report
    output_file = Path("../../docs/optim/complexity_analysis.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Print summary
    print(f"\nSummary:")
    print(f"  Total functions analyzed: {report['summary']['total_functions']}")
    print(f"  Complex functions (CC > 10): {report['summary']['complex_functions']}")
    print(f"  Very complex (CC > 20): {report['summary']['very_complex_functions']}")
    print(f"  Extremely complex (CC > 50): {report['summary']['extremely_complex_functions']}")
    print(f"  Long functions (>50 lines): {report['summary']['long_functions']}")
    print(f"  High parameter count (>5): {report['summary']['high_parameter_functions']}")
    print(f"\nDuplication:")
    print(f"  Duplication blocks found: {report['summary']['duplication_blocks']}")
    print(
        f"  Total duplicated lines: {report['summary']['total_duplicated_lines']}"
    )

    print(f"\nTop 10 Most Complex Functions:")
    for i, func in enumerate(report["top_complex_functions"][:10], 1):
        file_short = func["file"].replace("src\\", "")
        print(
            f"  {i}. {func['name']} - CC: {func['complexity']}, "
            f"Length: {func['length']} lines ({file_short}:{func['line']})"
        )

    print(f"\nTop 10 Duplication Blocks (by impact):")
    for i, dup in enumerate(report["top_duplications"][:10], 1):
        impact = dup["total_duplicated_lines"]
        print(
            f"  {i}. {dup['lines']} lines × {dup['occurrences']} locations = {impact} duplicated lines"
        )
        for loc in dup["locations"][:3]:
            loc_short = loc.replace("src\\", "").replace("src/", "")
            print(f"      - {loc_short}")

    print(f"\nFull report saved to: {output_file}")


if __name__ == "__main__":
    main()
