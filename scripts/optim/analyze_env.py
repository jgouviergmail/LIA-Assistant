#!/usr/bin/env python3
"""
Audit .env Files for Unused/Missing Keys.

Strategy:
1. Parse .env.example and .env.prod.example
2. Extract all keys
3. Grep each key in src/core/config.py and src/
4. Flag unused keys (0 occurrences)
5. Parse config.py Field() definitions
6. Find keys missing from .env.example

Usage:
    python scripts/optim/analyze_env.py

Output:
    docs/optim/09_ENV_AUDIT.md

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-14
"""

import sys
import re
from pathlib import Path

# Add utils to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "utils"))

from grep_helper import grep_in_directory
from report_generator import generate_finding_report


# Configuration
ENV_EXAMPLE = Path("apps/api/.env.example")
ENV_PROD_EXAMPLE = Path(".env.prod.example")
CONFIG_FILE = Path("apps/api/src/core/config.py")
SRC_ROOT = Path("apps/api/src")
OUTPUT_FILE = Path("docs/optim/09_ENV_AUDIT.md")


def parse_env_file(file_path):
    """Parse .env file and extract keys."""
    if not file_path.exists():
        return {}

    keys = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Extract key=value
                match = re.match(r'^([A-Z_][A-Z0-9_]*)=', line)
                if match:
                    key = match.group(1)
                    keys[key] = line_num
    except Exception as e:
        print(f"[WARN]  Error reading {file_path}: {e}")

    return keys


def check_key_usage(key, src_root):
    """Check if env key is used in source code."""
    # Search in source
    results = grep_in_directory(
        key,
        src_root,
        extensions=['.py'],
        case_sensitive=True,
        regex=False
    )
    return len(results)


def analyze_env():
    """Main analysis function."""
    print("[*] Analyzing .env files...")
    print(f"   .env.example: {ENV_EXAMPLE}")
    print(f"   .env.prod.example: {ENV_PROD_EXAMPLE}")
    print(f"   Config file: {CONFIG_FILE}")
    print(f"   Output: {OUTPUT_FILE}\n")

    findings = []
    stats = {
        'env_example_keys': 0,
        'env_prod_keys': 0,
        'unused_keys': 0,
        'missing_keys': 0,
    }

    # Parse .env files
    env_example_keys = parse_env_file(ENV_EXAMPLE)
    env_prod_keys = parse_env_file(ENV_PROD_EXAMPLE)

    stats['env_example_keys'] = len(env_example_keys)
    stats['env_prod_keys'] = len(env_prod_keys)

    print(f"[SUMMARY] Parsed:")
    print(f"   .env.example: {len(env_example_keys)} keys")
    print(f"   .env.prod.example: {len(env_prod_keys)} keys\n")

    # Check unused keys in .env.example
    print("[CHECK] Checking .env.example for unused keys...")
    for key, line_num in sorted(env_example_keys.items()):
        usage_count = check_key_usage(key, SRC_ROOT)

        if usage_count == 0:
            stats['unused_keys'] += 1
            findings.append({
                'item': key,
                'location': f".env.example:{line_num}",
                'confidence': 'medium',  # Needs manual verification
                'reason': 'No usages found in source code',
                'details': 'May be Docker/infrastructure var'
            })
            print(f"   [WARN]  {key}: 0 usages")
        else:
            print(f"   [OK] {key}: {usage_count} usages")

    # Check for missing keys in .env.example
    print("\n[CHECK] Checking for missing keys in .env.example...")
    if CONFIG_FILE.exists():
        # Parse config.py for Field() definitions
        expected_keys = _extract_expected_keys_from_config(CONFIG_FILE)

        for key in expected_keys:
            if key not in env_example_keys:
                stats['missing_keys'] += 1
                findings.append({
                    'item': key,
                    'location': "config.py (missing from .env.example)",
                    'confidence': 'high',
                    'reason': 'Defined in config.py but missing from .env.example',
                    'details': 'Should be documented in .env.example'
                })
                print(f"   [WARN]  Missing: {key}")

    print(f"\n[SUMMARY] Summary:")
    print(f"   .env.example keys: {stats['env_example_keys']}")
    print(f"   .env.prod.example keys: {stats['env_prod_keys']}")
    print(f"   Unused keys: {stats['unused_keys']}")
    print(f"   Missing keys: {stats['missing_keys']}")
    print(f"   Total findings: {len(findings)}")

    return findings, stats


