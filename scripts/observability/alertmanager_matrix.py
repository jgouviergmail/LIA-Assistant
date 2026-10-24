#!/usr/bin/env python3
"""Alertmanager rendering and routing matrix, in the production image (audit A07).

Each case of ``infrastructure/observability/alertmanager/tests/routing_matrix.yml``
renders the config through the real ``docker-entrypoint.sh --render-only`` — in
the image production pins, with no network, the files mounted exactly as
``docker-compose.prod.yml`` mounts them — then ``amtool check-config`` validates
it, ``amtool template render`` renders every email template it names, and
``amtool config routes test`` routes each alert of the case. The rendered file
is read back to check which notification kinds each receiver holds and that a
value typed with ``&``, ``|``, ``\\`` or ``'`` arrived intact.

A shell rendering checked by a Python re-implementation proves the
re-implementation: the busybox ``sed``/``awk`` the entrypoint runs on is the
thing under test, so it is the thing that runs.

Usage (from anywhere — paths resolve from ``__file__``; needs Docker):
    python scripts/observability/alertmanager_matrix.py
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.prod.yml"
ALERTS = ROOT / "infrastructure" / "observability" / "prometheus" / "alerts-core.yml"
MATRIX = ROOT / "infrastructure" / "observability" / "alertmanager" / "tests" / "routing_matrix.yml"
RENDERED = "/out/alertmanager.yml"
#: `check-config` parses the email templates without executing them, and a template
#: that fails at render time fails the notification: each one the rendered config
#: names is rendered here with amtool's example data.
RENDER_TEMPLATES = (
    "for name in $(grep -o 'template \"[a-z.]*\"' "
    + RENDERED
    + " | cut -d '\"' -f 2 | sort -u); do"
    " amtool template render --template.glob='/etc/alertmanager/templates/*.tmpl'"
    ' --template.text="{{ template \\"$name\\" . }}" > /dev/null 2>&1'
    ' && echo "TEMPLATE $name ok" || echo "TEMPLATE $name failed"; done'
)
#: Notification kinds a receiver may hold, by their Alertmanager key.
KINDS = {
    "email_configs": "email",
    "slack_configs": "slack",
    "pagerduty_configs": "pagerduty",
    "webhook_configs": "webhook",
}


def _service() -> dict[str, Any]:
    service: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"][
        "alertmanager"
    ]
    return service


def _mounts(service: dict[str, Any]) -> list[str]:
    """The service's bind mounts as ``docker run --mount`` arguments (named volumes left out)."""
    mounts = []
    for volume in service["volumes"]:
        source, target, *mode = volume.split(":")
        if not source.startswith("./"):
            continue
        host = (ROOT / source).resolve()
        if not host.exists():
            raise SystemExit(f"compose mounts {source}, which does not exist")
        mounts += ["--mount", f"type=bind,source={host},target={target},readonly"]
    return mounts


def _labels(alerts: dict[str, dict[str, str]], name: str) -> dict[str, str]:
    if name in alerts:
        return alerts[name]
    raise SystemExit(f"the matrix routes {name}, which is neither loaded nor synthetic")


def _loaded_alerts() -> dict[str, dict[str, str]]:
    groups = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))["groups"]
    return {
        rule["alert"]: dict(rule.get("labels", {}))
        for group in groups
        for rule in group.get("rules", [])
        if "alert" in rule
    }


def _script(case: dict[str, Any], alerts: dict[str, dict[str, str]]) -> str:
    lines = [
        f"sh /docker-entrypoint.sh --render-only {RENDERED} > /out/render.log 2>&1"
        ' || { echo "RENDER_EXIT $?"; exit 0; }',
        f"amtool check-config {RENDERED} > /out/check.log 2>&1"
        ' || { echo "CHECK_FAILED"; exit 0; }',
        'echo "CHECK_OK"',
        RENDER_TEMPLATES,
    ]
    for name in case.get("alerts", {}):
        labels = {**_labels(alerts, name), "alertname": name}
        arguments = " ".join(shlex.quote(f"{key}={value}") for key, value in labels.items())
        lines.append(
            f"printf 'ROUTE %s ' {shlex.quote(name)};"
            f" amtool config routes test --config.file={RENDERED} {arguments}"
        )
    return "\n".join(lines)


