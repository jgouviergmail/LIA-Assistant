"""Alertmanager's template, entrypoint and compose services agree, without Docker (audit A07).

What a rendered config DOES is proven by ``task test:alertmanager``: every case of
``infrastructure/observability/alertmanager/tests/routing_matrix.yml`` rendered by
the real entrypoint in the production image, checked and routed by amtool. This
guard holds, in the unit suite, the static contract that gate relies on: every
block the template marks is one the entrypoint knows how to drop, every
placeholder is a variable both compose files pass, both compose files mount the
same files from the same image, the LIA webhook observes without swallowing,
and the boot banner prints no address and no credential (ADR-317).
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
ALERTMANAGER = REPO_ROOT / "infrastructure" / "observability" / "alertmanager"
TEMPLATE = ALERTMANAGER / "alertmanager.yml.template"
ENTRYPOINT = ALERTMANAGER / "docker-entrypoint.sh"
FRAGMENTS = (
    ALERTMANAGER / "lia-webhook-route.fragment",
    ALERTMANAGER / "lia-webhook-receiver.fragment",
)
MATRIX = ALERTMANAGER / "tests" / "routing_matrix.yml"
#: What the entrypoint reads, where compose must mount it.
READ_BY_THE_ENTRYPOINT = {
    "/docker-entrypoint.sh",
    "/etc/alertmanager/alertmanager.yml.template",
    "/etc/alertmanager/lia-webhook-route.fragment",
    "/etc/alertmanager/lia-webhook-receiver.fragment",
    "/etc/alertmanager/templates",
}
_PLACEHOLDER = re.compile(r"\$\{(ALERTMANAGER_[A-Z0-9_]+)\}")
_MARKER = re.compile(r"^\s*# @(begin|end) ([a-z-]+)$")
LOADED_ALERTS = REPO_ROOT / "infrastructure" / "observability" / "prometheus" / "alerts-core.yml"
#: The urgency routes: every loaded alert is critical or warning, they see them all.
SEVERITY_RECEIVERS = frozenset({"critical", "warning"})
#: Audience routes no loaded alert reaches, each with why it stays rendered.
DORMANT_AUDIENCES = {
    "security-team": (
        "no loaded alert carries component oauth, and the dormant catalogue's OAuth alerts "
        "carry component auth; security is outside the A07 audit, so the route stays as it "
        "was, reported to the owner on 2026-10-23"
    ),
}


def _service(compose: str) -> dict[str, Any]:
    document = yaml.safe_load((REPO_ROOT / compose).read_text(encoding="utf-8"))
    service: dict[str, Any] = document["services"]["alertmanager"]
    return service


def _bind_mounts(service: dict[str, Any]) -> set[tuple[str, str]]:
    mounts = set()
    for volume in service["volumes"]:
        source, target, *_ = volume.split(":")
        if source.startswith("./"):
            mounts.add((source, target))
    return mounts


def _env_example_keys() -> set[str]:
    lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    return {line.split("=", 1)[0] for line in lines if re.match(r"^[A-Z][A-Z0-9_]*=", line)}


def test_every_marked_block_is_balanced_and_one_the_entrypoint_drops() -> None:
    open_blocks: list[str] = []
    marked: set[str] = set()
    for number, line in enumerate(TEMPLATE.read_text(encoding="utf-8").splitlines(), start=1):
        marker = _MARKER.match(line)
        if marker is None:
            continue
        kind, name = marker.groups()
        if kind == "begin":
            open_blocks.append(name)
            marked.add(name)
        else:
            assert (
                open_blocks and open_blocks.pop() == name
            ), f"line {number}: unbalanced @end {name}"
    assert open_blocks == [], f"blocks never closed: {open_blocks}"

    dropped = set(re.findall(r"\bdrop_block ([a-z-]+) ", ENTRYPOINT.read_text(encoding="utf-8")))
    assert marked == dropped, f"marked only: {marked - dropped}; dropped only: {dropped - marked}"


def test_every_placeholder_is_a_variable_both_compose_files_pass() -> None:
    placeholders = {
        name
        for path in (TEMPLATE, *FRAGMENTS)
        for name in _PLACEHOLDER.findall(path.read_text(encoding="utf-8"))
    }
    production = set(_service("docker-compose.prod.yml")["environment"])
    # The dev service reads the whole .env (env_file) plus its own environment block.
    development = set(_service("docker-compose.dev.yml")["environment"]) | _env_example_keys()

    assert placeholders, "the template no longer names any variable"
    assert placeholders <= production, f"production never passes {placeholders - production}"
    assert placeholders <= development, f"development never passes {placeholders - development}"


def test_both_compose_files_mount_the_same_files_from_the_same_image() -> None:
    development, production = _service("docker-compose.dev.yml"), _service(
        "docker-compose.prod.yml"
    )

    assert development["image"] == production["image"]
    assert _bind_mounts(development) == _bind_mounts(production)
    assert {target for _, target in _bind_mounts(production)} == READ_BY_THE_ENTRYPOINT
    for source, _ in _bind_mounts(production):
        assert (REPO_ROOT / source).exists(), f"compose mounts {source}, which does not exist"


def _loaded_alert_labels() -> list[dict[str, str]]:
    document = yaml.safe_load(LOADED_ALERTS.read_text(encoding="utf-8"))
    return [
        {"alertname": rule["alert"], **rule.get("labels", {})}
        for group in document["groups"]
        for rule in group["rules"]
        if "alert" in rule
    ]


def _route_matches(route: dict[str, Any], labels: dict[str, str]) -> bool:
    """Alertmanager's ``match`` (equality) and ``match_re`` (anchored), a missing label empty."""
    equal = all(labels.get(name) == value for name, value in (route.get("match") or {}).items())
    anchored = all(
        re.fullmatch(pattern, labels.get(name, "")) is not None
        for name, pattern in (route.get("match_re") or {}).items()
    )
    return equal and anchored


