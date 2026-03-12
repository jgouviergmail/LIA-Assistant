#!/usr/bin/env python3
"""
Advanced Unused Code Verification Script.

Strategy:
1. Detect FastAPI endpoints (decorators: @app.get, @router.post, etc.)
2. Detect FastAPI dependencies (Depends() injections)
3. Detect middleware (dispatch methods in middleware classes)
4. Detect LangGraph nodes (graph.add_node() registrations)
5. Detect Pydantic hooks (__post_init__, model_post_init)
6. Detect decorator usage (@decorator patterns)

Usage:
    python scripts/optim/verify_unused_code_advanced.py

Output:
    docs/optim/iterations/PHASE_3C_UNUSED_CODE_VERIFICATION.md

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-15
"""

import sys
import re
from pathlib import Path
from typing import Any

# Add utils to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "utils"))

from grep_helper import grep_in_directory

# Configuration
SRC_ROOT = Path("apps/api/src")
OUTPUT_FILE = Path("docs/optim/iterations/PHASE_3C_UNUSED_CODE_VERIFICATION.md")

EXCLUDE_DIRS = ["__pycache__", ".venv", ".git", "alembic/versions", "tests"]

# Load findings from 02_UNUSED_CODE.md
FINDINGS_FILE = Path("docs/optim/02_UNUSED_CODE.md")


def parse_findings() -> list[dict[str, str]]:
    """Parse findings from 02_UNUSED_CODE.md."""
    findings = []

    if not FINDINGS_FILE.exists():
        print(f"[ERROR] Findings file not found: {FINDINGS_FILE}")
        return findings

    with FINDINGS_FILE.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    # Parse table (skip header)
    in_table = False
    for line in lines:
        if line.startswith("| Élément"):
            in_table = True
            continue
        if in_table and line.startswith("|"):
            # Parse table row
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:
                element = parts[1]
                location = parts[2]
                confidence = parts[3]

                if element and location and confidence and element != "---":
                    findings.append({
                        "element": element,
                        "location": location,
                        "confidence": confidence
                    })

    return findings


