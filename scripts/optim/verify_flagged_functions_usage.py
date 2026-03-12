"""
Phase 5 Manual Review - Automated Usage Verification

This script performs automated usage verification for the 55 flagged functions
from the extreme vigilance analysis.

For each function:
1. Search for direct calls (function_name()
2. Search for method references (.function_name)
3. Search for string references (for dynamic imports/reflection)
4. Check if it's a FastAPI route (should have been caught by safeguards)
5. Generate detailed usage report

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-16
Session: 15 (Phase 5 - Manual Review)
"""

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).parent.parent.parent / "apps" / "api" / "src"

# All 55 flagged functions from UNUSED_CODE_EXTREME_VIGILANCE.md
FLAGGED_FUNCTIONS = [
    ("_read_file_utf8", "main.py"),
    ("readiness_check", "main.py"),
    ("liveness_check", "main.py"),
    ("raise_conversation_not_found", "core\\exceptions.py"),
    ("raise_message_not_found", "core\\exceptions.py"),
    ("raise_connector_already_exists", "core\\exceptions.py"),
    ("raise_google_api_error", "core\\exceptions.py"),
    ("raise_llm_service_error", "core\\exceptions.py"),
    ("transactional", "core\\unit_of_work.py"),
    ("get_sessions", "infrastructure\\cache\\redis.py"),
    ("verify_refresh_token", "infrastructure\\cache\\redis.py"),
    ("delete_oauth_state", "infrastructure\\cache\\redis.py"),
    ("init_db", "infrastructure\\database\\session.py"),
    ("async_wrapper", "infrastructure\\observability\\decorators.py"),  # Multiple instances
    ("sync_wrapper", "infrastructure\\observability\\decorators.py"),  # Multiple instances
    ("add_opentelemetry_context", "infrastructure\\observability\\logging.py"),
    ("parse_agent_result_key", "domains\\agents\\constants.py"),
    ("route_from_router", "domains\\agents\\graph.py"),
    ("route_from_orchestrator", "domains\\agents\\graph.py"),
    ("activate_gmail_connector", "domains\\connectors\\router.py"),
    ("update_connector_config", "domains\\connectors\\router.py"),
    ("update_user_activation_admin", "domains\\users\\router.py"),
    ("delete_user_gdpr_admin", "domains\\users\\router.py"),
    ("anonymize_connector_id", "domains\\connectors\\clients\\google_people_client.py"),
    ("get_confidence", "domains\\agents\\context\\manager.py"),
    ("model_post_init", "domains\\agents\\context\\registry.py"),
    ("reset_tool_context_store", "domains\\agents\\context\\store.py"),
    ("_get_current_datetime_formatted", "domains\\agents\\graphs\\contacts_agent_builder.py"),
    ("approval_gate_node", "domains\\agents\\nodes\\approval_gate_node.py"),
    ("route_from_planner", "domains\\agents\\nodes\\routing.py"),
    ("route_from_approval_gate", "domains\\agents\\nodes\\routing.py"),
    ("has_tool", "domains\\agents\\orchestration\\parallel_executor.py"),
    ("list_tools", "domains\\agents\\orchestration\\parallel_executor.py"),
    ("replace_ref", "domains\\agents\\orchestration\\parallel_executor.py"),  # Multiple files
    ("replacer", "domains\\agents\\orchestration\\plan_executor.py"),
    ("_convert_execution_plan_to_dict", "domains\\agents\\orchestration\\plan_executor.py"),
    ("_request_hitl_approval", "domains\\agents\\orchestration\\plan_executor.py"),
    ("_save_to_store", "domains\\agents\\orchestration\\plan_executor.py"),
    ("matches_keyword", "domains\\agents\\registry\\domain_taxonomy.py"),
    ("export_domain_metadata_for_prompt", "domains\\agents\\registry\\domain_taxonomy.py"),
    ("store_tool_call_mapping", "domains\\agents\\services\\hitl_orchestrator.py"),
    ("validate_and_normalize_list_response", "domains\\agents\\tools\\contacts_validators.py"),
    ("validate_and_normalize_details_response", "domains\\agents\\tools\\contacts_validators.py"),
    ("format_single_response", "domains\\agents\\tools\\formatters.py"),
    ("invalidate_user", "domains\\agents\\utils\\contacts_cache.py"),
    ("is_locked", "domains\\agents\\utils\\oauth_lock.py"),
    ("force_release", "domains\\agents\\utils\\oauth_lock.py"),
    ("format_router_decision", "domains\\agents\\services\\streaming\\service.py"),
    ("health_check", "api\\v1\\routes.py"),
    ("root", "api\\v1\\routes.py"),
    ("get_client_config", "api\\v1\\routes.py"),
]


