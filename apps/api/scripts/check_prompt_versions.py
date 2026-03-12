#!/usr/bin/env python3
"""
Diagnostic script to check available and active prompt versions.

Usage:
    python scripts/check_prompt_versions.py
"""

import os
import re
import sys
from pathlib import Path


def get_versions_from_filesystem(prompts_dir: Path) -> list[str]:
    """Scan the filesystem to detect available versions."""
    if not prompts_dir.exists():
        return []

    versions = []
    version_pattern = re.compile(r"^v\d+$")

    for item in prompts_dir.iterdir():
        if item.is_dir() and version_pattern.match(item.name):
            versions.append(item.name)

    return sorted(versions, key=lambda v: int(v[1:]) if v[1:].isdigit() else 0)


def get_prompts_for_version(prompts_dir: Path, version: str) -> list[str]:
    """List all available prompts for a given version."""
    version_dir = prompts_dir / version
    if not version_dir.exists():
        return []

    return sorted([f.stem for f in version_dir.glob("*.txt")])


def get_env_config() -> dict[str, str | None]:
    """Retrieve configuration from environment variables."""
    return {
        "router_version": os.getenv("ROUTER_PROMPT_VERSION"),
        "planner_version": os.getenv("PLANNER_PROMPT_VERSION"),
        "response_version": os.getenv("RESPONSE_PROMPT_VERSION"),
        "contacts_agent_version": os.getenv("CONTACTS_AGENT_PROMPT_VERSION"),
        "hitl_classifier_version": os.getenv("HITL_CLASSIFIER_PROMPT_VERSION"),
    }


# Mapping of critical prompts and their expected versions
CRITICAL_PROMPTS = {
    "router": {
        "env_var": "ROUTER_PROMPT_VERSION",
        "prompt_name": "router_system_prompt",
        "description": "Router (syntactic classification)",
    },
    "planner": {
        "env_var": "PLANNER_PROMPT_VERSION",
        "prompt_name": "planner_system_prompt",
        "description": "Planner (tool orchestration)",
    },
    "response": {
        "env_var": "RESPONSE_PROMPT_VERSION",
        "prompt_name": "response_system_prompt_base",
        "description": "Response (response generation)",
    },
    "contacts_agent": {
        "env_var": "CONTACTS_AGENT_PROMPT_VERSION",
        "prompt_name": "contacts_agent_prompt",
        "description": "Contacts Agent (domain-specific)",
    },
    "hitl_classifier": {
        "env_var": "HITL_CLASSIFIER_PROMPT_VERSION",
        "prompt_name": "hitl_classifier_prompt",
        "description": "HITL Classifier (approval detection)",
    },
    "hitl_plan_approval": {
        "env_var": "HITL_PLAN_APPROVAL_QUESTION_PROMPT_VERSION",
        "prompt_name": "hitl_plan_approval_question_prompt",
        "description": "HITL Plan Approval (plan questions)",
    },
    "hitl_question_generator": {
        "env_var": "HITL_QUESTION_GENERATOR_PROMPT_VERSION",
        "prompt_name": "hitl_question_generator_prompt",
        "description": "HITL Question Generator (question generation)",
    },
}


def main():
    """Display a comprehensive report on prompt versions."""

    # Determine the prompts directory
    script_dir = Path(__file__).parent
    prompts_dir = script_dir.parent / "src" / "domains" / "agents" / "prompts"

    print("=" * 80)
    print("DIAGNOSTIC DES VERSIONS DE PROMPTS")
    print("=" * 80)

    # 1. Versions detected in the filesystem
    print("\n📂 VERSIONS DÉTECTÉES DANS LE FILESYSTEM:")
    print(f"   Répertoire: {prompts_dir}")

    versions = get_versions_from_filesystem(prompts_dir)
    if versions:
        for version in versions:
            prompts = get_prompts_for_version(prompts_dir, version)
            print(f"\n   ✅ {version:<6} ({len(prompts)} prompts)")
            for prompt in prompts:
                print(f"      - {prompt}")
    else:
        print("   ❌ Aucune version détectée!")

    # 2. Configuration actuelle (.env)
    print("\n\n⚙️  CONFIGURATION ACTUELLE (Variables d'environnement):")
    get_env_config()

    for _name, info in CRITICAL_PROMPTS.items():
        env_var = info["env_var"]
        version = os.getenv(env_var)
        status = version or "NON DÉFINI"
        print(f"   {env_var:<35} = {status}")

    # 3. Vérification de cohérence
    print("\n\n🔍 VÉRIFICATION DE COHÉRENCE:")

    errors = []
    warnings = []
    successes = []

    for _name, info in CRITICAL_PROMPTS.items():
        env_var = info["env_var"]
        prompt_name = info["prompt_name"]
        description = info["description"]
        version = os.getenv(env_var)

        if not version:
            warnings.append(f"{description} - {env_var} non défini")
            print(f"   ⚠️  {description}")
            print(f"      Variable: {env_var} non définie")
            continue

        if version not in versions:
            errors.append(
                f"{description} - Version {version} n'existe pas "
                f"(disponibles: {', '.join(versions)})"
            )
            print(f"   ❌ {description}")
            print(f"      Version configurée: {version}")
            print("      VERSION NON DISPONIBLE!")
            print(f"      Versions disponibles: {', '.join(versions)}")
            continue

        prompts = get_prompts_for_version(prompts_dir, version)
        if prompt_name not in prompts:
            errors.append(f"{description} - Fichier {prompt_name}.txt manquant dans {version}")
            print(f"   ❌ {description}")
            print(f"      Version: {version} disponible")
            print(f"      Fichier {prompt_name}.txt MANQUANT!")
            continue

        # Tout est OK
        successes.append(f"{description} - {version}")
        print(f"   ✅ {description}")
        print(f"      Version: {version}")
        print(f"      Fichier: {prompt_name}.txt existe")

    # 4. Résumé
    print("\n\n" + "=" * 80)
    print("RÉSUMÉ:")
    print("=" * 80)
    print(f"Versions disponibles : {len(versions)}")
    print(f"Prompts critiques    : {len(CRITICAL_PROMPTS)}")
    print(f"  ✅ Succès          : {len(successes)}")
    print(f"  ⚠️  Warnings        : {len(warnings)}")
    print(f"  ❌ Erreurs         : {len(errors)}")

    # Problem details
    if warnings:
        print("\n⚠️  WARNINGS:")
        for warning in warnings:
            print(f"   - {warning}")

    if errors:
        print("\n❌ ERREURS CRITIQUES:")
        for error in errors:
            print(f"   - {error}")
        print("\n🚨 Le système risque de ne pas démarrer correctement!")
        return 1

    # Validation spécifique pour Router v8
    router_version = os.getenv("ROUTER_PROMPT_VERSION")
    if router_version == "v8":
        print("\n✅ VALIDATION SPÉCIALE:")
        print("   Router v8 est correctement configuré et disponible")
        print("   Anti-hallucination Règle #5 activée")

    print("\n" + "=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
