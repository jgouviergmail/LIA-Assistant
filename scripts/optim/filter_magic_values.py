#!/usr/bin/env python3
"""
Magic Values Intelligent Filtering Script.

Strategy:
1. Categorize magic values by type (log messages, field names, constants, etc.)
2. Filter out false positives (log messages, docstrings, test data)
3. Identify real candidates for centralization
4. Prioritize by impact (usage count × complexity)

Usage:
    python scripts/optim/filter_magic_values.py

Output:
    docs/optim/iterations/PHASE_4_MAGIC_VALUES_FILTERED.md

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-15
"""

import re
from pathlib import Path
from typing import Any
from collections import defaultdict

# Configuration
FINDINGS_FILE = Path("docs/optim/08_MISSING_CONSTANTS.md")
OUTPUT_FILE = Path("docs/optim/iterations/PHASE_4_MAGIC_VALUES_FILTERED.md")

# Patterns to EXCLUDE (false positives)
EXCLUDE_PATTERNS = [
    # Log/debug messages
    r'^\s*•\s',  # Bullet points in docs
    r'^Recommended:\s',  # Config recommendations
    r'^Keywords:\s',  # Metadata descriptions
    r'^, description=',  # Pydantic field descriptions

    # Test data
    r'^user123$', r'^sess456$', r'^conv_123$', r'^people/c123$',  # Test IDs
    r'^John$', r'^oui$', r'^2ème$', r'^premier$',  # Test strings

    # Encoding/formatting
    r'^utf-8$', r'^bearer$', r'^frozen$',  # Standard values

    # Model names (intentional configuration)
    r'^gpt-4.1-mini$', r'^gpt-4\.1-mini$',  # OpenAI models

    # Provider names (intentional)
    r'^openai$',  # LLM provider

    # Status/action enums (might be centralized already)
    r'^success$', r'^error$', r'^done$', r'^unknown$',  # Generic statuses
    r'^APPROVE$', r'^EDIT$', r'^approve$',  # HITL actions
    r'^PUBLIC$', r'^CONFIDENTIAL$',  # Access levels
    r'^sequential$', r'^auto$', r'^true$',  # Modes
]

# Categories to INCLUDE (high-priority candidates)
INCLUDE_CATEGORIES = {
    'field_names': [
        # Database/model field names (high priority)
        r'^user_id$', r'^session_id$', r'^thread_id$', r'^conversation_id$',
        r'^run_id$', r'^turn_id$', r'^step_id$', r'^wave_id$', r'^plan_id$',
        r'^agent_name$', r'^agent_type$', r'^node_name$', r'^tool_name$',
        r'^status$', r'^role$', r'^content$', r'^query$', r'^output$',
        r'^resource_name$', r'^connector_type$', r'^error_code$', r'^error_type$',
        r'^tokens_in$', r'^tokens_out$', r'^tokens_cache$', r'^cost_eur$',
        r'^created_at$', r'^cached_at$', r'^timestamp$', r'^is_active$',
        r'^message_count$', r'^total_count$', r'^total$',
    ],
    'tool_names': [
        # LangGraph/agent tool names
        r'_tool$',  # Ends with _tool
        r'^search_contacts$', r'^list_contacts$', r'^get_contact_details$',
        r'^get_context_state$', r'^resolve_reference$', r'^set_current_item$',
    ],
    'node_names': [
        # LangGraph node names
        r'^task_orchestrator$', r'^approval_gate$', r'^router_decision$',
        r'^plan_approval$', r'^gmail_agent$',
    ],
    'state_keys': [
        # LangGraph state keys
        r'^agent_results$', r'^routing_history$', r'^completed_steps$',
        r'^action_requests$', r'^current_turn_id$', r'^message_metadata$',
        r'^router_system_prompt$', r'^last_query$', r'^current_item$',
        r'^data_source$', r'^rejection_reason$', r'^step_index$',
    ],
    'llm_config_keys': [
        # LLM configuration keys
        r'^temperature$', r'^top_p$', r'^max_tokens$',
        r'^frequency_penalty$', r'^presence_penalty$', r'^reasoning_effort$',
    ],
    'type_names': [
        # JSON schema types
        r'^string$', r'^integer$', r'^boolean$', r'^array$',
        r'^object$', r'^number$',
    ],
}


