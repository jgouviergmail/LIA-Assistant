#!/usr/bin/env python3
"""Static validation of the observability config (audit F025).

The 22 Grafana dashboards and the Prometheus rule files shipped with no CI
check whatsoever: a malformed dashboard JSON, a panel with an empty query, a
duplicated dashboard ``uid`` (Grafana silently drops one), or an unbalanced
PromQL expression would only surface at runtime in the browser. This validator
runs deterministically — no Prometheus/Grafana server needed — and fails on:

* any rule file (``*_rules.yml``) that is not valid YAML or lacks the
  ``groups -> rules`` structure with a non-empty ``expr`` per rule;
* any dashboard that is not valid JSON, is missing ``title`` / ``uid`` /
  ``panels``, has a panel target with an empty ``expr``, or shares a ``uid``
  with another dashboard;
* any PromQL expression (rule or panel) whose brackets ``() {} []`` are
  unbalanced (the cheap structural check that survives Grafana ``$variables``).

Deep PromQL/label validation (``promtool check rules``) is layered on top in
CI for the non-templated ``recording_rules.yml``; this script is the portable,
dependency-light core that also runs in the pre-commit-adjacent pytest guard.

Usage (from anywhere — paths resolve from ``__file__``):
    python scripts/observability/validate_observability.py

Requires PyYAML (already a backend dependency).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROM_DIR = REPO_ROOT / "infrastructure" / "observability" / "prometheus"
DASHBOARD_DIR = (
    REPO_ROOT / "infrastructure" / "observability" / "grafana" / "dashboards"
)

_OPEN = {")": "(", "]": "[", "}": "{"}


def _rel(path: Path) -> str:
    """Repo-relative display path, falling back to the basename off-tree (tests)."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def _brackets_balanced(expr: str) -> bool:
    """True when (), [], {} are balanced (ignoring Grafana ``$vars`` — they add none)."""
    stack: list[str] = []
    for char in expr:
        if char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack or stack.pop() != _OPEN[char]:
                return False
    return not stack


def _iter_panel_exprs(panels: list[dict]) -> list[str]:
    """Yield every PromQL ``expr`` across panels, including nested rows."""
    exprs: list[str] = []
    for panel in panels:
        for target in panel.get("targets", []) or []:
            if "expr" in target:
                exprs.append(target["expr"])
        # Grafana "row" panels nest their children.
        if panel.get("panels"):
            exprs.extend(_iter_panel_exprs(panel["panels"]))
    return exprs


def _live_rule_files() -> list[Path]:
    """The rule files actually loaded by prometheus.yml (its ``rule_files`` list).

    Only the referenced files matter — the repo also carries standalone
    Jinja templates (``alert_rules.yml``) and disabled legacy files that
    Prometheus never reads. Glob patterns and commented entries are skipped.
    """
    config = PROM_DIR / "prometheus.yml"
    if not config.exists():
        return sorted(PROM_DIR.glob("*_rules.yml"))
    doc = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    files: list[Path] = []
    for entry in doc.get("rule_files", []) or []:
        if "*" in entry:  # a glob directory — resolve its concrete files
            files.extend(sorted(PROM_DIR.glob(entry)))
        else:
            files.append(PROM_DIR / entry)
    return files


def _validate_rules(errors: list[str]) -> int:
    checked = 0
    for rules_file in _live_rule_files():
        rel = _rel(rules_file)
        if not rules_file.exists():
            errors.append(f"{rel}: referenced by prometheus.yml rule_files but missing")
            continue
        checked += 1
        try:
            doc = yaml.safe_load(rules_file.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{rel}: invalid YAML ({exc})")
            continue
        groups = (doc or {}).get("groups")
        if not isinstance(groups, list) or not groups:
            errors.append(f"{rel}: no rule 'groups'")
            continue
        for group in groups:
            for rule in group.get("rules", []) or []:
                expr = str(rule.get("expr", "")).strip()
                name = rule.get("alert") or rule.get("record") or "<unnamed>"
                if not expr:
                    errors.append(f"{rel}: rule '{name}' has an empty expr")
                elif not _brackets_balanced(expr):
                    errors.append(f"{rel}: rule '{name}' has unbalanced brackets")
    return checked


def _validate_dashboards(errors: list[str]) -> int:
    uids: dict[str, str] = {}
    checked = 0
    for dash_file in sorted(DASHBOARD_DIR.glob("*.json")):
        checked += 1
        rel = _rel(dash_file)
        try:
            dash = json.loads(dash_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{rel}: invalid JSON ({exc})")
            continue
        for key in ("title", "uid", "panels"):
            if not dash.get(key):
                errors.append(f"{rel}: missing '{key}'")
        uid = dash.get("uid")
        if uid:
            if uid in uids:
                errors.append(f"{rel}: duplicate uid '{uid}' (also in {uids[uid]})")
            else:
                uids[uid] = rel
        for expr in _iter_panel_exprs(dash.get("panels", []) or []):
            if not expr.strip():
                errors.append(f"{rel}: panel target with empty expr")
            elif not _brackets_balanced(expr):
                errors.append(f"{rel}: unbalanced brackets in expr: {expr[:80]}")
    return checked


def main() -> int:
    """Validate rules + dashboards; return 1 on any problem."""
    if not DASHBOARD_DIR.is_dir():
        print(f"error: dashboards dir not found: {DASHBOARD_DIR}", file=sys.stderr)
        return 2
    errors: list[str] = []
    n_rules = _validate_rules(errors)
    n_dash = _validate_dashboards(errors)
    if errors:
        print(f"::error::Observability validation failed ({len(errors)} problem(s)):")
        for problem in errors:
            print(f"  - {problem}")
        return 1
    print(f"OK: {n_rules} rule file(s) and {n_dash} dashboard(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
