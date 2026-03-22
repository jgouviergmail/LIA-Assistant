"""
Refactoring script: Replace all hardcoded defaults in config files with named constants.

This script:
1. Scans all config files for Field(default=X) where X is a literal value
2. Creates named constants in constants.py (aligned with .env.prod values)
3. Adds imports to each config file
4. Replaces hardcoded defaults with constant names

Run from project root: python scripts/refactor_config_defaults.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
API_ROOT = ROOT / "apps" / "api"
CONSTANTS_FILE = API_ROOT / "src" / "core" / "constants.py"
CONFIG_DIR = API_ROOT / "src" / "core" / "config"

# Fields to skip (env-specific, not default-able)
SKIP_FIELDS = {
    "environment", "debug", "api_host", "api_port", "cors_origins",
    "session_cookie_samesite", "frontend_url", "api_url", "api_url_server",
    "api_url_server_http", "microsoft_tenant_id", "alertmanager_smtp_smarthost",
    "application_smtp_from", "google_api_key", "google_client_id",
    "google_client_secret", "google_redirect_uri", "otel_exporter_otlp_endpoint",
    "langfuse_host", "langfuse_public_key", "langfuse_secret_key", "langfuse_release",
    "fernet_key", "firebase_project_id", "mcp_servers_config",
    "hue_remote_client_id", "hue_remote_client_secret", "hue_remote_app_id",
    "http_log_exclude_paths", "log_level", "log_level_httpx", "log_level_sqlalchemy",
    "log_level_uvicorn", "log_level_uvicorn_access", "next_public_app_url",
    "docker_container", "openai_api_key", "openai_organization_id",
    "anthropic_api_key", "deepseek_api_key", "perplexity_api_key",
    "ollama_base_url", "gemini_api_key", "qwen_api_key", "qwen_base_url",
    "openweathermap_api_key", "google_api_key", "google_places_api_key",
}


def read_env_prod() -> dict[str, str]:
    """Read .env.prod values."""
    env_values = {}
    env_file = ROOT / ".env.prod"
    if not env_file.exists():
        print(f"WARNING: {env_file} not found, using code defaults only")
        return env_values
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                val = val.split("#")[0].strip()
                env_values[key.strip()] = val
    return env_values


def find_existing_constants() -> set[str]:
    """Find constant names already defined in constants.py."""
    existing = set()
    with open(CONSTANTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^([A-Z][A-Z_0-9]+)\s*=", line)
            if m:
                existing.add(m.group(1))
    return existing


def scan_config_file(filepath: Path, env_values: dict[str, str]) -> list[dict]:
    """Scan a config file for hardcoded defaults and return entries to fix."""
    entries = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        m = re.match(r"^(\s+)(\w+):\s+\S+.*=\s*Field\(\s*$", line)
        if m and i + 1 < len(lines):
            field_name = m.group(2)
            next_line = lines[i + 1]
            next_stripped = next_line.strip()
            dm = re.match(r"default=([^,\)]+)", next_stripped)
            if dm:
                default_val = dm.group(1).strip()

                # Skip if already using a named constant
                if re.match(r"^[A-Z][A-Z_0-9]+$", default_val):
                    continue
                # Skip None, True, False
                if default_val in ("None", "True", "False"):
                    continue
                # Skip env-specific fields
                if field_name in SKIP_FIELDS:
                    continue

                const_name = f"{field_name.upper()}_DEFAULT"
                env_key = field_name.upper()
                env_val = env_values.get(env_key)

                # Determine correct value
                code_stripped = default_val.strip('"').strip("'")

                if env_val and env_val != code_stripped:
                    final_val = env_val
                    aligned = True
                else:
                    final_val = code_stripped
                    aligned = False

                entries.append({
                    "field_name": field_name,
                    "const_name": const_name,
                    "code_default": default_val,
                    "code_stripped": code_stripped,
                    "final_val": final_val,
                    "aligned": aligned,
                    "line_num": i + 2,  # 1-indexed, next line
                })

    return entries


def format_const_value(val: str) -> str:
    """Format a value for a Python constant assignment."""
    # Try numeric
    try:
        if "." in val:
            float(val)
            return val
        else:
            int(val)
            return val
    except ValueError:
        return f'"{val}"'


def add_constants_to_file(entries: list[dict], section_name: str, existing: set[str]) -> str:
    """Generate constants block for a section."""
    lines = [f"\n# --- {section_name} config defaults ---"]
    for entry in entries:
        if entry["const_name"] in existing:
            continue  # Already exists
        val_repr = format_const_value(entry["final_val"])
        comment = ""
        if entry["aligned"]:
            comment = f"  # Aligned from .env.prod (was {entry['code_stripped']})"
        lines.append(f'{entry["const_name"]} = {val_repr}{comment}')
    return "\n".join(lines) + "\n"


def update_config_file(filepath: Path, entries: list[dict]) -> int:
    """Update a config file: add imports and replace defaults."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        lines = content.split("\n")

    # Collect constant names to import
    const_names = [e["const_name"] for e in entries]

    if not const_names:
        return 0

    # Find existing import block from constants
    import_pattern = re.compile(
        r"(from src\.core\.constants import \(.*?\))",
        re.DOTALL,
    )
    import_match = import_pattern.search(content)

    if import_match:
        # Parse existing imports
        existing_imports = set(
            re.findall(r"\b([A-Z][A-Z_0-9]+)\b", import_match.group(1))
        )
        # Add new imports
        all_imports = sorted(existing_imports | set(const_names))
        # Rebuild import block
        import_lines = ["from src.core.constants import ("]
        for imp in all_imports:
            import_lines.append(f"    {imp},")
        import_lines.append(")")
        new_import_block = "\n".join(import_lines)
        content = content[:import_match.start()] + new_import_block + content[import_match.end():]
    else:
        # No existing import from constants - add one after other imports
        # Find last import line
        import_insert = "from src.core.constants import (\n"
        for cn in sorted(const_names):
            import_insert += f"    {cn},\n"
        import_insert += ")\n"
        # Insert after the last top-level import
        last_import_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                last_import_idx = i
        lines.insert(last_import_idx + 1, import_insert)
        content = "\n".join(lines)

    # Replace hardcoded defaults with constant names
    replacements = 0
    for entry in entries:
        old = f"default={entry['code_default']},"
        new = f"default={entry['const_name']},"
        if old in content:
            content = content.replace(old, new, 1)
            replacements += 1
        else:
            # Try without trailing comma (last param)
            old_no_comma = f"default={entry['code_default']}"
            if old_no_comma in content:
                content = content.replace(old_no_comma, f"default={entry['const_name']}", 1)
                replacements += 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return replacements


