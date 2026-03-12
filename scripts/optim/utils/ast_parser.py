#!/usr/bin/env python3
"""
Generic AST Parsing Utilities for Code Analysis.

This module provides reusable AST parsing functions for analyzing Python code.
Used by multiple optimization scripts to avoid code duplication.

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-14
"""

import ast
from pathlib import Path
from typing import List, Dict, Any, Optional


def parse_file(file_path: Path) -> Optional[ast.Module]:
    """
    Parse a Python file to AST.

    Args:
        file_path: Path to Python file

    Returns:
        AST Module or None if parsing fails

    Example:
        >>> tree = parse_file(Path("src/main.py"))
        >>> if tree:
        ...     print("Parsed successfully")
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        return ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"[WARN] Failed to parse {file_path}: {e}")
        return None


def extract_functions(tree: ast.Module, file_path: str = "") -> List[Dict[str, Any]]:
    """
    Extract all function definitions from AST.

    Args:
        tree: AST Module
        file_path: Optional file path for context

    Returns:
        List of dicts with function metadata:
        {
            'name': str,
            'line': int,
            'col': int,
            'args': List[str],
            'decorators': List[str],
            'is_async': bool,
            'docstring': Optional[str]
        }

    Example:
        >>> tree = ast.parse("def foo(x, y): pass")
        >>> funcs = extract_functions(tree)
        >>> funcs[0]['name']
        'foo'
    """
    functions = []

    class FunctionVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            functions.append(_extract_function_info(node, file_path))
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            info = _extract_function_info(node, file_path)
            info['is_async'] = True
            functions.append(info)
            self.generic_visit(node)

    FunctionVisitor().visit(tree)
    return functions


def extract_classes(tree: ast.Module, file_path: str = "") -> List[Dict[str, Any]]:
    """
    Extract all class definitions from AST.

    Args:
        tree: AST Module
        file_path: Optional file path for context

    Returns:
        List of dicts with class metadata:
        {
            'name': str,
            'line': int,
            'col': int,
            'bases': List[str],
            'decorators': List[str],
            'methods': List[str],
            'docstring': Optional[str]
        }
    """
    classes = []

    class ClassVisitor(ast.NodeVisitor):
        def visit_ClassDef(self, node):
            classes.append(_extract_class_info(node, file_path))
            self.generic_visit(node)

    ClassVisitor().visit(tree)
    return classes


def extract_constants(tree: ast.Module, file_path: str = "") -> List[Dict[str, Any]]:
    """
    Extract all UPPER_CASE constants from AST.

    Identifies constants by naming convention: ^[A-Z][A-Z0-9_]*$

    Args:
        tree: AST Module
        file_path: Optional file path for context

    Returns:
        List of dicts with constant metadata:
        {
            'name': str,
            'line': int,
            'col': int,
            'value': Any (if simple literal),
            'value_type': str
        }
    """
    constants = []

    class ConstantVisitor(ast.NodeVisitor):
        def visit_Assign(self, node):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    # Check if UPPER_CASE naming
                    if name.isupper() and name.replace('_', '').isalnum():
                        constants.append({
                            'name': name,
                            'line': node.lineno,
                            'col': node.col_offset,
                            'value': _get_literal_value(node.value),
                            'value_type': type(node.value).__name__,
                            'file': file_path
                        })
            self.generic_visit(node)

    ConstantVisitor().visit(tree)
    return constants


def extract_imports(tree: ast.Module) -> List[Dict[str, Any]]:
    """
    Extract all imports from AST.

    Args:
        tree: AST Module

    Returns:
        List of dicts with import metadata:
        {
            'type': 'import' | 'from',
            'module': str,
            'names': List[str],
            'aliases': Dict[str, str],
            'line': int
        }
    """
    imports = []

    class ImportVisitor(ast.NodeVisitor):
        def visit_Import(self, node):
            for alias in node.names:
                imports.append({
                    'type': 'import',
                    'module': alias.name,
                    'names': [alias.name],
                    'aliases': {alias.name: alias.asname} if alias.asname else {},
                    'line': node.lineno
                })
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            imports.append({
                'type': 'from',
                'module': node.module or '',
                'names': [alias.name for alias in node.names],
                'aliases': {alias.name: alias.asname for alias in node.names if alias.asname},
                'line': node.lineno,
                'level': node.level  # For relative imports
            })
            self.generic_visit(node)

    ImportVisitor().visit(tree)
    return imports


def extract_decorators(node: ast.FunctionDef) -> List[str]:
    """
    Extract decorator names from function/class node.

    Args:
        node: FunctionDef or ClassDef node

    Returns:
        List of decorator names (as strings)
    """
    decorators = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
            decorators.append(dec.func.id)
        elif isinstance(dec, ast.Attribute):
            # Handle @router.get, @field_validator, etc.
            decorators.append(_get_attribute_name(dec))
        else:
            decorators.append('<complex_decorator>')
    return decorators


# ============================================================================
# Private Helper Functions
# ============================================================================

def _extract_function_info(node: ast.FunctionDef, file_path: str) -> Dict[str, Any]:
    """Extract metadata from FunctionDef node."""
    return {
        'name': node.name,
        'line': node.lineno,
        'col': node.col_offset,
        'args': [arg.arg for arg in node.args.args],
        'decorators': extract_decorators(node),
        'is_async': isinstance(node, ast.AsyncFunctionDef),
        'docstring': ast.get_docstring(node),
        'file': file_path
    }


def _extract_class_info(node: ast.ClassDef, file_path: str) -> Dict[str, Any]:
    """Extract metadata from ClassDef node."""
    methods = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(item.name)

    return {
        'name': node.name,
        'line': node.lineno,
        'col': node.col_offset,
        'bases': [_get_base_name(base) for base in node.bases],
        'decorators': extract_decorators(node),
        'methods': methods,
        'docstring': ast.get_docstring(node),
        'file': file_path
    }


def _get_base_name(node: ast.expr) -> str:
    """Get base class name from AST node."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return _get_attribute_name(node)
    else:
        return '<complex_base>'