def test_every_audience_route_is_reached_by_a_loaded_alert_or_declared_dormant() -> None:
    """An audience no alert can reach is a promise nothing keeps: wire it or remove it."""
    routes = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))["route"]["routes"]
    audiences = [route for route in routes if route["receiver"] not in SEVERITY_RECEIVERS]
    alerts = _loaded_alert_labels()
    unreached = {
        route["receiver"]
        for route in audiences
        if not any(_route_matches(route, labels) for labels in alerts)
    }

    assert audiences and alerts
    assert unreached == set(DORMANT_AUDIENCES), (
        f"reached by no loaded alert, undeclared: {sorted(unreached - set(DORMANT_AUDIENCES))}; "
        f"declared dormant but reached: {sorted(set(DORMANT_AUDIENCES) - unreached)}"
    )


def test_every_matrix_case_uses_only_variables_production_passes() -> None:
    production = set(_service("docker-compose.prod.yml")["environment"])
    cases = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))["cases"]

    assert cases
    for case in cases:
        assert set(case["env"]) <= production, f"{case['name']}: {set(case['env']) - production}"


def test_the_webhook_route_observes_and_never_swallows() -> None:
    (route,) = yaml.safe_load(FRAGMENTS[0].read_text(encoding="utf-8"))

    assert route["receiver"] == "lia-api-webhook"
    assert route["match_re"] == {"severity": "critical|warning"}
    # continue: true is what lets the backend and team routes still fire.
    assert route["continue"] is True


def test_the_webhook_receiver_carries_bearer_auth_and_resolved() -> None:
    (receiver,) = yaml.safe_load(FRAGMENTS[1].read_text(encoding="utf-8"))
    (webhook,) = receiver["webhook_configs"]

    assert receiver["name"] == "lia-api-webhook"
    assert webhook["send_resolved"] is True
    assert webhook["url"] == "${ALERTMANAGER_LIA_WEBHOOK_URL}"
    assert webhook["http_config"]["authorization"] == {
        "type": "Bearer",
        "credentials": "${ALERTMANAGER_LIA_WEBHOOK_SECRET}",
    }


#: What the entrypoint may name but never print (ADR-317): an address, a
#: credential, a webhook, a routing key. Its log lines reach Loki like any other.
_UNPRINTABLE_VARIABLE = re.compile(
    r"_(?:EMAIL|FROM|USERNAME|PASSWORD|SECRET|ROUTING_KEY)$|_SLACK_WEBHOOK_"
)


def test_the_entrypoint_prints_no_address_and_no_credential() -> None:
    # Measured 2026-10-03: the boot banner printed the alert sender and the
    # recipient team's address on every start, and Alloy shipped both to Loki.
    printed = [
        (number, name)
        for number, line in enumerate(ENTRYPOINT.read_text(encoding="utf-8").splitlines(), start=1)
        if re.search(r"(?:^|&&|\|\|)\s*echo\b", line)
        for name in re.findall(r"\$\{?([A-Z][A-Z0-9_]*)", line)
        if _UNPRINTABLE_VARIABLE.search(name)
    ]

    assert printed == []
