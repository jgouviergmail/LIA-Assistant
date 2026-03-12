#!/usr/bin/env python3
"""
LLM Multi-Provider Configuration Validator.

Validates LLM provider configuration for all LLM types:
- Checks that provider credentials are set
- Validates provider/model compatibility
- Checks advanced provider_config JSON syntax
- Validates temperature, max_tokens, and other parameters
- Provides actionable recommendations

Usage:
    python scripts/validate_llm_config.py

Best Practices (2025):
- Run this before deploying to production
- Run in CI/CD pipeline to catch configuration errors early
- Use --verbose flag for detailed diagnostics
"""

import argparse
import json
import sys
from typing import Any

# Add src to path for imports
sys.path.insert(0, "src")

from src.core.config import get_settings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Valid LLM types
LLM_TYPES = ["router", "response", "contacts_agent", "planner", "hitl_classifier"]

# Valid providers
PROVIDERS = ["openai", "anthropic", "deepseek", "perplexity", "ollama"]

# Provider credential mapping
PROVIDER_CREDENTIALS = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "deepseek": "deepseek_api_key",
    "perplexity": "perplexity_api_key",
    "ollama": "ollama_base_url",
}

# Models that require tools
TOOL_REQUIRING_LLM_TYPES = ["contacts_agent"]

# Models that don't support tools
NO_TOOL_MODELS = ["deepseek-reasoner"]


class ConfigurationError(Exception):
    """Configuration error detected."""

    pass


class ConfigurationWarning(Exception):
    """Configuration warning (non-fatal)."""

    pass


def validate_provider_credentials(settings: Any, provider: str, llm_type: str) -> list[str]:
    """
    Validate that provider credentials are configured.

    Args:
        settings: Settings object
        provider: Provider name
        llm_type: LLM type

    Returns:
        list: List of error messages (empty if valid)
    """
    errors = []
    credential_attr = PROVIDER_CREDENTIALS.get(provider)

    if not credential_attr:
        errors.append(f"❌ {llm_type}: Unknown provider '{provider}'")
        return errors

    credential_value = getattr(settings, credential_attr, None)

    if provider == "ollama":
        # Ollama just needs base_url (can be empty for localhost default)
        if not credential_value:
            errors.append(
                f"⚠️  {llm_type}: ollama_base_url not set (will default to http://localhost:11434)"
            )
    else:
        # Other providers require API keys
        if not credential_value or credential_value == "":
            errors.append(
                f"❌ {llm_type}: {credential_attr.upper()} not set for provider '{provider}'"
            )

    return errors


def validate_provider_model_compatibility(provider: str, model: str, llm_type: str) -> list[str]:
    """
    Validate provider/model compatibility.

    Args:
        provider: Provider name
        model: Model name
        llm_type: LLM type

    Returns:
        list: List of error messages (empty if valid)
    """
    errors = []

    # Rule 1: deepseek-reasoner doesn't support tools
    if model == "deepseek-reasoner" and llm_type in TOOL_REQUIRING_LLM_TYPES:
        errors.append(
            f"❌ {llm_type}: deepseek-reasoner does not support tool calling. "
            f"Use 'deepseek-chat' instead for {llm_type}."
        )

    # Rule 2: Warn if using deepseek-reasoner for router/planner (needs structured output)
    if model == "deepseek-reasoner" and llm_type in ["router", "planner"]:
        errors.append(
            f"⚠️  {llm_type}: deepseek-reasoner may not support structured output/JSON mode. "
            f"Consider using 'deepseek-chat' instead."
        )

    return errors


def validate_provider_config_json(settings: Any, llm_type: str) -> list[str]:
    """
    Validate provider_config JSON syntax.

    Args:
        settings: Settings object
        llm_type: LLM type

    Returns:
        list: List of error messages (empty if valid)
    """
    errors = []
    config_attr = f"{llm_type}_llm_provider_config"
    config_json = getattr(settings, config_attr, "{}")

    try:
        parsed = json.loads(config_json)
        if not isinstance(parsed, dict):
            errors.append(
                f"❌ {llm_type}: {config_attr} must be a JSON object, got {type(parsed).__name__}"
            )
    except json.JSONDecodeError as e:
        errors.append(f"❌ {llm_type}: Invalid JSON in {config_attr}: {e}")

    return errors


def validate_llm_parameters(settings: Any, llm_type: str) -> list[str]:
    """
    Validate LLM parameters (temperature, max_tokens, etc.).

    Args:
        settings: Settings object
        llm_type: LLM type

    Returns:
        list: List of error messages (empty if valid)
    """
    errors = []

    # Temperature validation (0.0 - 2.0)
    temp_attr = f"{llm_type}_llm_temperature"
    temperature = getattr(settings, temp_attr, None)
    if temperature is not None:
        if not (0.0 <= temperature <= 2.0):
            errors.append(f"❌ {llm_type}: {temp_attr}={temperature} out of range [0.0, 2.0]")

    # Max tokens validation (> 0)
    max_tokens_attr = f"{llm_type}_llm_max_tokens"
    max_tokens = getattr(settings, max_tokens_attr, None)
    if max_tokens is not None:
        if max_tokens <= 0:
            errors.append(f"❌ {llm_type}: {max_tokens_attr}={max_tokens} must be > 0")

    # Top-p validation (0.0 - 1.0)
    top_p_attr = f"{llm_type}_llm_top_p"
    top_p = getattr(settings, top_p_attr, None)
    if top_p is not None:
        if not (0.0 <= top_p <= 1.0):
            errors.append(f"❌ {llm_type}: {top_p_attr}={top_p} out of range [0.0, 1.0]")

    # Frequency/Presence penalty validation (-2.0 - 2.0)
    for penalty_name in ["frequency_penalty", "presence_penalty"]:
        penalty_attr = f"{llm_type}_llm_{penalty_name}"
        penalty = getattr(settings, penalty_attr, None)
        if penalty is not None:
            if not (-2.0 <= penalty <= 2.0):
                errors.append(f"❌ {llm_type}: {penalty_attr}={penalty} out of range [-2.0, 2.0]")

    return errors


