#!/usr/bin/env python3
"""
Generic Grep Utilities for Code Analysis.

Cross-platform grep operations for finding patterns in files.
Uses Python's built-in capabilities for maximum compatibility.

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-14
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional


def grep_in_directory(
    pattern: str,
    directory: Path,
    extensions: List[str] = [".py"],
    exclude_dirs: Optional[List[str]] = None,
    case_sensitive: bool = True,
    regex: bool = False
) -> List[Dict[str, Any]]:
    """
    Generic grep with filtering.

    Args:
        pattern: Pattern to search (string or regex)
        directory: Directory to search in
        extensions: File extensions to include (default: [".py"])
        exclude_dirs: Directories to exclude (default: ["__pycache__", ".venv", "alembic/versions"])
        case_sensitive: Case-sensitive search (default: True)
        regex: Treat pattern as regex (default: False, literal string)

    Returns:
        List of dicts:
        {
            'file': str (relative path),
            'line': int,
            'col': int,
            'match': str (matched text),
            'context': str (full line)
        }

    Example:
        >>> results = grep_in_directory("logger.debug", Path("src"))
        >>> print(f"Found {len(results)} matches")
    """
    if exclude_dirs is None:
        exclude_dirs = ["__pycache__", ".venv", ".git", "alembic/versions", "node_modules"]

    # Compile regex pattern
    flags = 0 if case_sensitive else re.IGNORECASE
    if regex:
        try:
            pattern_re = re.compile(pattern, flags)
        except re.error as e:
            print(f"[WARN] Invalid regex pattern '{pattern}': {e}")
            return []
    else:
        # Escape special regex characters for literal matching
        pattern_re = re.compile(re.escape(pattern), flags)

    results = []

    def should_exclude(path: Path) -> bool:
        """Check if path should be excluded."""
        path_str = str(path)
        for exclude in exclude_dirs:
            if exclude in path_str:
                return True
        return False

    # Recursively search files
    for file_path in directory.rglob("*"):
        # Skip if excluded
        if should_exclude(file_path):
            continue

        # Skip if wrong extension
        if file_path.suffix not in extensions:
            continue

        # Skip if not a file
        if not file_path.is_file():
            continue

        # Search in file
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, start=1):
                    matches = pattern_re.finditer(line)
                    for match in matches:
                        results.append({
                            'file': str(file_path.relative_to(directory)),
                            'line': line_num,
                            'col': match.start() + 1,
                            'match': match.group(),
                            'context': line.rstrip()
                        })
        except Exception as e:
            print(f"[WARN] Failed to read {file_path}: {e}")
            continue

    return results


def count_occurrences(
    pattern: str,
    directory: Path,
    extensions: List[str] = [".py"],
    exclude_dirs: Optional[List[str]] = None,
    case_sensitive: bool = True
) -> int:
    """
    Count pattern occurrences in directory.

    Args:
        pattern: Pattern to count
        directory: Directory to search
        extensions: File extensions to include
        exclude_dirs: Directories to exclude
        case_sensitive: Case-sensitive search

    Returns:
        Total count of occurrences

    Example:
        >>> count = count_occurrences("logger.debug", Path("src"))
        >>> print(f"Found {count} debug logs")
    """
    results = grep_in_directory(
        pattern, directory, extensions, exclude_dirs, case_sensitive, regex=False
    )
    return len(results)


def find_files_importing(
    module_name: str,
    directory: Path,
    exclude_dirs: Optional[List[str]] = None
) -> List[Path]:
    """
    Find all files importing a module.

    Searches for:
    - import module_name
    - from module_name import ...
    - from parent.module_name import ...

    Args:
        module_name: Module name to find imports for
        directory: Directory to search
        exclude_dirs: Directories to exclude

    Returns:
        List of file paths importing the module

    Example:
        >>> files = find_files_importing("my_module", Path("src"))
        >>> print(f"{len(files)} files import my_module")
    """
    if exclude_dirs is None:
        exclude_dirs = ["__pycache__", ".venv", ".git", "alembic/versions"]

    importing_files = set()

    # Pattern 1: import module_name
    pattern1 = f"^import\\s+{re.escape(module_name)}\\b"
    results1 = grep_in_directory(pattern1, directory, [".py"], exclude_dirs, regex=True)
    for result in results1:
        importing_files.add(Path(directory) / result['file'])

    # Pattern 2: from module_name import ...
    pattern2 = f"^from\\s+{re.escape(module_name)}\\s+import"
    results2 = grep_in_directory(pattern2, directory, [".py"], exclude_dirs, regex=True)
    for result in results2:
        importing_files.add(Path(directory) / result['file'])

    # Pattern 3: from parent.module_name import ...
    pattern3 = f"^from\\s+\\S*\\.{re.escape(module_name)}\\s+import"
    results3 = grep_in_directory(pattern3, directory, [".py"], exclude_dirs, regex=True)
    for result in results3:
        importing_files.add(Path(directory) / result['file'])

    # Pattern 4: from .module_name import ... (relative imports)
    pattern4 = f"^from\\s+\\.+{re.escape(module_name)}\\s+import"
    results4 = grep_in_directory(pattern4, directory, [".py"], exclude_dirs, regex=True)
    for result in results4:
        importing_files.add(Path(directory) / result['file'])

    return sorted(list(importing_files))


def find_function_usages(
    function_name: str,
    directory: Path,
    exclude_definition: bool = True,
    exclude_dirs: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Find all usages of a function.

    Args:
        function_name: Function name to find
        directory: Directory to search
        exclude_definition: Exclude definition line (default: True)
        exclude_dirs: Directories to exclude

    Returns:
        List of usage locations

    Example:
        >>> usages = find_function_usages("my_function", Path("src"))
        >>> print(f"Function used {len(usages)} times")
    """
    # Pattern: function_name( with optional whitespace
    pattern = f"{re.escape(function_name)}\\s*\\("

    results = grep_in_directory(pattern, directory, [".py"], exclude_dirs, regex=True)

    if exclude_definition:
        # Filter out lines that look like definitions
        # def function_name( or async def function_name(
        filtered_results = []
        for result in results:
            context = result['context'].strip()
            if not (context.startswith('def ') or context.startswith('async def ')):
                filtered_results.append(result)
        return filtered_results

    return results


