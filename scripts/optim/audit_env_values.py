#!/usr/bin/env python3
"""Audit env value drift across .env files and Python defaults.

Source of truth: ``.env.prod``.

This script reports — without modifying anything — every key whose value
diverges from ``.env.prod``:

1. ``.env.prod`` vs ``.env.example``
2. ``.env.prod`` vs ``.env.prod.example``
3. ``.env.prod`` vs ``Field(default=...)`` in ``apps/api/src/core/config/*.py``
   (resolving constants imported from ``apps/api/src/core/constants.py`` when
   the default is a name reference rather than a literal).

Secrets and environment-specific keys are filtered out using two heuristics
(name regex + placeholder value detection), since they are expected to differ
between environments by design.

Usage:
    python scripts/optim/audit_env_values.py

Output:
    docs/optim/ENV_VALUE_AUDIT.md
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

ENV_PROD = REPO_ROOT / ".env.prod"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
ENV_PROD_EXAMPLE = REPO_ROOT / ".env.prod.example"
CONFIG_DIR = REPO_ROOT / "apps" / "api" / "src" / "core" / "config"
CONSTANTS_FILE = REPO_ROOT / "apps" / "api" / "src" / "core" / "constants.py"
OUTPUT_FILE = REPO_ROOT / "docs" / "optim" / "ENV_VALUE_AUDIT.md"

# Keys whose value is a secret — excluded from comparison (placeholder by design).
SECRET_NAME_PATTERNS = [
    re.compile(r"_KEY$"),                    # API_KEY, PRIVATE_KEY, PUBLIC_KEY, ENCRYPTION_KEY, ...
    re.compile(r"_PASSWORD$"),
    re.compile(r"_SECRET$"),
    re.compile(r"_TOKEN$"),
    re.compile(r"_CLIENT_ID$"),
    re.compile(r"_CLIENT_SECRET$"),
    re.compile(r"^SECRET_KEY$"),
    re.compile(r"^FERNET_KEY$"),
    re.compile(r"_SALT$"),
    re.compile(r"_SERVICE_ACCOUNT$"),
    re.compile(r"_CREDENTIALS$"),
]

# Keys whose value is environment-specific (URLs, domains, ports, env mode). Excluded too.
ENV_SPECIFIC_NAME_PATTERNS = [
    re.compile(r"_URL($|_)"),               # FOO_URL, FOO_URL_SERVER, FOO_URL_SERVER_HTTP
    re.compile(r"^API_URL"),                # API_URL, API_URL_SERVER, API_URL_SERVER_HTTP
    re.compile(r"_URI$"),                   # GOOGLE_REDIRECT_URI, etc.
    re.compile(r"_DOMAIN$"),
    re.compile(r"_HOST($|_)"),              # FOO_HOST, FOO_HOST_PORT, FOO_SMARTHOST is matched separately below
    re.compile(r"_SMARTHOST$"),
    re.compile(r"_FROM$"),                  # SMTP_FROM (from-email)
    re.compile(r"_PROJECT_ID$"),
    re.compile(r"_ORGANIZATION_ID$"),
    re.compile(r"_APP_ID$"),
    re.compile(r"_SERVERS_CONFIG$"),
    re.compile(r"^CORS_ORIGINS$"),
    re.compile(r"_ORIGIN$"),
    re.compile(r"_ORIGINS$"),
    re.compile(r"_HOST_PORT$"),
    re.compile(r"_ENDPOINT$"),
    re.compile(r"_WEBHOOK$"),
    re.compile(r"_BASE_URL$"),
    re.compile(r"^DATABASE_URL$"),
    re.compile(r"^REDIS_URL$"),
    # Per-environment runtime mode (intentionally differs in dev vs prod files)
    re.compile(r"^ENVIRONMENT$"),
    re.compile(r"^DEBUG$"),
    re.compile(r"^NODE_ENV$"),
    re.compile(r"^LOG_LEVEL$"),
    re.compile(r"^NEXT_PUBLIC_LOG_LEVEL$"),
    re.compile(r"^LANGFUSE_DEBUG$"),
    re.compile(r"^LANGFUSE_RELEASE$"),
    # Deployment-specific identifiers (admin emails, bot usernames, etc.)
    re.compile(r"_EMAIL$"),
    re.compile(r"_USERNAME$"),
    re.compile(r"_USER$"),
    re.compile(r"_BOT_NAME$"),
]

# Placeholder markers — any value containing one of these is considered a placeholder.
PLACEHOLDER_MARKERS = (
    "CHANGE_ME",
    "your-",
    "yourdomain",
    "your_",
    "<your-",
    "REPLACE_ME",
    "TODO",
)


@dataclass
class EnvEntry:
    key: str
    value: str
    line: int


@dataclass
class PyDefault:
    """A Python Field default for a settings attribute."""

    env_name: str          # uppercase env var equivalent (e.g. HEALTH_METRICS_ENABLED)
    py_attr: str           # snake_case Pydantic attribute (e.g. health_metrics_enabled)
    raw_default: str       # source-form default expression (e.g. "60", "HEALTH_..._DEFAULT", "openai")
    resolved_value: str | None  # canonical string form for comparison, or None if unresolvable
    file: Path
    line: int
    via_constant: str | None = None  # name of the constant if the default was a Name reference


# --------------------------------------------------------------------------- #
# .env parsing
# --------------------------------------------------------------------------- #


def parse_env(path: Path) -> dict[str, EnvEntry]:
    """Parse a .env file and return ``{KEY: EnvEntry}`` (last assignment wins)."""
    entries: dict[str, EnvEntry] = {}
    if not path.exists():
        return entries
    pattern = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
    with path.open("r", encoding="utf-8") as fh:
        for line_num, raw in enumerate(fh, start=1):
            stripped = raw.rstrip("\r\n")
            if not stripped or stripped.lstrip().startswith("#"):
                continue
            match = pattern.match(stripped)
            if not match:
                continue
            key, value = match.group(1), match.group(2)
            # Strip inline comment only when value is unquoted and a clear " #" appears
            if not (value.startswith('"') or value.startswith("'")):
                hash_pos = value.find(" #")
                if hash_pos != -1:
                    value = value[:hash_pos]
            value = value.strip()
            # Strip surrounding quotes for comparison stability
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            entries[key] = EnvEntry(key=key, value=value, line=line_num)
    return entries


def is_excluded_key(name: str) -> bool:
    """Return True for secrets and environment-specific keys."""
    for pattern in SECRET_NAME_PATTERNS + ENV_SPECIFIC_NAME_PATTERNS:
        if pattern.search(name):
            return True
    return False


def looks_like_placeholder(value: str) -> bool:
    upper = value.upper()
    if not value:
        return True
    return any(marker.upper() in upper for marker in PLACEHOLDER_MARKERS)


# --------------------------------------------------------------------------- #
# Python AST parsing — constants and Field defaults
# --------------------------------------------------------------------------- #


def _eval_numeric(node: ast.AST) -> int | float | None:
    """Safely evaluate numeric literal expressions: constants, unary -, BinOp +-*/."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _eval_numeric(node.operand)
        return -inner if inner is not None else None
    if isinstance(node, ast.BinOp):
        left = _eval_numeric(node.left)
        right = _eval_numeric(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
    return None


def _literal_to_str(node: ast.AST) -> str | None:
    """Return canonical string for a literal AST node, or None if non-literal."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "true" if node.value else "false"
        if node.value is None:
            return ""
        return str(node.value)
    numeric = _eval_numeric(node)
    if numeric is not None:
        # Drop trailing .0 for whole-number floats so "30.0" matches "30"
        if isinstance(numeric, float) and numeric.is_integer():
            return str(int(numeric))
        return str(numeric)
    if isinstance(node, ast.List | ast.Tuple):
        items = [_literal_to_str(elt) for elt in node.elts]
        if all(item is not None for item in items):
            # JSON-like form so it matches Pydantic-friendly env representations
            # (e.g. ``["admin","power_user"]``) instead of CSV.
            quoted = []
            for raw_item, ast_item in zip(items, node.elts, strict=True):
                if isinstance(ast_item, ast.Constant) and isinstance(ast_item.value, str):
                    quoted.append(f'"{raw_item}"')
                else:
                    quoted.append(raw_item)  # type: ignore[arg-type]
            return "[" + ",".join(quoted) + "]"
    return None


def parse_constants(path: Path) -> dict[str, str]:
    """Parse top-level literal constants from constants.py."""
    constants: dict[str, str] = {}
    if not path.exists():
        return constants
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        target_name: str | None = None
        value_node: ast.AST | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            target_name = node.target.id
            value_node = node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            value_node = node.value
        if target_name is None or value_node is None:
            continue
        literal = _literal_to_str(value_node)
        if literal is not None:
            constants[target_name] = literal
    return constants


def _extract_field_default(call: ast.Call) -> ast.AST | None:
    """Return the AST node for the ``default=`` arg of a Field() call."""
    for kw in call.keywords:
        if kw.arg == "default":
            return kw.value
    if call.args:
        return call.args[0]  # Field(default_value, ...) positional
    return None


def parse_config_module(path: Path, constants: dict[str, str]) -> list[PyDefault]:
    """Parse a config module and extract all Field() defaults."""
    results: list[PyDefault] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return results

    for class_node in tree.body:
        if not isinstance(class_node, ast.ClassDef):
            continue
        # Only inspect classes that look like Pydantic settings
        base_names = [b.id for b in class_node.bases if isinstance(b, ast.Name)]
        if not any("Settings" in name for name in base_names):
            continue
        for item in class_node.body:
            if not isinstance(item, ast.AnnAssign) or not isinstance(item.target, ast.Name):
                continue
            attr_name = item.target.id
            value_node = item.value
            if value_node is None:
                continue

            default_node: ast.AST | None = None
            if (
                isinstance(value_node, ast.Call)
                and isinstance(value_node.func, ast.Name)
                and value_node.func.id == "Field"
            ):
                default_node = _extract_field_default(value_node)
            else:
                default_node = value_node

            if default_node is None:
                continue

            via_constant: str | None = None
            resolved: str | None = None
            raw_default = ast.unparse(default_node)

            if isinstance(default_node, ast.Name):
                via_constant = default_node.id
                resolved = constants.get(default_node.id)
            else:
                resolved = _literal_to_str(default_node)

            results.append(
                PyDefault(
                    env_name=attr_name.upper(),
                    py_attr=attr_name,
                    raw_default=raw_default,
                    resolved_value=resolved,
                    file=path,
                    line=item.lineno,
                    via_constant=via_constant,
                )
            )
    return results


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #


def values_equal(env_value: str, py_value: str) -> bool:
    """Compare an env (string) value with a resolved Python default (string)."""
    a = env_value.strip()
    b = py_value.strip()
    if a == b:
        return True
    # Boolean tolerance
    bool_synonyms = {
        "true": {"true", "1", "yes", "on"},
        "false": {"false", "0", "no", "off", ""},
    }
    a_lower, b_lower = a.lower(), b.lower()
    for canonical, synonyms in bool_synonyms.items():
        if a_lower in synonyms and b_lower in synonyms and (a_lower == canonical or b_lower == canonical):
            if a_lower in synonyms and b_lower in synonyms:
                # Same canonical only
                if (a_lower == canonical or a_lower in synonyms) and (b_lower == canonical or b_lower in synonyms):
                    if (a_lower in bool_synonyms["true"]) == (b_lower in bool_synonyms["true"]):
                        return True
    # Numeric tolerance (60 == 60.0)
    try:
        if float(a) == float(b):
            return True
    except (ValueError, TypeError):
        pass
    return False


@dataclass
class FileDriftRow:
    key: str
    prod_value: str
    other_value: str
    prod_line: int
    other_line: int


@dataclass
class PyDriftRow:
    key: str
    prod_value: str
    py_value: str
    raw_default: str
    via_constant: str | None
    py_file: str
    py_line: int


def compare_env_files(
    prod: dict[str, EnvEntry],
    other: dict[str, EnvEntry],
) -> tuple[list[FileDriftRow], list[str], list[str]]:
    """Return (drift_rows, only_in_prod, only_in_other) with exclusions applied."""
    drift: list[FileDriftRow] = []
    only_in_prod: list[str] = []
    only_in_other: list[str] = []

    for key, prod_entry in prod.items():
        if is_excluded_key(key):
            continue
        if key not in other:
            only_in_prod.append(key)
            continue
        other_entry = other[key]
        # Skip if other side is a placeholder — secrets/URLs that escaped name patterns
        if looks_like_placeholder(other_entry.value) and not looks_like_placeholder(prod_entry.value):
            continue
        if not values_equal(prod_entry.value, other_entry.value):
            drift.append(
                FileDriftRow(
                    key=key,
                    prod_value=prod_entry.value,
                    other_value=other_entry.value,
                    prod_line=prod_entry.line,
                    other_line=other_entry.line,
                )
            )
    for key in other:
        if is_excluded_key(key):
            continue
        if key not in prod:
            only_in_other.append(key)
    return drift, sorted(only_in_prod), sorted(only_in_other)


def compare_env_with_python(
    prod: dict[str, EnvEntry],
    py_defaults: dict[str, PyDefault],
) -> tuple[list[PyDriftRow], list[str], list[str]]:
    """Return (drift_rows, env_without_py_default, py_default_without_env)."""
    drift: list[PyDriftRow] = []
    env_without_py: list[str] = []
    py_without_env: list[str] = []

    for key, prod_entry in prod.items():
        if is_excluded_key(key):
            continue
        py = py_defaults.get(key)
        if py is None:
            env_without_py.append(key)
            continue
        if py.resolved_value is None:
            # Cannot resolve (complex expression) — surface in a separate section
            drift.append(
                PyDriftRow(
                    key=key,
                    prod_value=prod_entry.value,
                    py_value="<unresolved>",
                    raw_default=py.raw_default,
                    via_constant=py.via_constant,
                    py_file=str(py.file.relative_to(REPO_ROOT)).replace("\\", "/"),
                    py_line=py.line,
                )
            )
            continue
        if not values_equal(prod_entry.value, py.resolved_value):
            drift.append(
                PyDriftRow(
                    key=key,
                    prod_value=prod_entry.value,
                    py_value=py.resolved_value,
                    raw_default=py.raw_default,
                    via_constant=py.via_constant,
                    py_file=str(py.file.relative_to(REPO_ROOT)).replace("\\", "/"),
                    py_line=py.line,
                )
            )
    for key in py_defaults:
        if is_excluded_key(key):
            continue
        if key not in prod:
            py_without_env.append(key)
    return drift, sorted(env_without_py), sorted(py_without_env)


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #


def _truncate(text: str, limit: int = 80) -> str:
    text = text.replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _md_table_file_drift(rows: list[FileDriftRow]) -> str:
    if not rows:
        return "_(none)_\n"
    lines = [
        "| Key | `.env.prod` value | Other file value | prod L. | other L. |",
        "|---|---|---|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| `{row.key}` | `{_truncate(row.prod_value)}` | `{_truncate(row.other_value)}` | "
            f"{row.prod_line} | {row.other_line} |"
        )
    return "\n".join(lines) + "\n"


def _md_table_py_drift(rows: list[PyDriftRow]) -> str:
    if not rows:
        return "_(none)_\n"
    lines = [
        "| Key | `.env.prod` | Python default | Source | Location |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        if row.via_constant is None:
            source = f"literal `{_truncate(row.raw_default, 60)}`"
        else:
            source = f"constant `{row.via_constant}`"
        lines.append(
            f"| `{row.key}` | `{_truncate(row.prod_value, 50)}` | `{_truncate(row.py_value, 50)}` | "
            f"{source} | `{row.py_file}:{row.py_line}` |"
        )
    return "\n".join(lines) + "\n"


def _bullet_list(keys: list[str], limit: int = 80) -> str:
    if not keys:
        return "_(none)_\n"
    head = keys[:limit]
    out = "\n".join(f"- `{key}`" for key in head) + "\n"
    if len(keys) > limit:
        out += f"\n_… and {len(keys) - limit} more._\n"
    return out


def render_report(
    *,
    prod_count: int,
    example_drift: list[FileDriftRow],
    example_only_prod: list[str],
    example_only_other: list[str],
    prod_example_drift: list[FileDriftRow],
    prod_example_only_prod: list[str],
    prod_example_only_other: list[str],
    py_drift: list[PyDriftRow],
    env_without_py: list[str],
    py_without_env: list[str],
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts: list[str] = []
    parts.append("# ENV value drift audit\n")
    parts.append(f"_Generated {now} by `scripts/optim/audit_env_values.py`._\n")
    parts.append(
        "Source of truth: **`.env.prod`**. Secrets and environment-specific keys "
        "(API keys, passwords, URLs, domains, host ports, endpoints) are excluded "
        "from comparison via name regex + placeholder detection.\n"
    )
    parts.append("## Summary\n")
    parts.append(
        f"- `.env.prod` keys (after exclusions): **{prod_count}**\n"
        f"- Drift `.env.prod` ↔ `.env.example`: **{len(example_drift)}** value mismatches, "
        f"{len(example_only_prod)} keys only in prod, {len(example_only_other)} keys only in example\n"
        f"- Drift `.env.prod` ↔ `.env.prod.example`: **{len(prod_example_drift)}** value mismatches, "
        f"{len(prod_example_only_prod)} keys only in prod, {len(prod_example_only_other)} keys only in template\n"
        f"- Drift `.env.prod` ↔ Python `Field(default=...)`: **{len(py_drift)}** value mismatches, "
        f"{len(env_without_py)} env keys without Python default, {len(py_without_env)} Python defaults without env key\n"
    )
    parts.append("---\n")
    parts.append("## 1. `.env.prod` vs `.env.example`\n")
    parts.append("### Value mismatches\n")
    parts.append(_md_table_file_drift(example_drift))
    parts.append("\n### Keys only in `.env.prod`\n")
    parts.append(_bullet_list(example_only_prod))
    parts.append("\n### Keys only in `.env.example` (likely dev-only — review)\n")
    parts.append(_bullet_list(example_only_other))
    parts.append("\n---\n")
    parts.append("## 2. `.env.prod` vs `.env.prod.example`\n")
    parts.append("### Value mismatches\n")
    parts.append(_md_table_file_drift(prod_example_drift))
    parts.append("\n### Keys only in `.env.prod`\n")
    parts.append(_bullet_list(prod_example_only_prod))
    parts.append("\n### Keys only in `.env.prod.example`\n")
    parts.append(_bullet_list(prod_example_only_other))
    parts.append("\n---\n")
    parts.append("## 3. `.env.prod` vs Python `Field(default=...)`\n")
    parts.append(
        "Resolution rules:\n"
        "- Literal default (`Field(default=60)`) → compared directly.\n"
        "- Name reference (`Field(default=FOO_DEFAULT)`) → resolved by parsing "
        "`apps/api/src/core/constants.py`. If the constant itself is non-literal, the "
        "row appears with `<unresolved>`.\n\n"
    )
    parts.append("### Value mismatches\n")
    parts.append(_md_table_py_drift(py_drift))
    parts.append("\n### `.env.prod` keys without Python default\n")
    parts.append(
        "_These env vars are read elsewhere (raw `os.environ`, third-party libs, "
        "Docker compose, etc.) — not actionable for default alignment, but listed for awareness._\n\n"
    )
    parts.append(_bullet_list(env_without_py, limit=120))
    parts.append("\n### Python defaults without entry in `.env.prod`\n")
    parts.append(_bullet_list(py_without_env, limit=120))
    parts.append("\n---\n")
    parts.append(
        "**Next step**: review value mismatches above; for each row, decide whether to "
        "(a) align the secondary file/Python default on `.env.prod`, or (b) update `.env.prod` "
        "if the production value is itself stale.\n"
    )
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> int:
    print(f"[INFO] Repo root: {REPO_ROOT}")
    if not ENV_PROD.exists():
        print(f"[ERROR] Source of truth not found: {ENV_PROD}")
        return 1

    print("[INFO] Parsing .env files...")
    prod = parse_env(ENV_PROD)
    example = parse_env(ENV_EXAMPLE)
    prod_example = parse_env(ENV_PROD_EXAMPLE)
    print(f"[INFO]   .env.prod         : {len(prod)} keys")
    print(f"[INFO]   .env.example      : {len(example)} keys")
    print(f"[INFO]   .env.prod.example : {len(prod_example)} keys")

    print("[INFO] Parsing Python constants...")
    constants = parse_constants(CONSTANTS_FILE)
    print(f"[INFO]   resolved literal constants: {len(constants)}")

    print("[INFO] Parsing config modules...")
    py_defaults: dict[str, PyDefault] = {}
    duplicates: list[str] = []
    for module in sorted(CONFIG_DIR.glob("*.py")):
        if module.name.startswith("__"):
            continue
        for item in parse_config_module(module, constants):
            if item.env_name in py_defaults:
                duplicates.append(item.env_name)
            py_defaults[item.env_name] = item
    print(f"[INFO]   Python Field() defaults: {len(py_defaults)} (duplicates: {len(set(duplicates))})")

    eligible_prod_count = sum(1 for k in prod if not is_excluded_key(k))

    print("[INFO] Comparing .env.prod vs .env.example...")
    ex_drift, ex_only_prod, ex_only_other = compare_env_files(prod, example)

    print("[INFO] Comparing .env.prod vs .env.prod.example...")
    pe_drift, pe_only_prod, pe_only_other = compare_env_files(prod, prod_example)

    print("[INFO] Comparing .env.prod vs Python Field defaults...")
    py_drift, env_no_py, py_no_env = compare_env_with_python(prod, py_defaults)

    report = render_report(
        prod_count=eligible_prod_count,
        example_drift=ex_drift,
        example_only_prod=ex_only_prod,
        example_only_other=ex_only_other,
        prod_example_drift=pe_drift,
        prod_example_only_prod=pe_only_prod,
        prod_example_only_other=pe_only_other,
        py_drift=py_drift,
        env_without_py=env_no_py,
        py_without_env=py_no_env,
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(report, encoding="utf-8")

    print("\n[SUMMARY]")
    print(f"  .env.prod vs .env.example         : {len(ex_drift)} value mismatches")
    print(f"  .env.prod vs .env.prod.example    : {len(pe_drift)} value mismatches")
    print(f"  .env.prod vs Python Field defaults: {len(py_drift)} value mismatches")
    print(f"\n[OUTPUT] Report: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