def _extract_expected_keys_from_config(config_file):
    """Extract env var names from config.py Field() definitions."""
    expected_keys = set()

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()

            # Pattern 1: Field(env="VAR_NAME")
            matches1 = re.findall(r'Field\([^)]*env=["\']([A-Z_][A-Z0-9_]*)["\']', content)
            expected_keys.update(matches1)

            # Pattern 2: os.getenv("VAR_NAME")
            matches2 = re.findall(r'os\.getenv\(["\']([A-Z_][A-Z0-9_]*)["\']', content)
            expected_keys.update(matches2)

            # Pattern 3: os.environ.get("VAR_NAME")
            matches3 = re.findall(r'os\.environ\.get\(["\']([A-Z_][A-Z0-9_]*)["\']', content)
            expected_keys.update(matches3)

    except Exception as e:
        print(f"[WARN]  Error parsing config.py: {e}")

    return expected_keys


def generate_report(findings, stats):
    """Generate markdown report."""
    additional_sections = {
        "[SUMMARY] Statistics": f"""
- **.env.example keys**: {stats['env_example_keys']}
- **.env.prod.example keys**: {stats['env_prod_keys']}
- **Unused keys**: {stats['unused_keys']}
- **Missing keys**: {stats['missing_keys']}

---

## [WARN] Key Types

### Application Keys
Variables used by `src/core/config.py` (Pydantic Settings)
-> **Must be in .env.example**

### Infrastructure Keys
Variables for Docker Compose, Grafana, Prometheus, etc.
-> **May not be in config.py** (normal)

Infrastructure key examples:
- `POSTGRES_USER`, `POSTGRES_PASSWORD` (Docker)
- `GRAFANA_ADMIN_*` (Grafana container)
- `ALERTMANAGER_*` (Alertmanager container)

---

## Manual Verifications

For each unused key:

### 1. Is It an Infrastructure Key?
```bash
# Docker Compose keys
grep KEY_NAME docker-compose*.yml
```
-> If found -> KEEP (infrastructure)

### 2. Is It Referenced Indirectly?
```python
# Via getattr, os.environ, etc.
os.environ.get(f"{{prefix}}_KEY_NAME")
```
-> Grep for dynamic usage

### 3. Is It Documented?
- Mentioned in README.md
- Commented in .env.example

-> If documented but unused -> Potential legacy

### 4. Is It Optional?
- Feature flags
- Optional services
- Development only

-> If optional -> KEEP with comment

---

## Recommendations

### Unused Keys
1. **Check if infrastructure** (Docker, monitoring)
2. **If application AND unused** -> Remove from .env.example
3. **If in doubt** -> Keep with comment

### Missing Keys
1. **Add to .env.example**
2. **Document usage**
3. **Provide default value or example**

### .env.example Organization
Add clear sections:

```bash
# ========================================
# APPLICATION CONFIGURATION
# ========================================
DATABASE_URL=...
REDIS_URL=...

# ========================================
# INFRASTRUCTURE (Docker Compose)
# ========================================
POSTGRES_USER=...
GRAFANA_ADMIN_PASSWORD=...
```

---

## Next Steps

1. [OK] Manual review of each finding
2. Pending - For unused keys:
   - Check infrastructure
   - Delete if truly unused
3. Pending - For missing keys:
   - Add to .env.example
   - Document
4. Pending - Reorganize .env.example with sections
""",
        "Notes": """
- Infrastructure keys (Docker, Grafana) are normal in .env but not in code
- Optional keys should be documented even if rarely used
- Always check docker-compose*.yml before deleting
"""
    }

    generate_finding_report(
        title="Environment Variables Audit",
        findings=findings,
        output_path=OUTPUT_FILE,
        script_name="analyze_env.py",
        additional_sections=additional_sections
    )


if __name__ == "__main__":
    print("=" * 60)
    print("  .env Audit - LIA")
    print("=" * 60)
    print()

    try:
        findings, stats = analyze_env()
        generate_report(findings, stats)

        print(f"\n[OK] Analysis complete!")
        print(f"   Report: {OUTPUT_FILE}")
        print(f"   Findings: {len(findings)}")
        print(f"\n[NEXT] Next: Review findings manually in {OUTPUT_FILE}")

    except KeyboardInterrupt:
        print("\n\n[WARN]  Analysis interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