def parse_magic_values_report() -> list[dict[str, Any]]:
    """Parse magic values from 08_MISSING_CONSTANTS.md."""
    findings = []

    if not FINDINGS_FILE.exists():
        print(f"[ERROR] Findings file not found: {FINDINGS_FILE}")
        return findings

    with FINDINGS_FILE.open("r", encoding="utf-8") as f:
        content = f.read()

    # Parse table (| Element | Location | Confidence | Reason |)
    # Skip until we find the table
    lines = content.split('\n')
    in_table = False

    for line in lines:
        if line.startswith("| Élément") or line.startswith("| Element"):
            in_table = True
            continue

        if not in_table:
            continue

        # Stop at end of table (## heading)
        if line.startswith("##"):
            break

        if line.startswith("|") and not line.startswith("|---"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 5:
                element = parts[1]
                location = parts[2]
                confidence = parts[3]
                reason = parts[4]

                if element and element not in ["Élément", "Element", ""]:
                    # Extract value (remove quotes if present)
                    value = element.strip('"')

                    # Extract occurrence count from reason
                    match = re.search(r'(\d+) occurrence', reason)
                    occurrences = int(match.group(1)) if match else 1

                    findings.append({
                        "value": value,
                        "location": location,
                        "confidence": confidence,
                        "reason": reason,
                        "occurrences": occurrences,
                    })

    return findings


def should_exclude(value: str) -> tuple[bool, str]:
    """Check if value matches exclusion patterns."""
    for pattern in EXCLUDE_PATTERNS:
        if re.match(pattern, value):
            return True, f"Excluded: {pattern}"
    return False, ""


def categorize_value(value: str) -> tuple[str | None, str]:
    """Categorize magic value by type."""
    for category, patterns in INCLUDE_CATEGORIES.items():
        for pattern in patterns:
            if re.match(pattern, value):
                return category, f"Category: {category}"
    return None, "No category match"


def filter_and_categorize() -> dict[str, list[dict[str, Any]]]:
    """Filter magic values and categorize by type."""
    print("=" * 60)
    print("  Magic Values Intelligent Filtering - LIA")
    print("=" * 60)
    print()

    findings = parse_magic_values_report()
    print(f"[*] Loaded {len(findings)} magic values from {FINDINGS_FILE}")
    print()

    results = {
        "field_names": [],
        "tool_names": [],
        "node_names": [],
        "state_keys": [],
        "llm_config_keys": [],
        "type_names": [],
        "excluded": [],
        "uncategorized": [],
    }

    for finding in findings:
        value = finding["value"]

        # Check exclusions
        is_excluded, exclude_reason = should_exclude(value)
        if is_excluded:
            results["excluded"].append({**finding, "reason_filter": exclude_reason})
            continue

        # Categorize
        category, cat_reason = categorize_value(value)
        if category:
            results[category].append({**finding, "reason_filter": cat_reason})
        else:
            results["uncategorized"].append({**finding, "reason_filter": cat_reason})

    # Statistics
    print(f"[*] Filtering complete:")
    print(f"   Excluded (log messages, test data): {len(results['excluded'])}")
    print(f"   Field names (DB/model fields): {len(results['field_names'])}")
    print(f"   Tool names (LangGraph tools): {len(results['tool_names'])}")
    print(f"   Node names (LangGraph nodes): {len(results['node_names'])}")
    print(f"   State keys (LangGraph state): {len(results['state_keys'])}")
    print(f"   LLM config keys: {len(results['llm_config_keys'])}")
    print(f"   Type names (JSON schema): {len(results['type_names'])}")
    print(f"   Uncategorized (manual review): {len(results['uncategorized'])}")
    print()

    return results


def generate_report(results: dict[str, list[dict[str, Any]]]) -> None:
    """Generate filtered magic values report."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    total_findings = sum(len(v) for v in results.values())
    excluded_count = len(results["excluded"])
    candidates_count = total_findings - excluded_count

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        f.write("# Phase 4 - HIGH RISK: Magic Values Intelligent Filtering\n\n")
        f.write("**Date**: 2025-11-15\n")
        f.write("**Status**: [OK] FILTERING COMPLETE\n")
        f.write("**Script**: `scripts/optim/filter_magic_values.py`\n")
        f.write("**Author**: Claude Code (Sonnet 4.5)\n\n")
        f.write("---\n\n")

        f.write("## [SUMMARY] Résumé Exécutif\n\n")
        f.write("### Approche\n\n")
        f.write("Le rapport initial (`08_MISSING_CONSTANTS.md`) contenait **570 magic values** ")
        f.write("incluant beaucoup de **FAUX POSITIFS** (log messages, test data, etc.).\n\n")
        f.write("**Script de filtrage** : Catégorisation intelligente pour identifier les ")
        f.write("vrais candidats de centralisation.\n\n")

        f.write("### Statistiques\n\n")
        f.write(f"- **Total éléments analysés** : {total_findings}\n")
        f.write(f"- **[EXCLUDED] Faux positifs** : {excluded_count} ({excluded_count*100//total_findings}%)\n")
        f.write(f"- **[ACTION] Candidats réels** : {candidates_count} ({candidates_count*100//total_findings}%)\n\n")

        f.write("---\n\n")

        # Categorized findings
        priority_categories = [
            ("field_names", "Field Names (DB/Model Fields)", "HIGH"),
            ("state_keys", "State Keys (LangGraph State)", "HIGH"),
            ("tool_names", "Tool Names (LangGraph Tools)", "MEDIUM"),
            ("node_names", "Node Names (LangGraph Nodes)", "MEDIUM"),
            ("llm_config_keys", "LLM Config Keys", "LOW"),
            ("type_names", "Type Names (JSON Schema)", "LOW"),
        ]

        for key, title, priority in priority_categories:
            items = results[key]
            if not items:
                continue

            f.write(f"## [{priority}] {title} ({len(items)} items)\n\n")

            # Sort by occurrence count (descending)
            items_sorted = sorted(items, key=lambda x: x['occurrences'], reverse=True)

            # Show top 20
            f.write("**Top 20 par usage:**\n\n")
            f.write("| Value | Occurrences | Confidence | Locations (sample) |\n")
            f.write("|-------|-------------|------------|--------------------|\n")

            for item in items_sorted[:20]:
                value = item['value']
                occurrences = item['occurrences']
                confidence = item['confidence']
                location_sample = item['location'].split(',')[0]  # First location

                f.write(f"| `{value}` | {occurrences} | {confidence} | {location_sample} |\n")

            if len(items_sorted) > 20:
                f.write(f"\n... et {len(items_sorted) - 20} autres\n")

            f.write("\n---\n\n")

        # Uncategorized (manual review needed)
        if results["uncategorized"]:
            f.write(f"## [CHECK] Uncategorized ({len(results['uncategorized'])} items)\n\n")
            f.write("Nécessitent revue manuelle pour déterminer si centralisation appropriée\n\n")

            # Show top 30
            items_sorted = sorted(results["uncategorized"], key=lambda x: x['occurrences'], reverse=True)
            f.write("**Top 30 par usage:**\n\n")
            f.write("| Value | Occurrences | Locations (sample) |\n")
            f.write("|-------|-------------|--------------------|\n")

            for item in items_sorted[:30]:
                value = item['value']
                occurrences = item['occurrences']
                location_sample = item['location'].split(',')[0]

                f.write(f"| `{value}` | {occurrences} | {location_sample} |\n")

            if len(items_sorted) > 30:
                f.write(f"\n... et {len(items_sorted) - 30} autres\n")

            f.write("\n---\n\n")

        # Excluded (for reference)
        f.write(f"## [EXCLUDED] Faux Positifs ({len(results['excluded'])} items)\n\n")
        f.write("Log messages, test data, standard values, intentional configs\n\n")
        f.write(f"**Raisons d'exclusion:**\n")
        f.write("- Messages de log / documentation (bullets, descriptions)\n")
        f.write("- Données de test (user123, sess456, conv_123)\n")
        f.write("- Valeurs standard (utf-8, bearer, frozen)\n")
        f.write("- Noms de modèles LLM (gpt-4.1-mini, gpt-4.1-mini) - Configs intentionnelles\n")
        f.write("- Providers LLM (openai) - Configs intentionnelles\n")
        f.write("- Status/actions génériques (success, error, approve) - Possiblement déjà centralisés\n\n")

        f.write("---\n\n")

        # Recommendations
        f.write("## [ACTION] Recommandations\n\n")

        f.write("### Priorité 1: Field Names (HIGH)\n\n")
        field_count = len(results["field_names"])
        f.write(f"**{field_count} field names** utilisés dans DB queries, API responses, state management.\n\n")
        f.write("**Action:** Créer `core/field_names.py` avec constantes:\n")
        f.write("```python\n")
        f.write("# Database/Model field names\n")
        f.write("FIELD_USER_ID = \"user_id\"\n")
        f.write("FIELD_SESSION_ID = \"session_id\"\n")
        f.write("FIELD_STATUS = \"status\"\n")
        f.write("# ... etc\n")
        f.write("```\n\n")

        f.write("**Bénéfices:**\n")
        f.write("- Typo safety (IDE autocomplete)\n")
        f.write("- Refactoring facile (rename field)\n")
        f.write("- Documentation centralisée\n\n")

        f.write("### Priorité 2: State Keys (HIGH)\n\n")
        state_count = len(results["state_keys"])
        f.write(f"**{state_count} state keys** utilisés dans LangGraph state management.\n\n")
        f.write("**Action:** Créer `domains/agents/state_keys.py`\n\n")

        f.write("### Priorité 3: Tool/Node Names (MEDIUM)\n\n")
        tool_count = len(results["tool_names"])
        node_count = len(results["node_names"])
        f.write(f"**{tool_count} tool names + {node_count} node names** utilisés dans LangGraph.\n\n")
        f.write("**Action:** Vérifier si déjà centralisés dans `domains/agents/constants.py`\n\n")

        f.write("### Priorité 4: Manual Review (CHECK)\n\n")
        uncat_count = len(results["uncategorized"])
        f.write(f"**{uncat_count} uncategorized items** - revue manuelle requise\n\n")

        f.write("---\n\n")
        f.write("**Report Generated**: 2025-11-15\n\n")
        f.write("**Author**: Claude Code (Sonnet 4.5)\n")

    print(f"[OK] Report generated: {OUTPUT_FILE}")


if __name__ == "__main__":
    try:
        results = filter_and_categorize()
        generate_report(results)

        print(f"\n[SUCCESS] Filtering complete!")
        print(f"   Report: {OUTPUT_FILE}")
        print(f"\n[NEXT] Review report and decide on centralization actions")

    except KeyboardInterrupt:
        print("\n\n[WARN] Filtering interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Filtering failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
