#!/usr/bin/env python3
"""Alertmanager rendering and routing matrix, in the production image (audit A07).

Each case of ``infrastructure/observability/alertmanager/tests/routing_matrix.yml``
renders the config through the real ``docker-entrypoint.sh --render-only`` — in
the image production pins, with no network, the files mounted exactly as
``docker-compose.prod.yml`` mounts them — then ``amtool check-config`` validates
it, ``amtool template render`` renders every email template it names and every
notification's source identity for firing/resolved dev, prod and incomplete labels, and
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

import json
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
    "for name in $(grep -o 'template \"email.[a-z.]*\"' "
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


def _notification_fields(rendered: dict[str, Any]) -> list[tuple[str, str, set[str]]]:
    """Every configured notification field that must identify its source."""
    fields = []
    for receiver in rendered.get("receivers", []):
        for kind, names in (
            ("email_configs", ("subject", "html")),
            ("slack_configs", ("title", "text")),
            ("pagerduty_configs", ("description", "environment", "host")),
        ):
            for index, config in enumerate(receiver.get(kind, [])):
                for name in names:
                    if name == "subject":
                        value = config.get("headers", {}).get("Subject", "")
                    elif name in {"environment", "host"}:
                        value = config.get("details", {}).get(name, "")
                    else:
                        value = config.get(name, "")
                    expected = (
                        {name} if name in {"environment", "host"} else {"environment", "host"}
                    )
                    fields.append((f"{receiver['name']}.{kind}.{index}.{name}", value, expected))
    return fields


def _check_notification_identity(
    case: dict[str, Any], rendered: dict[str, Any], out_dir: Path, command: list[str]
) -> list[str]:
    """Execute real notification templates with dev, prod and incomplete source labels.

    No notifier runs: amtool only renders strings, in an isolated network namespace.
    Subject/title, body and PagerDuty detail fields are read from the rendered config,
    so dropping their identity makes this gate fail even if the helper still exists.
    """
    identities = case.get("notification_identities", [])
    if not identities:
        return []
    fields = _notification_fields(rendered)
    checks = []
    lines = []
    for identity_index, identity in enumerate(identities):
        for status in ("firing", "resolved"):
            labels = {
                "alertname": "ServiceDown",
                "severity": "critical",
                "component": "api",
                **identity["labels"],
            }
            data = {
                "receiver": "critical",
                "status": status,
                "groupLabels": labels,
                "commonLabels": labels,
                "commonAnnotations": {"summary": "Service unavailable"},
                "externalURL": "http://alertmanager.example.invalid",
                "alerts": [
                    {
                        "status": status,
                        "labels": labels,
                        "annotations": {
                            "summary": "Service unavailable",
                            "description": "Check API",
                        },
                        "startsAt": "2026-10-26T10:00:00Z",
                        "endsAt": (
                            "2026-10-26T10:05:00Z"
                            if status == "resolved"
                            else "0001-01-01T00:00:00Z"
                        ),
                        "generatorURL": "http://prometheus.example.invalid",
                        "fingerprint": "notification-identity-proof",
                    }
                ],
            }
            data_name = f"identity-{identity_index}-{status}.json"
            (out_dir / data_name).write_text(json.dumps(data), encoding="utf-8")
            for field_index, (name, template, keys) in enumerate(fields):
                filename = f"identity-{identity_index}-{status}-{field_index}.txt"
                checks.append(
                    (
                        identity["name"],
                        status,
                        name,
                        filename,
                        identity["expected"],
                        keys,
                    )
                )
                lines.append(
                    "amtool template render --template.glob='/etc/alertmanager/templates/*.tmpl' "
                    f"--template.data=/out/{data_name} --template.text={shlex.quote(template)} "
                    f"> /out/{filename} 2> /out/{filename}.err; echo $? > /out/{filename}.rc"
                )
    # Keep the batch in a mounted file: a full notifier matrix exceeds the
    # Windows CreateProcess command-line limit even though the shell accepts it.
    (out_dir / "notification-identity.sh").write_text("\n".join(lines), encoding="utf-8")
    completed = subprocess.run(
        [*command, "/out/notification-identity.sh"], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        return [f"notification rendering exited {completed.returncode}: {completed.stderr.strip()}"]
    problems = []
    for identity, status, name, filename, expected, keys in checks:
        # The exit status decides; a warning on stderr from a render that
        # succeeded is not a failure.
        returned = (out_dir / f"{filename}.rc").read_text(encoding="utf-8").strip()
        error = (out_dir / f"{filename}.err").read_text(encoding="utf-8", errors="replace")
        output = (out_dir / filename).read_text(encoding="utf-8", errors="replace")
        if returned != "0":
            problems.append(
                f"{identity}/{status}/{name} failed to render ({returned}): {error.strip()}"
            )
        elif any(expected[key] not in output for key in keys):
            problems.append(f"{identity}/{status}/{name} omits source identity {expected}")
    return problems


def _check_source_isolation(rendered: dict[str, Any]) -> list[str]:
    """Effective route grouping and inhibition must stay inside one deployment."""
    problems = []

    def check_route(route: dict[str, Any], inherited: set[str]) -> None:
        grouping = set(route.get("group_by", inherited))
        if not {"environment", "host"} <= grouping:
            problems.append(
                f"route {route['receiver']} groups different source environments or hosts"
            )
        for child in route.get("routes", []):
            check_route(child, grouping)

    check_route(rendered["route"], set())
    for rule in rendered.get("inhibit_rules", []):
        if not {"environment", "host"} <= set(rule.get("equal", [])):
            problems.append(f"inhibition can silence another environment or host: {rule}")
    return problems


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
    problems += _check_source_isolation(rendered)
    named = set(
        re.findall(
            r'template "(email\.[a-z.]+)"',
            (out_dir / "alertmanager.yml").read_text(encoding="utf-8"),
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
    case: dict[str, Any],
    image: str,
    mounts: list[str],
    alerts: dict[str, dict[str, str]],
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
            *environment, "--entrypoint", "/bin/sh", image,
        ]  # fmt: skip
        completed = subprocess.run(
            [*command, "-c", _script(case, alerts)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return [f"docker exited {completed.returncode}: {completed.stderr.strip()}"]
        problems = _check(case, completed.stdout, out_dir)
        if (out_dir / "alertmanager.yml").exists() and "CHECK_OK" in completed.stdout:
            rendered = yaml.safe_load((out_dir / "alertmanager.yml").read_text(encoding="utf-8"))
            problems += _check_notification_identity(case, rendered, out_dir, command)
        return problems


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
