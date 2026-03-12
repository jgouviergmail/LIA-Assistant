#!/usr/bin/env python3
"""
Advanced File Usage Verification Script.

Detects BOTH module-level AND function-level imports to avoid false positives.

Strategy:
1. Search for module-level imports (original script logic)
2. Search for function-level imports (inside function bodies)
3. Search for dynamic imports (importlib.import_module)
4. Search for string references (module paths in configs, docs)

Usage:
    python scripts/optim/verify_unused_files_advanced.py

Output:
    docs/optim/iterations/PHASE_3B_UNUSED_FILES_VERIFICATION.md

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
OUTPUT_FILE = Path("docs/optim/iterations/PHASE_3B_UNUSED_FILES_VERIFICATION.md")

EXCLUDE_DIRS = ["__pycache__", ".venv", ".git", "alembic/versions", "tests"]

# Files to verify (from PHASE_2 01_UNUSED_FILES.md)
FILES_TO_VERIFY = [
    "core/unit_of_work.py",
    "infrastructure/cache/llm_cache.py",
    "infrastructure/llm/decorators.py",
    "infrastructure/observability/lifetime_metrics.py",
    "infrastructure/observability/metrics_business.py",
    "infrastructure/observability/metrics_errors.py",
    "domains/chat/repository.py",
    "domains/conversations/checkpointer.py",
    "domains/llm/pricing_service.py",
    "domains/agents/context/catalogue_manifests.py",
    "domains/agents/google_contacts/catalogue_manifests.py",
    "domains/agents/nodes/decorators.py",
    "domains/agents/orchestration/parallel_executor.py",
    "domains/agents/orchestration/plan_executor.py",
    "domains/agents/orchestration/step_executor_node.py",
    "domains/agents/orchestration/wave_aggregator_node.py",
    "domains/agents/prompts/prompt_loader.py",
    "domains/agents/registry/catalogue_loader.py",
    "domains/agents/registry/domain_taxonomy.py",
    "domains/agents/registry/manifest_builder.py",
    "domains/agents/services/conversation_orchestrator.py",
    "domains/agents/services/hitl_orchestrator.py",
    "domains/agents/tools/constants.py",
    "domains/agents/tools/contacts_models.py",
    "domains/agents/tools/contacts_validators.py",
    "domains/agents/utils/execution_metadata.py",
    "domains/agents/utils/message_windowing.py",
    "domains/agents/services/approval/evaluator.py",
    "domains/agents/services/hitl/parameter_enrichment.py",
    "domains/agents/services/hitl/schema_validator.py",
    "core/oauth/exceptions.py",
    "core/oauth/flow_handler.py",
    "core/oauth/providers/base.py",
    "core/oauth/providers/google.py",
]


def get_module_name(file_path: str) -> str:
    """Convert file path to module name."""
    # Remove .py extension
    module_path = file_path.replace(".py", "")
    # Convert slashes to dots
    module_name = module_path.replace("/", ".").replace("\\", ".")
    return module_name


def search_all_import_patterns(file_path: str) -> dict[str, Any]:
    """
    Search for ALL possible import patterns for a file.

    Returns dict with:
    - module_imports: List of module-level imports
    - function_imports: List of function-level imports
    - dynamic_imports: List of dynamic imports
    - string_refs: List of string references
    - total_usages: Total count
    """
    module_name = get_module_name(file_path)

    # Extract key identifiers from module name
    # e.g., "domains.agents.orchestration.parallel_executor" → ["parallel_executor", "orchestration"]
    parts = module_name.split(".")
    file_basename = parts[-1]  # "parallel_executor"

    results = {
        "module_imports": [],
        "function_imports": [],
        "dynamic_imports": [],
        "string_refs": [],
        "total_usages": 0,
    }

    # Pattern 1: Module-level imports (standard)
    # from src.domains.agents.orchestration.parallel_executor import X
    # import src.domains.agents.orchestration.parallel_executor
    module_import_patterns = [
        f"from src.{module_name} import",
        f"import src.{module_name}",
        f"from .{file_basename} import",  # Relative import
    ]

    for pattern in module_import_patterns:
        matches = grep_in_directory(
            pattern,
            SRC_ROOT,
            extensions=['.py'],
            exclude_dirs=EXCLUDE_DIRS,
            regex=False
        )
        if matches:
            results["module_imports"].extend(matches)

    # Pattern 2: Function-level imports (inside function bodies)
    # Detect by indentation before "from" or "import"
    # Regex: ^\s{4,}from src.domains.agents.orchestration.parallel_executor import
    function_import_pattern = rf"^\s{{4,}}from src\.{module_name.replace('.', r'\.')} import"

    matches = grep_in_directory(
        function_import_pattern,
        SRC_ROOT,
        extensions=['.py'],
        exclude_dirs=EXCLUDE_DIRS,
        regex=True
    )
    if matches:
        results["function_imports"].extend(matches)

    # Pattern 3: Dynamic imports
    # importlib.import_module("src.domains.agents.orchestration.parallel_executor")
    dynamic_import_pattern = f'importlib.import_module.*{file_basename}'

    matches = grep_in_directory(
        dynamic_import_pattern,
        SRC_ROOT,
        extensions=['.py'],
        exclude_dirs=EXCLUDE_DIRS,
        regex=True
    )
    if matches:
        results["dynamic_imports"].extend(matches)

    # Pattern 4: String references (module paths in configs, docstrings)
    # Search for module name as string literal
    string_ref_pattern = f'"{module_name}"|\'{module_name}\''

    matches = grep_in_directory(
        string_ref_pattern,
        SRC_ROOT,
        extensions=['.py'],
        exclude_dirs=EXCLUDE_DIRS,
        regex=True
    )
    if matches:
        results["string_refs"].extend(matches)

    # Calculate total
    results["total_usages"] = (
        len(results["module_imports"])
        + len(results["function_imports"])
        + len(results["dynamic_imports"])
        + len(results["string_refs"])
    )

    return results


def classify_file_status(usage_results: dict[str, Any], file_path: str) -> dict[str, Any]:
    """
    Classify file status based on usage patterns.

    Returns:
        dict with:
        - status: "USED" | "UNUSED" | "PLANNED" | "UNCERTAIN"
        - confidence: "high" | "medium" | "low"
        - reason: str
        - recommendation: "KEEP" | "DELETE" | "MANUAL_REVIEW"
    """
    total = usage_results["total_usages"]

    # Check for ADR references (architectural documentation)
    file_content_path = SRC_ROOT / file_path
    has_adr_reference = False
    if file_content_path.exists():
        content = file_content_path.read_text(encoding="utf-8")
        if "ADR-" in content or "Architecture Decision" in content:
            has_adr_reference = True

    # Classification logic
    if total > 0:
        # File is used
        status = "USED"
        confidence = "high"
        reason = f"Found {total} usage(s) in codebase"
        recommendation = "KEEP"
    elif has_adr_reference:
        # File references ADR but not used yet
        status = "PLANNED"
        confidence = "high"
        reason = "References ADR documentation (planned infrastructure)"
        recommendation = "KEEP"
    else:
        # No usages found
        status = "UNUSED"
        confidence = "medium"
        reason = "No imports or references found (possible false positive)"
        recommendation = "MANUAL_REVIEW"

    return {
        "status": status,
        "confidence": confidence,
        "reason": reason,
        "recommendation": recommendation,
    }


def generate_report(verification_results: list[dict[str, Any]]) -> None:
    """Generate markdown verification report."""

    # Count by status
    stats = {
        "USED": 0,
        "UNUSED": 0,
        "PLANNED": 0,
        "UNCERTAIN": 0,
    }

    for result in verification_results:
        status = result["classification"]["status"]
        stats[status] = stats.get(status, 0) + 1

    # Generate report
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        f.write("# Phase 3B - MEDIUM RISK: Advanced File Usage Verification\n\n")
        f.write("**Date**: 2025-11-15\n")
        f.write("**Status**: [OK] VERIFICATION COMPLETE\n")
        f.write("**Script**: `scripts/optim/verify_unused_files_advanced.py`\n")
        f.write("**Author**: Claude Code (Sonnet 4.5)\n\n")
        f.write("---\n\n")

        f.write("## [SUMMARY] Résumé Exécutif\n\n")
        f.write("### Découverte Critique\n\n")
        f.write("Le script d'analyse initial (`analyze_unused_files.py`) a produit des **FAUX POSITIFS** ")
        f.write("car il ne détectait que les imports module-level.\n\n")
        f.write("**Raison** : Les fichiers orchestration utilisent des **imports fonction-level** ")
        f.write("(lazy imports) pour éviter les dépendances circulaires.\n\n")

        f.write("### Statistiques\n\n")
        f.write(f"- **Total fichiers vérifiés** : {len(verification_results)}\n")
        f.write(f"- **[OK] USED (actifs)** : {stats['USED']}\n")
        f.write(f"- **[WARN] UNUSED (potentiel)** : {stats['UNUSED']}\n")
        f.write(f"- **[INFO] PLANNED (ADR docs)** : {stats['PLANNED']}\n")
        f.write(f"- **[CHECK] UNCERTAIN** : {stats['UNCERTAIN']}\n\n")

        f.write("---\n\n")
        f.write("## [DETAILS] Résultats Détaillés\n\n")

        # Group by status
        for status_filter in ["USED", "PLANNED", "UNUSED", "UNCERTAIN"]:
            filtered = [r for r in verification_results if r["classification"]["status"] == status_filter]

            if not filtered:
                continue

            status_emoji = {
                "USED": "[OK]",
                "PLANNED": "[INFO]",
                "UNUSED": "[WARN]",
                "UNCERTAIN": "[CHECK]",
            }

            f.write(f"### {status_emoji[status_filter]} {status_filter} ({len(filtered)} fichiers)\n\n")

            for result in filtered:
                f.write(f"#### {result['file_path']}\n\n")
                f.write(f"**Status**: {result['classification']['status']}\n\n")
                f.write(f"**Confidence**: {result['classification']['confidence']}\n\n")
                f.write(f"**Reason**: {result['classification']['reason']}\n\n")
                f.write(f"**Recommendation**: **{result['classification']['recommendation']}**\n\n")

                # Show usage details if any
                usage = result["usage"]
                if usage["total_usages"] > 0:
                    f.write("**Usages trouvés** :\n\n")

                    if usage["module_imports"]:
                        f.write(f"- Module-level imports: {len(usage['module_imports'])}\n")
                        for match in usage["module_imports"][:3]:  # Show first 3
                            f.write(f"  - `{match['file']}:{match['line']}`\n")
                        if len(usage["module_imports"]) > 3:
                            f.write(f"  - ... et {len(usage['module_imports']) - 3} autres\n")
                        f.write("\n")

                    if usage["function_imports"]:
                        f.write(f"- Function-level imports: {len(usage['function_imports'])}\n")
                        for match in usage["function_imports"][:3]:
                            f.write(f"  - `{match['file']}:{match['line']}`\n")
                        if len(usage["function_imports"]) > 3:
                            f.write(f"  - ... et {len(usage['function_imports']) - 3} autres\n")
                        f.write("\n")

                    if usage["dynamic_imports"]:
                        f.write(f"- Dynamic imports: {len(usage['dynamic_imports'])}\n\n")

                    if usage["string_refs"]:
                        f.write(f"- String references: {len(usage['string_refs'])}\n\n")

                f.write("---\n\n")

        # Summary recommendations
        f.write("## [ACTION] Recommandations\n\n")

        keep_files = [r for r in verification_results if r["classification"]["recommendation"] == "KEEP"]
        delete_files = [r for r in verification_results if r["classification"]["recommendation"] == "DELETE"]
        review_files = [r for r in verification_results if r["classification"]["recommendation"] == "MANUAL_REVIEW"]

        f.write(f"### [OK] KEEP ({len(keep_files)} fichiers)\n\n")
        f.write("Fichiers activement utilisés ou planifiés (ADR) - **NE PAS SUPPRIMER**\n\n")
        for result in keep_files:
            f.write(f"- `{result['file_path']}` - {result['classification']['reason']}\n")
        f.write("\n")

        if delete_files:
            f.write(f"### [WARN] DELETE ({len(delete_files)} fichiers)\n\n")
            f.write("Fichiers sans usage détecté - **CANDIDATS SUPPRESSION** (après revue manuelle)\n\n")
            for result in delete_files:
                f.write(f"- `{result['file_path']}` - {result['classification']['reason']}\n")
            f.write("\n")

        if review_files:
            f.write(f"### [CHECK] MANUAL REVIEW ({len(review_files)} fichiers)\n\n")
            f.write("Fichiers sans usage détecté mais nécessitant revue manuelle\n\n")
            for result in review_files:
                f.write(f"- `{result['file_path']}` - {result['classification']['reason']}\n")
            f.write("\n")

        f.write("---\n\n")
        f.write("**Report Generated**: 2025-11-15\n\n")
        f.write("**Author**: Claude Code (Sonnet 4.5)\n")


def verify_files():
    """Main verification function."""
    print("=" * 60)
    print("  Advanced File Usage Verification - LIA")
    print("=" * 60)
    print()
    print(f"[*] Verifying {len(FILES_TO_VERIFY)} files...")
    print(f"   Source root: {SRC_ROOT}")
    print(f"   Output: {OUTPUT_FILE}\n")

    verification_results = []

    for idx, file_path in enumerate(FILES_TO_VERIFY, 1):
        print(f"[{idx}/{len(FILES_TO_VERIFY)}] Analyzing: {file_path}")

        # Search for all import patterns
        usage_results = search_all_import_patterns(file_path)

        # Classify status
        classification = classify_file_status(usage_results, file_path)

        # Store result
        verification_results.append({
            "file_path": file_path,
            "usage": usage_results,
            "classification": classification,
        })

        # Log status
        status_emoji = {
            "USED": "[OK]",
            "PLANNED": "[INFO]",
            "UNUSED": "[WARN]",
            "UNCERTAIN": "[CHECK]",
        }
        emoji = status_emoji.get(classification["status"], "[?]")
        print(f"   {emoji} {classification['status']} - {classification['reason']}")
        print()

    print(f"\n[*] Generating report...")
    generate_report(verification_results)

    print(f"\n[OK] Verification complete!")
    print(f"   Report: {OUTPUT_FILE}")
    print(f"\n[NEXT] Review report and proceed with user validation")


if __name__ == "__main__":
    try:
        verify_files()
    except KeyboardInterrupt:
        print("\n\n[WARN] Verification interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