def main() -> None:
    env_values = read_env_prod()
    existing_constants = find_existing_constants()

    config_files = [
        ("agents.py", "Agents"),
        ("connectors.py", "Connectors"),
        ("journals.py", "Journals"),
        ("database.py", "Database"),
        ("advanced.py", "Advanced"),
        ("llm.py", "LLM"),
        ("observability.py", "Observability"),
        ("voice.py", "Voice"),
        ("mcp.py", "MCP"),
    ]

    # Phase 1: Scan all config files
    all_entries: dict[str, list[dict]] = {}
    total_entries = 0
    for fname, section in config_files:
        filepath = CONFIG_DIR / fname
        if not filepath.exists():
            continue
        entries = scan_config_file(filepath, env_values)
        if entries:
            all_entries[fname] = entries
            total_entries += len(entries)
            print(f"  {fname}: {len(entries)} hardcoded defaults found")

    print(f"\nTotal: {total_entries} constants to create\n")

    # Phase 2: Add constants to constants.py
    new_constants_text = ""
    new_const_names = set()
    for fname, section in config_files:
        if fname in all_entries:
            new_entries = [e for e in all_entries[fname] if e["const_name"] not in existing_constants]
            if new_entries:
                new_constants_text += add_constants_to_file(new_entries, section, existing_constants)
                for e in new_entries:
                    new_const_names.add(e["const_name"])

    if new_constants_text:
        # Find insertion point: before the PROMPT CACHING section or at end
        with open(CONSTANTS_FILE, "r", encoding="utf-8") as f:
            constants_content = f.read()

        # Insert before the last section marker or at end
        marker = "# ============================================================================\n# PROMPT CACHING"
        if marker in constants_content:
            constants_content = constants_content.replace(
                marker,
                new_constants_text + "\n" + marker,
            )
        else:
            constants_content += new_constants_text

        with open(CONSTANTS_FILE, "w", encoding="utf-8") as f:
            f.write(constants_content)

        print(f"Added {len(new_const_names)} new constants to constants.py")
    else:
        print("No new constants needed (all already exist)")

    # Phase 3: Update config files
    for fname, section in config_files:
        if fname in all_entries:
            filepath = CONFIG_DIR / fname
            replacements = update_config_file(filepath, all_entries[fname])
            print(f"  {fname}: {replacements} defaults replaced with constants")

    print(f"\nDone! Run 'ruff check --fix' and 'py_compile' to verify.")


if __name__ == "__main__":
    main()