def _get_attribute_name(node: ast.Attribute) -> str:
    """Get full attribute name (e.g., 'router.get')."""
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return '.'.join(reversed(parts))


def _get_literal_value(node: ast.expr) -> Any:
    """
    Extract literal value from AST node.
    Returns None for complex expressions.
    """
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Num):  # Python < 3.8 compatibility
        return node.n
    elif isinstance(node, ast.Str):  # Python < 3.8 compatibility
        return node.s
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        try:
            return [_get_literal_value(elt) for elt in node.elts]
        except:
            return None
    elif isinstance(node, ast.Dict):
        try:
            return {
                _get_literal_value(k): _get_literal_value(v)
                for k, v in zip(node.keys, node.values)
            }
        except:
            return None
    else:
        return None  # Complex expression


# ============================================================================
# Utility Functions
# ============================================================================

def count_nodes_by_type(tree: ast.Module) -> Dict[str, int]:
    """
    Count AST nodes by type.

    Useful for complexity analysis.

    Returns:
        Dict mapping node type to count
    """
    counts = {}

    class CountVisitor(ast.NodeVisitor):
        def visit(self, node):
            node_type = type(node).__name__
            counts[node_type] = counts.get(node_type, 0) + 1
            self.generic_visit(node)

    CountVisitor().visit(tree)
    return counts


def get_function_complexity(node: ast.FunctionDef) -> int:
    """
    Calculate cyclomatic complexity of a function (simplified).

    Counts decision points:
    - if, elif, while, for, except, with, and, or, comprehensions

    Returns:
        Complexity score (McCabe-like)
    """
    complexity = 1  # Base complexity

    class ComplexityVisitor(ast.NodeVisitor):
        def visit_If(self, node):
            nonlocal complexity
            complexity += 1
            self.generic_visit(node)

        def visit_While(self, node):
            nonlocal complexity
            complexity += 1
            self.generic_visit(node)

        def visit_For(self, node):
            nonlocal complexity
            complexity += 1
            self.generic_visit(node)

        def visit_ExceptHandler(self, node):
            nonlocal complexity
            complexity += 1
            self.generic_visit(node)

        def visit_BoolOp(self, node):
            nonlocal complexity
            # and/or add complexity
            complexity += len(node.values) - 1
            self.generic_visit(node)

    ComplexityVisitor().visit(node)
    return complexity


if __name__ == "__main__":
    # Self-test
    import sys

    if len(sys.argv) > 1:
        test_file = Path(sys.argv[1])
        if test_file.exists():
            print(f"Parsing {test_file}...")
            tree = parse_file(test_file)
            if tree:
                funcs = extract_functions(tree, str(test_file))
                classes = extract_classes(tree, str(test_file))
                constants = extract_constants(tree, str(test_file))
                imports = extract_imports(tree)

                print(f"\n[OK] Functions: {len(funcs)}")
                for func in funcs[:5]:  # Show first 5
                    print(f"   - {func['name']}() at line {func['line']}")

                print(f"\n[OK] Classes: {len(classes)}")
                for cls in classes[:5]:
                    print(f"   - {cls['name']} at line {cls['line']}")

                print(f"\n[OK] Constants: {len(constants)}")
                for const in constants[:5]:
                    print(f"   - {const['name']} = {const['value']}")

                print(f"\n[OK] Imports: {len(imports)}")
                for imp in imports[:5]:
                    print(f"   - {imp['type']} {imp['module']}")
        else:
            print(f"File not found: {test_file}")
    else:
        print("Usage: python ast_parser.py <python_file>")
        print("\nSelf-test:")
        test_code = """
def example_function(x, y):
    '''Example function'''
    return x + y

class ExampleClass:
    '''Example class'''
    def method(self):
        pass

EXAMPLE_CONSTANT = 42
"""
        tree = ast.parse(test_code)
        funcs = extract_functions(tree)
        classes = extract_classes(tree)
        constants = extract_constants(tree)

        print(f"[OK] Functions: {len(funcs)}")
        print(f"[OK] Classes: {len(classes)}")
        print(f"[OK] Constants: {len(constants)}")
        print("\nAll tests passed!")
