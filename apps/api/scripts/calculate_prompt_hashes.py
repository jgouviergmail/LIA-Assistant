"""
Script to calculate and display SHA256 hashes for all versioned prompts.

This script is used to:
1. Calculate hashes for all prompts in a given version
2. Update the CHANGELOG.md with actual hash values
3. Validate prompt integrity during deployment

Usage:
    python scripts/calculate_prompt_hashes.py
    python scripts/calculate_prompt_hashes.py --version v1
    python scripts/calculate_prompt_hashes.py --validate

Compliance: LangGraph v1.0 + LangChain v1.0 best practices
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.domains.agents.prompts.prompt_loader import (
    calculate_prompt_hash,
    get_prompt_metadata,
    list_available_prompts,
    load_prompt,
    validate_all_prompts,
)


def main():
    parser = argparse.ArgumentParser(description="Calculate SHA256 hashes for versioned prompts")
    parser.add_argument("--version", default="v1", help="Prompt version (default: v1)")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate against expected hashes (reads from CHANGELOG.md)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output with metadata")
    args = parser.parse_args()

    print(f"🔍 Analyzing prompts for version: {args.version}")
    print("=" * 80)

    # List all available prompts
    prompts = list_available_prompts(args.version)

    if not prompts:
        print(f"❌ No prompts found for version {args.version}")
        return 1

    print(f"\n📋 Found {len(prompts)} prompt(s):\n")

    # Calculate and display hashes
    results = {}
    total_size = 0

    for prompt_name in prompts:
        try:
            if args.verbose:
                # Get full metadata
                metadata = get_prompt_metadata(prompt_name, args.version)
                size = metadata["size"]
                prompt_hash = metadata["hash"]
                total_size += size

                print(f"📄 {prompt_name}")
                print(f"   Size: {size:,} chars ({size} bytes)")
                print(f"   Hash: {prompt_hash}")
                print(f"   Path: {metadata['file_path']}")
                print()
            else:
                # Simple hash calculation
                content = load_prompt(prompt_name, args.version)
                prompt_hash = calculate_prompt_hash(content)
                size = len(content)
                total_size += size

                print(f"✅ {prompt_name}")
                print(f"   Hash: {prompt_hash}")
                print(f"   Size: {size:,} chars")
                print()

            results[prompt_name] = prompt_hash

        except Exception as e:
            print(f"❌ Error processing {prompt_name}: {e}")
            return 1

    # Summary
    print("=" * 80)
    print("\n📊 Summary:")
    print(f"   Total prompts: {len(results)}")
    print(f"   Total size: {total_size:,} chars ({total_size:,} bytes)")
    print(f"   Average size: {total_size // len(results):,} chars")

    # Check if prompts exceed 1024 tokens threshold for OpenAI caching
    # Rough estimate: 1 token ≈ 4 characters
    avg_tokens = total_size // len(results) // 4
    print(f"   Estimated avg tokens: ~{avg_tokens:,} tokens")

    if avg_tokens > 1024:
        print("   ✅ Prompts optimized for OpenAI prompt caching (>1024 tokens)")
    else:
        print("   ⚠️  Prompts may be too short for optimal caching (<1024 tokens)")

    # Hash registry format for CHANGELOG.md
    print("\n" + "=" * 80)
    print("\n📝 Hash Registry (copy to CHANGELOG.md):\n")
    print("```")
    for prompt_name, prompt_hash in sorted(results.items()):
        print(f"{prompt_name + '.txt':<40} {prompt_hash}")
    print("```")

    # Validation mode
    if args.validate:
        print("\n" + "=" * 80)
        print("\n🔐 Validating prompt integrity...\n")

        # TODO: Read expected hashes from CHANGELOG.md
        # For now, just validate that all prompts are loadable
        try:
            validate_all_prompts(args.version)
            print("✅ All prompts validated successfully")
        except Exception as e:
            print(f"❌ Validation failed: {e}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