def search_usage(function_name: str) -> Tuple[int, List[str]]:
    """
    Search for all usages of a function in the codebase.

    Returns:
        (total_count, list of file paths with usage)
    """
    # Pattern: function_name( or .function_name or "function_name" (for string refs)
    patterns = [
        f"{function_name}\\(",  # Direct call
        f"\\.{function_name}",  # Method reference
        f'"{function_name}"',  # String reference
        f"'{function_name}'",  # String reference (single quotes)
    ]

    all_files = set()
    total_count = 0

    for pattern in patterns:
        try:
            result = subprocess.run(
                ["rg", "-l", pattern, str(ROOT)],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                files = result.stdout.strip().split("\n")
                all_files.update([f for f in files if f])

                # Count occurrences
                count_result = subprocess.run(
                    ["rg", "-c", pattern, str(ROOT)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if count_result.returncode == 0:
                    for line in count_result.stdout.strip().split("\n"):
                        if line:
                            try:
                                count = int(line.split(":")[-1])
                                total_count += count
                            except:
                                pass
        except:
            pass

    return total_count, list(all_files)


def check_if_fastapi_route(file_path: str, function_name: str) -> bool:
    """Check if function is a FastAPI route."""
    full_path = ROOT / file_path
    if not full_path.exists():
        return False

    try:
        content = full_path.read_text(encoding="utf-8")

        # Find function definition
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if f"def {function_name}(" in line or f"async def {function_name}(" in line:
                # Check 10 lines before for route decorator
                start = max(0, i - 10)
                context = "\n".join(lines[start:i+1])

                if re.search(r"@(app|router)\.(get|post|put|delete|patch)", context):
                    return True

        return False
    except:
        return False


def analyze_flagged_functions():
    """Analyze all 55 flagged functions."""

    results = {
        "USED": [],
        "FASTAPI_ROUTE": [],
        "MAYBE_UNUSED": [],
        "NOT_FOUND": [],
    }

    for func_name, file_path in FLAGGED_FUNCTIONS:
        print(f"Analyzing {func_name} in {file_path}...")

        # Check if file exists
        full_path = ROOT / file_path
        if not full_path.exists():
            results["NOT_FOUND"].append((func_name, file_path, "File does not exist"))
            continue

        # Check if it's a FastAPI route
        if check_if_fastapi_route(file_path, func_name):
            results["FASTAPI_ROUTE"].append((func_name, file_path, "FastAPI route (should be protected)"))
            continue

        # Search for usage
        count, files = search_usage(func_name)

        if count > 0:
            # Filter out self-definition
            filtered_files = [f for f in files if file_path not in f]

            if filtered_files:
                results["USED"].append((func_name, file_path, f"Used {count} times in {len(filtered_files)} files"))
            else:
                results["MAYBE_UNUSED"].append((func_name, file_path, f"Only self-definition found"))
        else:
            results["MAYBE_UNUSED"].append((func_name, file_path, "No usage found"))

    return results


def generate_report(results: Dict):
    """Generate markdown report of manual review."""
    report = []
    report.append("# Phase 5 - Manual Review Results\n")
    report.append("**Date** : 2025-11-16\n")
    report.append("**Scope** : 55 flagged functions\n")
    report.append("**Analysis** : Automated usage verification\n")
    report.append("\n---\n")

    report.append("## Summary\n\n")
    report.append(f"**Total analyzed** : {len(FLAGGED_FUNCTIONS)}\n")
    report.append(f"**USED (keep)** : {len(results['USED'])}\n")
    report.append(f"**FASTAPI_ROUTE (keep)** : {len(results['FASTAPI_ROUTE'])}\n")
    report.append(f"**MAYBE_UNUSED (review)** : {len(results['MAYBE_UNUSED'])}\n")
    report.append(f"**NOT_FOUND (already deleted)** : {len(results['NOT_FOUND'])}\n")
    report.append("\n")

    # Detail each category
    for category, items in sorted(results.items()):
        if not items:
            continue

        report.append(f"## {category} ({len(items)} items)\n\n")

        for func, file, reason in items:
            report.append(f"- `{func}()` - {file}\n")
            report.append(f"  - {reason}\n")

        report.append("\n")

    report.append("---\n")
    report.append("**Report Generated** : 2025-11-16\n")
    report.append("**Recommendation** : Review MAYBE_UNUSED items manually\n")

    return "".join(report)


def main():
    """Main entry point."""
    print("Starting Phase 5 Manual Review...")
    print()

    results = analyze_flagged_functions()

    print()
    print("Analysis complete!")
    print()
    print("Summary:")
    for category, items in results.items():
        print(f"  {category}: {len(items)} items")

    # Generate report
    report = generate_report(results)
    output_path = Path(__file__).parent.parent.parent / "docs" / "optim" / "PHASE_5_MANUAL_REVIEW.md"
    output_path.write_text(report, encoding="utf-8")
    print()
    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    main()