def classify_finding(finding: dict[str, str]) -> dict[str, Any]:
    """
    Classify finding based on pattern detection.

    Returns:
        dict with:
        - status: "USED" | "UNUSED" | "UNCERTAIN"
        - confidence: "high" | "medium" | "low"
        - reason: str
        - pattern: str (FastAPI endpoint, Middleware, Node, etc.)
    """
    element = finding["element"]
    location = finding["location"]

    # Extract function/class name
    if element.startswith("class "):
        name = element.replace("class ", "").strip()
        is_class = True
    else:
        name = element.replace("()", "").strip()
        is_class = False

    # Pattern 1: FastAPI endpoints (@app.get, @router.post, etc.)
    if location.endswith("router.py") or location == "main.py":
        # Check for decorator above function
        file_path = SRC_ROOT / location.split(":")[0]
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")

            # Search for @app.XXX or @router.XXX decorator
            endpoint_pattern = rf'@(app|router)\.(get|post|put|delete|patch).*\n.*def {name}\('
            if re.search(endpoint_pattern, content, re.MULTILINE):
                return {
                    "status": "USED",
                    "confidence": "high",
                    "reason": "FastAPI endpoint (decorator-based routing)",
                    "pattern": "FastAPI Endpoint"
                }

    # Pattern 2: FastAPI dependencies (Depends() injection)
    if name in ["get_db", "get_session_store", "get_current_verified_session",
                "get_current_superuser_session", "get_optional_session"]:
        # Search for Depends(function_name) usage
        pattern = rf"Depends\({name}\)"
        results = grep_in_directory(
            pattern,
            SRC_ROOT,
            extensions=['.py'],
            exclude_dirs=EXCLUDE_DIRS,
            regex=True
        )
        if results:
            return {
                "status": "USED",
                "confidence": "high",
                "reason": f"FastAPI dependency injection ({len(results)} usages)",
                "pattern": "Dependency Injection"
            }

    # Pattern 3: Middleware dispatch() methods
    if name == "dispatch" and "middleware.py" in location:
        return {
            "status": "USED",
            "confidence": "high",
            "reason": "Middleware dispatch() called automatically by FastAPI",
            "pattern": "Middleware"
        }

    # Pattern 4: LangGraph nodes (planner_node, response_node, etc.)
    if name.endswith("_node"):
        # Search for graph.add_node() or Send() usage
        patterns = [
            rf"add_node\(['\"].*?['\"],\s*{name}\)",
            rf"Send\(['\"].*?['\"],.*?{name}\)",
            rf'"{name}"',  # Node name as string
        ]
        for pattern in patterns:
            results = grep_in_directory(
                pattern,
                SRC_ROOT,
                extensions=['.py'],
                exclude_dirs=EXCLUDE_DIRS,
                regex=True
            )
            if results:
                return {
                    "status": "USED",
                    "confidence": "high",
                    "reason": f"LangGraph node registration ({len(results)} refs)",
                    "pattern": "LangGraph Node"
                }

    # Pattern 5: Pydantic hooks
    if name in ["__post_init__", "model_post_init", "__getattr__"]:
        return {
            "status": "USED",
            "confidence": "high",
            "reason": "Pydantic/dataclass hook (called automatically)",
            "pattern": "Pydantic Hook"
        }

    # Pattern 6: Callback methods (on_llm_end, on_llm_error, etc.)
    if name.startswith("on_"):
        if "callbacks.py" in location or "observability" in location:
            return {
                "status": "USED",
                "confidence": "high",
                "reason": "LangChain callback (invoked by framework)",
                "pattern": "LangChain Callback"
            }

    # Pattern 7: Decorator functions (decorator, wrapper patterns)
    if name in ["decorator", "async_wrapper", "sync_wrapper"]:
        # These are internal to decorator implementations
        return {
            "status": "USED",
            "confidence": "medium",
            "reason": "Decorator implementation (internal pattern)",
            "pattern": "Decorator Pattern"
        }

    # Pattern 8: Pydantic model classes
    if is_class:
        # Search for class usage (inheritance, type hints, etc.)
        patterns = [
            rf":\s*{name}",  # Type hint
            rf"\[{name}\]",  # Generic type
            rf"{name}\(",    # Instantiation
            rf"-> {name}",   # Return type
        ]
        total_refs = 0
        for pattern in patterns:
            results = grep_in_directory(
                pattern,
                SRC_ROOT,
                extensions=['.py'],
                exclude_dirs=EXCLUDE_DIRS,
                regex=True
            )
            total_refs += len(results)

        if total_refs > 0:
            return {
                "status": "USED",
                "confidence": "high",
                "reason": f"Pydantic model ({total_refs} type refs)",
                "pattern": "Pydantic Model"
            }

    # Pattern 9: FastAPI endpoint metrics
    if name == "metrics_endpoint":
        return {
            "status": "USED",
            "confidence": "high",
            "reason": "Metrics endpoint (Prometheus /metrics)",
            "pattern": "Prometheus Endpoint"
        }

    # Pattern 10: Routing functions
    if name.startswith("route_from_"):
        # LangGraph routing functions
        patterns = [
            rf"add_conditional_edges.*{name}",
            rf'"{name}"',  # Function name as string
        ]
        for pattern in patterns:
            results = grep_in_directory(
                pattern,
                SRC_ROOT,
                extensions=['.py'],
                exclude_dirs=EXCLUDE_DIRS,
                regex=True
            )
            if results:
                return {
                    "status": "USED",
                    "confidence": "high",
                    "reason": f"LangGraph routing function ({len(results)} refs)",
                    "pattern": "LangGraph Routing"
                }

    # Default: UNCERTAIN (needs manual review)
    return {
        "status": "UNCERTAIN",
        "confidence": "low",
        "reason": "No pattern detected - manual review required",
        "pattern": "Unknown"
    }


def verify_findings():
    """Main verification function."""
    print("=" * 60)
    print("  Advanced Unused Code Verification - LIA")
    print("=" * 60)
    print()

    findings = parse_findings()
    print(f"[*] Loaded {len(findings)} findings from {FINDINGS_FILE}")
    print()

    results = {
        "USED": [],
        "UNUSED": [],
        "UNCERTAIN": [],
    }

    for idx, finding in enumerate(findings, 1):
        print(f"[{idx}/{len(findings)}] Analyzing: {finding['element']}")

        classification = classify_finding(finding)
        status = classification["status"]

        result = {
            **finding,
            **classification
        }
        results[status].append(result)

        emoji = {"USED": "[OK]", "UNUSED": "[WARN]", "UNCERTAIN": "[CHECK]"}
        print(f"   {emoji[status]} {status} - {classification['pattern']} - {classification['reason']}")

    print(f"\n[*] Verification complete!")
    print(f"   USED: {len(results['USED'])}")
    print(f"   UNUSED: {len(results['UNUSED'])}")
    print(f"   UNCERTAIN: {len(results['UNCERTAIN'])}")

    return results