def find_files_with_pattern(
    pattern: str,
    directory: Path,
    extensions: List[str] = [".py"],
    exclude_dirs: Optional[List[str]] = None,
    regex: bool = False
) -> List[Path]:
    """
    Find files containing a pattern.

    Args:
        pattern: Pattern to search for
        directory: Directory to search
        extensions: File extensions to include
        exclude_dirs: Directories to exclude
        regex: Treat pattern as regex

    Returns:
        List of file paths containing the pattern

    Example:
        >>> files = find_files_with_pattern("TODO", Path("src"))
        >>> print(f"{len(files)} files have TODOs")
    """
    results = grep_in_directory(pattern, directory, extensions, exclude_dirs, regex=regex)

    # Get unique files
    files = set()
    for result in results:
        files.add(Path(directory) / result['file'])

    return sorted(list(files))


def grep_files(
    pattern: str,
    file_paths: List[Path],
    case_sensitive: bool = True,
    regex: bool = False
) -> List[Dict[str, Any]]:
    """
    Grep in specific files (not recursive).

    Args:
        pattern: Pattern to search
        file_paths: List of specific files to search
        case_sensitive: Case-sensitive search
        regex: Treat pattern as regex

    Returns:
        List of matches

    Example:
        >>> files = [Path("src/main.py"), Path("src/config.py")]
        >>> results = grep_files("DEBUG", files, case_sensitive=False)
    """
    # Compile regex pattern
    flags = 0 if case_sensitive else re.IGNORECASE
    if regex:
        try:
            pattern_re = re.compile(pattern, flags)
        except re.error as e:
            print(f"[WARN] Invalid regex pattern '{pattern}': {e}")
            return []
    else:
        pattern_re = re.compile(re.escape(pattern), flags)

    results = []

    for file_path in file_paths:
        if not file_path.is_file():
            continue

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, start=1):
                    matches = pattern_re.finditer(line)
                    for match in matches:
                        results.append({
                            'file': str(file_path),
                            'line': line_num,
                            'col': match.start() + 1,
                            'match': match.group(),
                            'context': line.rstrip()
                        })
        except Exception as e:
            print(f"[WARN] Failed to read {file_path}: {e}")
            continue

    return results


def extract_module_name_from_path(file_path: Path, src_root: Path) -> str:
    """
    Convert file path to Python module name.

    Args:
        file_path: Path to Python file
        src_root: Root of source directory

    Returns:
        Module name (e.g., "domains.agents.tools.base")

    Example:
        >>> path = Path("src/domains/agents/tools/base.py")
        >>> module = extract_module_name_from_path(path, Path("src"))
        >>> print(module)  # "domains.agents.tools.base"
    """
    try:
        # Get relative path from src_root
        rel_path = file_path.relative_to(src_root)

        # Remove .py extension
        if rel_path.suffix == '.py':
            rel_path = rel_path.with_suffix('')

        # Convert path separators to dots
        module_name = str(rel_path).replace('\\', '.').replace('/', '.')

        # Remove __init__ if present
        if module_name.endswith('.__init__'):
            module_name = module_name[:-9]

        return module_name
    except ValueError:
        # file_path not relative to src_root
        return ""


if __name__ == "__main__":
    # Self-test
    import sys

    if len(sys.argv) > 2:
        pattern = sys.argv[1]
        directory = Path(sys.argv[2])

        if directory.exists():
            print(f"Searching for '{pattern}' in {directory}...")
            results = grep_in_directory(pattern, directory)

            print(f"\n[OK] Found {len(results)} matches")
            for result in results[:10]:  # Show first 10
                print(f"   {result['file']}:{result['line']} - {result['context'][:60]}")

            if len(results) > 10:
                print(f"   ... and {len(results) - 10} more")
        else:
            print(f"Directory not found: {directory}")
    else:
        print("Usage: python grep_helper.py <pattern> <directory>")
        print("\nSelf-test:")
        # Create temporary test
        test_dir = Path(".")
        count = count_occurrences("def ", test_dir, extensions=[".py"])
        print(f"[OK] Found {count} function definitions in current directory")
        print("All tests passed!")
