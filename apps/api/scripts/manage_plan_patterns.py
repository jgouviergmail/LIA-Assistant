#!/usr/bin/env python
"""
Plan Pattern Learner - CLI Maintenance Tool.

Script d'administration pour gérer les patterns de planification appris.

Commands:
    list        Liste tous les patterns enregistrés
    show        Affiche les détails d'un pattern spécifique
    stats       Affiche les statistiques globales
    delete      Supprime un pattern
    reset       Supprime tous les patterns (reset complet)
    seed        Crée un pattern avec des valeurs initiales
    export      Exporte tous les patterns en JSON

Usage:
    python scripts/manage_plan_patterns.py list
    python scripts/manage_plan_patterns.py list --suggerable
    python scripts/manage_plan_patterns.py show "get_contacts→send_email"
    python scripts/manage_plan_patterns.py stats
    python scripts/manage_plan_patterns.py delete "get_contacts→send_email"
    python scripts/manage_plan_patterns.py reset --confirm
    python scripts/manage_plan_patterns.py seed "get_contacts→send_email" --domains contacts,emails --intent mutation
    python scripts/manage_plan_patterns.py export > patterns.json

Created: 2026-01-12
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for Windows console
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Add apps/api to path for imports (so 'from src.domains...' works)
sys.path.insert(0, str(Path(__file__).parent.parent))


# Load .env file from project root and patch REDIS_URL for localhost execution
def _load_env_for_local_execution():
    """Load .env and patch REDIS_URL to use localhost instead of Docker hostname."""
    import os
    import re

    project_root = Path(__file__).parent.parent.parent.parent  # apps/api/scripts -> project root
    env_file = project_root / ".env"

    if not env_file.exists():
        return

    # Parse .env file
    env_vars = {}
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                # Remove quotes if present
                value = value.strip().strip('"').strip("'")
                env_vars[key.strip()] = value

    # Set env vars that aren't already set
    for key, value in env_vars.items():
        if key not in os.environ:
            # Expand ${VAR} references
            expanded = re.sub(
                r"\$\{(\w+)\}",
                lambda m: env_vars.get(m.group(1), os.environ.get(m.group(1), "")),
                value,
            )
            os.environ[key] = expanded

    # Patch REDIS_URL to use localhost instead of Docker hostname
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url and "@redis:" in redis_url:
        # Replace redis:6379 with 127.0.0.1:6379
        os.environ["REDIS_URL"] = redis_url.replace("@redis:", "@127.0.0.1:")


_load_env_for_local_execution()


def format_timestamp(ts: int) -> str:
    """Format Unix timestamp to human readable date."""
    if ts == 0:
        return "N/A"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def format_confidence(confidence: float) -> str:
    """Format confidence with color indicator."""
    pct = int(confidence * 100)
    if confidence >= 0.90:
        return f"{pct}% [BYPASS]"
    elif confidence >= 0.75:
        return f"{pct}% [SUGGEST]"
    else:
        return f"{pct}%"


def print_pattern_table(patterns: list, show_all: bool = True) -> None:
    """Print patterns in a formatted table."""
    if not patterns:
        print("No patterns found.")
        return

    # Header
    print()
    print(f"{'Pattern Key':<40} {'S/F':<8} {'Conf':<12} {'Domains':<20} {'Intent':<8}")
    print("-" * 90)

    for p in patterns:
        # Format S/F
        sf = f"{p.successes}/{p.failures}"

        # Format confidence
        conf = format_confidence(p.confidence)

        # Format domains
        domains = ",".join(sorted(p.domains))[:18]
        if len(",".join(sorted(p.domains))) > 18:
            domains += ".."

        # Format pattern key (truncate if too long)
        key = p.key[:38] + ".." if len(p.key) > 40 else p.key

        print(f"{key:<40} {sf:<8} {conf:<12} {domains:<20} {p.intent:<8}")

    print("-" * 90)
    print(f"Total: {len(patterns)} patterns")
    print()


def print_pattern_details(pattern) -> None:
    """Print detailed info about a single pattern."""
    if not pattern:
        print("Pattern not found.")
        return

    print()
    print("=" * 60)
    print(f"Pattern: {pattern.key}")
    print("=" * 60)
    print()
    print(f"  Successes:    {pattern.successes}")
    print(f"  Failures:     {pattern.failures}")
    print(f"  Total:        {pattern.total}")
    print(f"  Confidence:   {format_confidence(pattern.confidence)}")
    print()
    print(f"  Domains:      {', '.join(sorted(pattern.domains))}")
    print(f"  Intent:       {pattern.intent}")
    print(f"  Last Update:  {format_timestamp(pattern.last_update)}")
    print()
    print(f"  Suggerable:   {'Yes' if pattern.is_suggerable else 'No'}")
    print(f"  Can Bypass:   {'Yes' if pattern.can_bypass_validation else 'No'}")
    print()

    # Bayesian interpretation
    print("  Bayesian Analysis:")
    print("    Prior:      Beta(2, 1) = 67% initial confidence")
    print(f"    Posterior:  Beta({2 + pattern.successes}, {1 + pattern.failures})")
    print(f"    Mean:       {pattern.confidence:.1%}")
    print()


def print_stats(stats: dict) -> None:
    """Print global statistics."""
    print()
    print("=" * 50)
    print("Plan Pattern Learner - Statistics")
    print("=" * 50)
    print()
    print(f"  Total patterns:       {stats['total_patterns']}")
    print(f"  Suggerable patterns:  {stats['suggerable_patterns']}")
    print(f"  Bypassable patterns:  {stats['bypassable_patterns']}")
    print()
    print(f"  Total observations:   {stats['total_observations']}")
    print(f"  Total successes:      {stats['total_successes']}")
    print(f"  Total failures:       {stats['total_failures']}")
    print()
    print(f"  Global success rate:  {stats['global_success_rate']:.1%}")
    print(f"  Avg confidence:       {stats['avg_confidence']:.1%}")
    print()

    # Interpretation
    if stats["total_patterns"] == 0:
        print("  Status: No patterns learned yet. System is learning.")
    elif stats["bypassable_patterns"] > 0:
        print(f"  Status: {stats['bypassable_patterns']} patterns can bypass validation!")
    elif stats["suggerable_patterns"] > 0:
        print(f"  Status: {stats['suggerable_patterns']} patterns ready for suggestion.")
    else:
        print("  Status: Learning in progress, not enough data yet.")
    print()


# =============================================================================
# ASYNC COMMANDS
# =============================================================================


async def cmd_list(args) -> int:
    """List all patterns."""
    from src.domains.agents.services.plan_pattern_learner import get_pattern_learner

    learner = get_pattern_learner()
    patterns = await learner.list_all_patterns()

    # Filter if requested
    if args.suggerable:
        patterns = [p for p in patterns if p.is_suggerable]
    if args.bypassable:
        patterns = [p for p in patterns if p.can_bypass_validation]
    if args.domain:
        patterns = [p for p in patterns if args.domain in p.domains]
    if args.intent:
        patterns = [p for p in patterns if p.intent == args.intent]

    print_pattern_table(patterns)
    return 0


async def cmd_show(args) -> int:
    """Show details of a specific pattern."""
    from src.domains.agents.services.plan_pattern_learner import get_pattern_learner

    learner = get_pattern_learner()
    pattern = await learner.get_pattern(args.pattern_key)

    print_pattern_details(pattern)
    return 0 if pattern else 1


async def cmd_stats(args) -> int:
    """Show global statistics."""
    from src.domains.agents.services.plan_pattern_learner import get_pattern_learner

    learner = get_pattern_learner()
    stats = await learner.get_stats_summary()

    print_stats(stats)
    return 0


async def cmd_delete(args) -> int:
    """Delete a specific pattern."""
    from src.domains.agents.services.plan_pattern_learner import get_pattern_learner

    learner = get_pattern_learner()

    # Show pattern first
    pattern = await learner.get_pattern(args.pattern_key)
    if not pattern:
        print(f"Pattern not found: {args.pattern_key}")
        return 1

    if not args.confirm:
        print_pattern_details(pattern)
        print("Add --confirm to delete this pattern.")
        return 0

    success = await learner.delete_pattern(args.pattern_key)
    if success:
        print(f"Deleted pattern: {args.pattern_key}")
        return 0
    else:
        print(f"Failed to delete pattern: {args.pattern_key}")
        return 1


async def cmd_reset(args) -> int:
    """Delete all patterns."""
    from src.domains.agents.services.plan_pattern_learner import get_pattern_learner

    if not args.confirm:
        learner = get_pattern_learner()
        patterns = await learner.list_all_patterns()
        print(f"This will delete {len(patterns)} patterns.")
        print("Add --confirm to proceed with reset.")
        return 0

    learner = get_pattern_learner()
    count = await learner.delete_all_patterns()
    print(f"Deleted {count} patterns.")
    return 0


async def cmd_seed(args) -> int:
    """Seed a pattern with initial values."""
    from src.domains.agents.services.plan_pattern_learner import get_pattern_learner

    learner = get_pattern_learner()

    domains = args.domains.split(",") if args.domains else []

    success = await learner.seed_pattern(
        pattern_key=args.pattern_key,
        domains=domains,
        intent=args.intent,
        successes=args.successes,
        failures=args.failures,
    )

    if success:
        print(f"Seeded pattern: {args.pattern_key}")
        print(f"  Domains: {', '.join(domains)}")
        print(f"  Intent: {args.intent}")
        print(f"  Successes: {args.successes}")
        print(f"  Failures: {args.failures}")

        # Show resulting confidence
        pattern = await learner.get_pattern(args.pattern_key)
        if pattern:
            print(f"  Confidence: {format_confidence(pattern.confidence)}")
        return 0
    else:
        print(f"Failed to seed pattern: {args.pattern_key}")
        return 1


async def cmd_export(args) -> int:
    """Export all patterns to JSON."""
    from src.domains.agents.services.plan_pattern_learner import get_pattern_learner

    learner = get_pattern_learner()
    patterns = await learner.list_all_patterns()

    data = {
        "exported_at": datetime.now().isoformat(),
        "count": len(patterns),
        "patterns": [p.to_dict() for p in patterns],
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Exported {len(patterns)} patterns to {args.output}")
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))

    return 0


async def cmd_import(args) -> int:
    """Import patterns from JSON file."""
    from src.domains.agents.services.plan_pattern_learner import get_pattern_learner

    try:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to read file: {e}")
        return 1

    patterns = data.get("patterns", [])
    if not patterns:
        print("No patterns found in file.")
        return 1

    print(f"Found {len(patterns)} patterns to import.")

    if not args.confirm:
        print("Add --confirm to proceed with import.")
        return 0

    learner = get_pattern_learner()
    imported = 0

    for p in patterns:
        success = await learner.seed_pattern(
            pattern_key=p["key"],
            domains=p.get("domains", []),
            intent=p.get("intent", "read"),
            successes=p.get("successes", 0),
            failures=p.get("failures", 0),
        )
        if success:
            imported += 1
            print(f"  Imported: {p['key']}")
        else:
            print(f"  Failed: {p['key']}")

    print(f"\nImported {imported}/{len(patterns)} patterns.")
    return 0 if imported == len(patterns) else 1


async def cmd_seed_golden(args) -> int:
    """Seed golden (predefined) patterns."""
    from src.domains.agents.services.golden_patterns import (
        GOLDEN_PATTERNS,
        reset_to_golden_patterns,
        seed_golden_patterns,
    )

    print()
    print("=" * 60)
    print("Golden Pattern Seeding")
    print("=" * 60)
    print()
    print(f"Total golden patterns defined: {len(GOLDEN_PATTERNS)}")
    print()

    # Show what will be seeded
    if args.list:
        print("Golden patterns to seed:")
        print()
        print(f"{'Pattern Key':<45} {'Domains':<25} {'Intent':<10} {'S/F':<8}")
        print("-" * 90)
        for p in GOLDEN_PATTERNS:
            print(f"{p.key:<45} {p.domains:<25} {p.intent:<10} {p.successes}/{p.failures}")
        print("-" * 90)
        print()
        return 0

    if args.reset:
        if not args.confirm:
            print("WARNING: --reset will DELETE ALL existing patterns first!")
            print("Add --confirm to proceed.")
            return 0

        print("Resetting to golden patterns (deleting existing patterns)...")
        stats = await reset_to_golden_patterns()
    else:
        if not args.confirm:
            print("This will seed golden patterns (existing patterns preserved).")
            print("Add --confirm to proceed.")
            print("Add --reset --confirm to replace all existing patterns.")
            return 0

        print("Seeding golden patterns (preserving existing)...")
        stats = await seed_golden_patterns(replace_existing=False)

    print()
    print("Results:")
    print(f"  Seeded:  {stats['seeded']} patterns")
    print(f"  Skipped: {stats['skipped']} patterns (already exist)")
    print(f"  Errors:  {stats['errors']} patterns")
    print()

    return 0 if stats["errors"] == 0 else 1


# =============================================================================
# MAIN
# =============================================================================


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Plan Pattern Learner - CLI Maintenance Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list                     List all patterns
  %(prog)s list --suggerable        List only suggerable patterns
  %(prog)s show "get_contacts"      Show details of a pattern
  %(prog)s stats                    Show global statistics
  %(prog)s delete "pattern" --confirm  Delete a pattern
  %(prog)s reset --confirm          Delete ALL patterns
  %(prog)s seed "pattern" --domains contacts,emails --intent mutation
  %(prog)s export > patterns.json   Export patterns
  %(prog)s import patterns.json --confirm  Import patterns
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List all patterns")
    p_list.add_argument("--suggerable", action="store_true", help="Only show suggerable patterns")
    p_list.add_argument(
        "--bypassable", action="store_true", help="Only show patterns that can bypass validation"
    )
    p_list.add_argument("--domain", type=str, help="Filter by domain")
    p_list.add_argument("--intent", type=str, choices=["read", "mutation"], help="Filter by intent")

    # show
    p_show = subparsers.add_parser("show", help="Show details of a pattern")
    p_show.add_argument(
        "pattern_key", type=str, help="Pattern key (e.g., 'get_contacts→send_email')"
    )

    # stats
    subparsers.add_parser("stats", help="Show global statistics")

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete a pattern")
    p_delete.add_argument("pattern_key", type=str, help="Pattern key to delete")
    p_delete.add_argument("--confirm", action="store_true", help="Confirm deletion")

    # reset
    p_reset = subparsers.add_parser("reset", help="Delete ALL patterns")
    p_reset.add_argument("--confirm", action="store_true", help="Confirm reset")

    # seed
    p_seed = subparsers.add_parser("seed", help="Seed a pattern with initial values")
    p_seed.add_argument("pattern_key", type=str, help="Pattern key")
    p_seed.add_argument("--domains", type=str, required=True, help="Comma-separated domains")
    p_seed.add_argument(
        "--intent", type=str, choices=["read", "mutation"], required=True, help="Intent type"
    )
    p_seed.add_argument("--successes", type=int, default=5, help="Initial successes (default: 5)")
    p_seed.add_argument("--failures", type=int, default=0, help="Initial failures (default: 0)")

    # export
    p_export = subparsers.add_parser("export", help="Export patterns to JSON")
    p_export.add_argument("--output", "-o", type=str, help="Output file (default: stdout)")

    # import
    p_import = subparsers.add_parser("import", help="Import patterns from JSON")
    p_import.add_argument("input", type=str, help="Input JSON file")
    p_import.add_argument("--confirm", action="store_true", help="Confirm import")

    # seed-golden
    p_golden = subparsers.add_parser("seed-golden", help="Seed predefined golden patterns")
    p_golden.add_argument(
        "--list", action="store_true", help="List golden patterns without seeding"
    )
    p_golden.add_argument("--reset", action="store_true", help="Delete all existing patterns first")
    p_golden.add_argument("--confirm", action="store_true", help="Confirm seeding")

    args = parser.parse_args()

    # Load .env
    try:
        from dotenv import load_dotenv

        env_file = Path(__file__).parent.parent.parent.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)
    except ImportError:
        pass

    # Dispatch to async command
    commands = {
        "list": cmd_list,
        "show": cmd_show,
        "stats": cmd_stats,
        "delete": cmd_delete,
        "reset": cmd_reset,
        "seed": cmd_seed,
        "export": cmd_export,
        "import": cmd_import,
        "seed-golden": cmd_seed_golden,
    }

    cmd_func = commands.get(args.command)
    if not cmd_func:
        print(f"Unknown command: {args.command}")
        return 1

    try:
        return asyncio.run(cmd_func(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