def _receivers(rendered: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {receiver["name"]: receiver for receiver in rendered.get("receivers", [])}


def _value(rendered: dict[str, Any], dotted: str) -> Any:
    """``global.x`` or ``receiver.<name>.<key>...`` — list indexes are numbers."""
    head, *path = dotted.split(".")
    node: Any = _receivers(rendered)[path.pop(0)] if head == "receiver" else rendered[head]
    for key in path:
        node = node[int(key)] if isinstance(node, list) else node[key]
    return node


def _check(case: dict[str, Any], output: str, out_dir: Path) -> list[str]:
    problems: list[str] = []
    if case.get("refused"):
        if "RENDER_EXIT" not in output or (out_dir / "alertmanager.yml").exists():
            problems.append("the render was not refused")
        return problems
    if "RENDER_EXIT" in output:
        log = (out_dir / "render.log").read_text(encoding="utf-8", errors="replace")
        return [f"the render failed: {output.strip()}\n{log}"]
    if "CHECK_OK" not in output:
        log = (out_dir / "check.log").read_text(encoding="utf-8", errors="replace")
        return [f"amtool check-config refused the config:\n{log}"]
    routed = {
        line.split(" ", 2)[1]: line.split(" ", 2)[2].strip().split(",")
        for line in output.splitlines()
        if line.startswith("ROUTE ")
    }
    for name, expected in case.get("alerts", {}).items():
        if routed.get(name) != expected:
            problems.append(f"{name} reached {routed.get(name)}, expected {expected}")
    problems += [
        f"email template {line.split()[1]} does not render"
        for line in output.splitlines()
        if line.startswith("TEMPLATE ") and line.endswith(" failed")
    ]
    rendered = yaml.safe_load((out_dir / "alertmanager.yml").read_text(encoding="utf-8"))
    named = set(
        re.findall(
            r'template "([a-z.]+)"', (out_dir / "alertmanager.yml").read_text(encoding="utf-8")
        )
    )
    checked = {line.split()[1] for line in output.splitlines() if line.startswith("TEMPLATE ")}
    if named != checked:
        problems.append(f"email templates named but never rendered: {sorted(named - checked)}")
    receivers = _receivers(rendered)
    for name, kinds in case.get("configs", {}).items():
        held = sorted(KINDS[key] for key in receivers.get(name, {}) if key in KINDS)
        if held != sorted(kinds):
            problems.append(f"receiver {name} holds {held}, expected {sorted(kinds)}")
    for name in case.get("absent", []):
        if name in receivers:
            problems.append(f"receiver {name} is rendered, expected absent")
    for dotted, expected in case.get("values", {}).items():
        actual = _value(rendered, dotted)
        if actual != expected:
            problems.append(f"{dotted} renders as {actual!r}, expected {expected!r}")
    return problems


def run_case(
    case: dict[str, Any], image: str, mounts: list[str], alerts: dict[str, dict[str, str]]
) -> list[str]:
    """Render, validate and route one case; the problems it found, empty when it holds."""
    with tempfile.TemporaryDirectory(prefix="alertmanager-matrix-") as out:
        out_dir = Path(out)
        out_dir.chmod(0o777)  # the image runs as nobody
        environment = [
            arg for key, value in case["env"].items() for arg in ("-e", f"{key}={value}")
        ]
        command = [
            "docker", "run", "--rm", "--network", "none", *mounts,
            "--mount", f"type=bind,source={out_dir},target=/out",
            *environment, "--entrypoint", "/bin/sh", image, "-c", _script(case, alerts),
        ]  # fmt: skip
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            return [f"docker exited {completed.returncode}: {completed.stderr.strip()}"]
        return _check(case, completed.stdout, out_dir)


def main() -> int:
    """Run every case; non-zero when any of them does not hold."""
    service = _service()
    image, mounts = service["image"], _mounts(service)
    declared = set(service["environment"])
    matrix = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    alerts = {**_loaded_alerts(), **matrix["synthetic_alerts"]}
    failed = 0
    for case in matrix["cases"]:
        undeclared = sorted(set(case["env"]) - declared)
        problems = (
            [f"compose never passes {undeclared}"]
            if undeclared
            else run_case(case, image, mounts, alerts)
        )
        print(f"{'FAIL' if problems else 'ok  '} {case['name']}")
        for problem in problems:
            print(f"     {problem}")
        failed += bool(problems)
    print(f"{len(matrix['cases']) - failed}/{len(matrix['cases'])} cases hold")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