def generate_report(results: dict[str, list[dict[str, Any]]]) -> None:
    """Generate markdown report."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    total = sum(len(v) for v in results.values())

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        f.write("# Phase 3C - MEDIUM RISK: Unused Code Verification\n\n")
        f.write("**Date**: 2025-11-15\n")
        f.write("**Status**: [OK] VERIFICATION COMPLETE\n")
        f.write("**Script**: `scripts/optim/verify_unused_code_advanced.py`\n")
        f.write("**Author**: Claude Code (Sonnet 4.5)\n\n")
        f.write("---\n\n")

        f.write("## [SUMMARY] Résumé Exécutif\n\n")
        f.write("### Découverte Critique\n\n")
        f.write("Le script d'analyse initial (`analyze_unused_code.py`) a produit des **FAUX POSITIFS** ")
        f.write("car il ne détectait que les appels directs de fonctions.\n\n")
        f.write("**Raison** : Beaucoup de fonctions sont utilisées via :\n")
        f.write("- FastAPI decorators (`@app.get`, `@router.post`)\n")
        f.write("- Dependency injection (`Depends()`)\n")
        f.write("- LangGraph registrations (`add_node()`, `Send()`)\n")
        f.write("- Framework callbacks (`on_llm_end`, `dispatch`)\n")
        f.write("- Pydantic hooks (`__post_init__`, `model_post_init`)\n\n")

        f.write("### Statistiques\n\n")
        f.write(f"- **Total éléments vérifiés** : {total}\n")
        f.write(f"- **[OK] USED (actifs)** : {len(results['USED'])} ({len(results['USED'])*100//total}%)\n")
        f.write(f"- **[WARN] UNUSED (vraiment inutilisés)** : {len(results['UNUSED'])} ({len(results['UNUSED'])*100//total if total > 0 else 0}%)\n")
        f.write(f"- **[CHECK] UNCERTAIN (revue manuelle)** : {len(results['UNCERTAIN'])} ({len(results['UNCERTAIN'])*100//total if total > 0 else 0}%)\n\n")

        f.write("---\n\n")

        # USED section
        if results["USED"]:
            f.write(f"## [OK] USED ({len(results['USED'])} éléments)\n\n")

            # Group by pattern
            by_pattern = {}
            for item in results["USED"]:
                pattern = item["pattern"]
                if pattern not in by_pattern:
                    by_pattern[pattern] = []
                by_pattern[pattern].append(item)

            for pattern, items in sorted(by_pattern.items()):
                f.write(f"### {pattern} ({len(items)} items)\n\n")
                for item in items[:10]:  # Show first 10
                    f.write(f"- **{item['element']}** - `{item['location']}` - {item['reason']}\n")
                if len(items) > 10:
                    f.write(f"- ... et {len(items) - 10} autres\n")
                f.write("\n")

        # UNUSED section
        if results["UNUSED"]:
            f.write(f"## [WARN] UNUSED ({len(results['UNUSED'])} éléments)\n\n")
            f.write("Vraiment inutilisés - **CANDIDATS SUPPRESSION** (après revue manuelle)\n\n")
            for item in results["UNUSED"]:
                f.write(f"- **{item['element']}** - `{item['location']}` - {item['reason']}\n")
            f.write("\n")

        # UNCERTAIN section
        if results["UNCERTAIN"]:
            f.write(f"## [CHECK] UNCERTAIN ({len(results['UNCERTAIN'])} éléments)\n\n")
            f.write("Nécessitent revue manuelle\n\n")

            for item in results["UNCERTAIN"]:
                f.write(f"### {item['element']}\n\n")
                f.write(f"**Location**: `{item['location']}`\n\n")
                f.write(f"**Confidence**: {item['confidence']}\n\n")
                f.write(f"**Reason**: {item['reason']}\n\n")
                f.write("---\n\n")

        f.write("---\n\n")
        f.write("**Report Generated**: 2025-11-15\n\n")
        f.write("**Author**: Claude Code (Sonnet 4.5)\n")

    print(f"\n[OK] Report generated: {OUTPUT_FILE}")


if __name__ == "__main__":
    try:
        results = verify_findings()
        generate_report(results)
    except KeyboardInterrupt:
        print("\n\n[WARN] Verification interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