def validate_llm_type(
    settings: Any, llm_type: str, verbose: bool = False
) -> tuple[list[str], list[str]]:
    """
    Validate configuration for a single LLM type.

    Args:
        settings: Settings object
        llm_type: LLM type to validate
        verbose: Print verbose output

    Returns:
        tuple: (errors, warnings)
    """
    errors = []
    warnings = []

    # Get provider
    provider_attr = f"{llm_type}_llm_provider"
    provider = getattr(settings, provider_attr, None)

    if not provider:
        errors.append(f"❌ {llm_type}: {provider_attr} not set")
        return errors, warnings

    if provider not in PROVIDERS:
        errors.append(
            f"❌ {llm_type}: Invalid provider '{provider}'. "
            f"Must be one of: {', '.join(PROVIDERS)}"
        )
        return errors, warnings

    # Get model
    model_attr = f"{llm_type}_llm_model"
    model = getattr(settings, model_attr, None)

    if not model:
        errors.append(f"❌ {llm_type}: {model_attr} not set")
        return errors, warnings

    if verbose:
        print(f"  {llm_type}: provider={provider}, model={model}")

    # Validate credentials
    cred_errors = validate_provider_credentials(settings, provider, llm_type)
    errors.extend([e for e in cred_errors if "❌" in e])
    warnings.extend([e for e in cred_errors if "⚠️" in e])

    # Validate provider/model compatibility
    compat_errors = validate_provider_model_compatibility(provider, model, llm_type)
    errors.extend([e for e in compat_errors if "❌" in e])
    warnings.extend([e for e in compat_errors if "⚠️" in e])

    # Validate provider_config JSON
    json_errors = validate_provider_config_json(settings, llm_type)
    errors.extend(json_errors)

    # Validate LLM parameters
    param_errors = validate_llm_parameters(settings, llm_type)
    errors.extend(param_errors)

    return errors, warnings


def validate_all_llm_types(
    verbose: bool = False,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """
    Validate configuration for all LLM types.

    Args:
        verbose: Print verbose output

    Returns:
        tuple: (errors_by_type, warnings_by_type)
    """
    settings = get_settings()
    errors_by_type = {}
    warnings_by_type = {}

    for llm_type in LLM_TYPES:
        errors, warnings = validate_llm_type(settings, llm_type, verbose)
        if errors:
            errors_by_type[llm_type] = errors
        if warnings:
            warnings_by_type[llm_type] = warnings

    return errors_by_type, warnings_by_type


def print_results(
    errors_by_type: dict[str, list[str]],
    warnings_by_type: dict[str, list[str]],
) -> None:
    """Print validation results."""
    print("\n" + "=" * 80)
    print("LLM Multi-Provider Configuration Validation Results")
    print("=" * 80 + "\n")

    total_errors = sum(len(errors) for errors in errors_by_type.values())
    total_warnings = sum(len(warnings) for warnings in warnings_by_type.values())

    if total_errors == 0 and total_warnings == 0:
        print("✅ All LLM configurations are valid!\n")
        return

    # Print errors
    if total_errors > 0:
        print(f"Errors: {total_errors}")
        print("-" * 80)
        for _llm_type, errors in errors_by_type.items():
            for error in errors:
                print(error)
        print()

    # Print warnings
    if total_warnings > 0:
        print(f"Warnings: {total_warnings}")
        print("-" * 80)
        for _llm_type, warnings in warnings_by_type.items():
            for warning in warnings:
                print(warning)
        print()

    # Print recommendations
    if total_errors > 0:
        print("Recommendations:")
        print("-" * 80)
        print("1. Review .env file and set missing credentials")
        print("2. Check provider/model compatibility")
        print("3. Validate JSON syntax in XXXX_LLM_PROVIDER_CONFIG fields")
        print("4. Ensure all parameters are within valid ranges")
        print("\nSee docs/guides/MULTI_PROVIDER_CONFIGURATION.md for details")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate LLM multi-provider configuration")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print verbose output")
    parser.add_argument("--llm-type", choices=LLM_TYPES, help="Validate only specific LLM type")
    args = parser.parse_args()

    try:
        if args.llm_type:
            # Validate single LLM type
            settings = get_settings()
            errors, warnings = validate_llm_type(settings, args.llm_type, args.verbose)
            errors_by_type = {args.llm_type: errors} if errors else {}
            warnings_by_type = {args.llm_type: warnings} if warnings else {}
        else:
            # Validate all LLM types
            if args.verbose:
                print("Validating all LLM types...")
                print()
            errors_by_type, warnings_by_type = validate_all_llm_types(args.verbose)

        print_results(errors_by_type, warnings_by_type)

        # Exit with error code if errors found
        total_errors = sum(len(errors) for errors in errors_by_type.values())
        sys.exit(1 if total_errors > 0 else 0)

    except Exception as e:
        print(f"❌ Validation failed: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
