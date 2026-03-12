"""
Automatic inventory script for LangChain tools.

Scans the apps/api/src/domains/agents/tools/ directory and extracts all tools
decorated with @tool to generate a JSON and Markdown inventory.

Usage:
    python scripts/agents/list_tools.py
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

# Configuration
TOOLS_ROOT = Path("apps/api/src/domains/agents/tools")
OUTPUT_JSON = Path("docs/agents/tool_inventory.json")
OUTPUT_MD = Path("docs/agents/tool_inventory.md")


class ToolVisitor(ast.NodeVisitor):
    """AST visitor to extract functions decorated with @tool."""

    def __init__(self, module: str) -> None:
        self.module = module
        self.tools: list[dict[str, Any]] = []

    def _process_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Process a function definition (sync or async)."""
        # Extract decorator names
        decorator_ids = []
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                decorator_ids.append(decorator.id)
            elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                decorator_ids.append(decorator.func.id)

        # If "tool" decorator is present
        if "tool" in decorator_ids:
            # Extract arguments
            args = []
            for arg in node.args.args:
                arg_annotation = ""
                if arg.annotation:
                    arg_annotation = ast.unparse(arg.annotation)
                args.append({
                    "name": arg.arg,
                    "annotation": arg_annotation,
                })

            # Extract docstring
            docstring = ast.get_docstring(node) or ""
            # Clean docstring (single line)
            docstring_clean = " ".join(docstring.strip().split())
            if len(docstring_clean) > 200:
                docstring_clean = docstring_clean[:200] + "..."

            # Determine if async
            is_async = isinstance(node, ast.AsyncFunctionDef)

            self.tools.append({
                "name": node.name,
                "module": self.module,
                "decorators": decorator_ids,
                "args": args,
                "docstring": docstring_clean,
                "lineno": node.lineno,
                "is_async": is_async,
            })

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit a sync function definition."""
        self._process_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit an async function definition."""
        self._process_function(node)
        self.generic_visit(node)


def main() -> None:
    """Run the tool inventory."""
    print("[*] Scanning tools directory...")

    tools: list[dict[str, Any]] = []

    # Iterate over all .py files
    for file_path in TOOLS_ROOT.rglob("*.py"):
        # Skip __init__.py and test files
        if file_path.name == "__init__.py" or file_path.name.startswith("test_"):
            continue

        # Build module name
        relative_path = file_path.relative_to(Path("."))
        module = str(relative_path).replace("\\", ".").replace("/", ".").removesuffix(".py")

        print(f"  [*] Analyzing {file_path.name}...")

        # Parse the file
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        except SyntaxError as e:
            print(f"    [!] Syntax error: {e}")
            continue

        # Visit the AST
        visitor = ToolVisitor(module)
        visitor.visit(tree)

        if visitor.tools:
            print(f"    [+] Found {len(visitor.tools)} tool(s)")
        tools.extend(visitor.tools)

    # Sort by name
    tools.sort(key=lambda x: x["name"])

    print(f"\n[+] Total tools found: {len(tools)}")

    # Generate JSON
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(tools, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[+] JSON inventory saved: {OUTPUT_JSON}")

    # Generate Markdown
    md_lines = [
        "# Tool Inventory",
        "",
        f"**Generated:** {Path(__file__).name}",
        f"**Total tools:** {len(tools)}",
        "",
        "| Tool | Type | Module | Line | Decorators | Arguments | Description |",
        "|------|------|--------|------|------------|-----------|-------------|",
    ]

    for tool in tools:
        # Format arguments
        args_str = ", ".join([
            f"{arg['name']}: {arg['annotation']}" if arg['annotation'] else arg['name']
            for arg in tool["args"]
        ])
        if len(args_str) > 50:
            args_str = args_str[:47] + "..."

        # Format decorators
        decorators_str = ", ".join([f"`{d}`" for d in tool["decorators"]])

        # Type (async or sync)
        tool_type = "async" if tool.get("is_async", False) else "sync"

        # Table row
        md_lines.append(
            f"| **{tool['name']}** | {tool_type} | `{tool['module']}` | {tool['lineno']} | "
            f"{decorators_str} | {args_str} | {tool['docstring']} |"
        )

    OUTPUT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[+] Markdown inventory saved: {OUTPUT_MD}")

    # Summary by file
    files_count = len(set(t["module"] for t in tools))
    print(f"\n[+] Tools distributed across {files_count} file(s)")


if __name__ == "__main__":
    main()
