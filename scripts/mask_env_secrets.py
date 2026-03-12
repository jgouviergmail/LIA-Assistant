#!/usr/bin/env python3
"""
Mask sensitive values in .env.example file
Preserves all structure, comments, and variable names
Only masks actual secret values
"""

import re
from pathlib import Path

# Sensitive variable patterns to mask
SENSITIVE_VARS = [
    # Security keys
    "SECRET_KEY",
    "FERNET_KEY",
    # OAuth secrets
    "GOOGLE_CLIENT_SECRET",
    # LLM API keys
    "OPENAI_API_KEY",
    "OPENAI_ORGANIZATION_ID",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "PERPLEXITY_API_KEY",
    # SMTP/Alertmanager credentials
    "ALERTMANAGER_SMTP_AUTH_PASSWORD",
    "ALERTMANAGER_SMTP_AUTH_USERNAME",
    "APPLICATION_SMTP_FROM",
    "ALERTMANAGER_SMTP_FROM",
    "ALERTMANAGER_BACKEND_TEAM_EMAIL",
    "ALERTMANAGER_FINANCE_TEAM_EMAIL",
    "ALERTMANAGER_SECURITY_TEAM_EMAIL",
    "ALERTMANAGER_ML_TEAM_EMAIL",
    # Langfuse secrets
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    # Database passwords (in URLs)
    # Handled separately with regex
]

def mask_env_file(input_path: Path, output_path: Path):
    """Mask sensitive values while preserving structure."""

    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    masked_lines = []

    for line in lines:
        # Skip comments and empty lines
        if line.strip().startswith('#') or not line.strip():
            masked_lines.append(line)
            continue

        # Check if line is a variable assignment
        if '=' in line:
            var_name = line.split('=')[0].strip()

            # Mask sensitive variables
            if var_name in SENSITIVE_VARS:
                # Keep variable name and = sign, mask value
                masked_lines.append(f"{var_name}=CHANGE_ME_{var_name}\n")
            # Special handling for DATABASE_URL (contains password)
            elif 'DATABASE_URL' in var_name:
                # Replace password in postgres://user:password@host pattern
                masked_line = re.sub(
                    r'(postgresql\+asyncpg://[^:]+:)[^@]+(@)',
                    r'\1CHANGE_ME_DB_PASSWORD\2',
                    line
                )
                masked_lines.append(masked_line)
            else:
                # Keep line as-is
                masked_lines.append(line)
        else:
            masked_lines.append(line)

    # Write masked content
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(masked_lines)

    print(f"[OK] Masked {input_path} -> {output_path}")
    print(f"     Processed {len(lines)} lines, masked {len(SENSITIVE_VARS)} sensitive variables")

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    input_file = project_root / ".env.development"
    output_file = project_root / ".env.example"

    if not input_file.exists():
        print(f"[ERROR] Input file not found: {input_file}")
        exit(1)

    mask_env_file(input_file, output_file)
