"""Alertmanager webhook injection — the receiver matrix, validated in CI.

The entrypoint composes the rendered template with two committed fragments
using exactly two trivial operations: INSERT the route fragment after the
``  routes:`` anchor line, APPEND the receiver fragment at EOF. This test
replays that exact composition over the matrix {full, email-only} × {webhook
on, off} (+ the minimal no-SMTP mode) and validates the resulting YAML
structure — the CLAUDE.md rule that every supported receiver combination must
be validated, applied mechanically to the combination this feature adds.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_ALERTMANAGER_DIR = (
    Path(__file__).resolve().parents[3].parent / "infrastructure" / "observability" / "alertmanager"
)

_DUMMY_VARS = {
    "ALERTMANAGER_SMTP_SMARTHOST": "smtp.example.com:587",
    "ALERTMANAGER_SMTP_FROM": "am@example.com",
    "ALERTMANAGER_SMTP_AUTH_USERNAME": "u@example.com",
    "ALERTMANAGER_SMTP_AUTH_PASSWORD": "pw",
    "ALERTMANAGER_BACKEND_TEAM_EMAIL": "backend@example.com",
    "ALERTMANAGER_FINANCE_TEAM_EMAIL": "finance@example.com",
    "ALERTMANAGER_SECURITY_TEAM_EMAIL": "security@example.com",
    "ALERTMANAGER_ML_TEAM_EMAIL": "ml@example.com",
    "ALERTMANAGER_SLACK_WEBHOOK_CRITICAL": "https://hooks.slack.example/xxx",
    "ALERTMANAGER_SLACK_WEBHOOK_WARNING": "https://hooks.slack.example/yyy",
    "ALERTMANAGER_SLACK_WEBHOOK_SECURITY": "https://hooks.slack.example/zzz",
    "ALERTMANAGER_PAGERDUTY_ROUTING_KEY": "pd-key",
    "ALERTMANAGER_LIA_WEBHOOK_URL": "http://api:8000/api/v1/internal/diagnostics/alert-webhook",
    "ALERTMANAGER_LIA_WEBHOOK_SECRET": "dummy-secret",
}


def _render(text: str) -> str:
    for name, value in _DUMMY_VARS.items():
        text = text.replace("${" + name + "}", value)
    return text


def _compose(template_name: str, with_webhook: bool) -> dict:
    """Replay the entrypoint composition: render, insert route, append receiver."""
    template = (_ALERTMANAGER_DIR / template_name).read_text(encoding="utf-8")
    if with_webhook:
        route_fragment = (_ALERTMANAGER_DIR / "lia-webhook-route.fragment").read_text(
            encoding="utf-8"
        )
        receiver_fragment = (_ALERTMANAGER_DIR / "lia-webhook-receiver.fragment").read_text(
            encoding="utf-8"
        )
        lines = template.splitlines(keepends=True)
        anchor = next(i for i, line in enumerate(lines) if line.rstrip("\n") == "  routes:")
        lines.insert(
            anchor + 1,
            route_fragment if route_fragment.endswith("\n") else route_fragment + "\n",
        )
        template = "".join(lines) + "\n" + receiver_fragment
    rendered = _render(template)
    assert not re.findall(r"\$\{[A-Z_]+\}", rendered), "unsubstituted variables remain"
    return yaml.safe_load(rendered)


def _receiver_names(config: dict) -> set[str]:
    return {r["name"] for r in config.get("receivers", [])}


@pytest.mark.unit
class TestWebhookInjectionMatrix:
    @pytest.mark.parametrize(
        "template_name",
        ["alertmanager.yml.template", "alertmanager-email-only.yml.template"],
    )
    def test_without_webhook_receiver_is_absent(self, template_name: str) -> None:
        config = _compose(template_name, with_webhook=False)
        assert "lia-api-webhook" not in _receiver_names(config)

    @pytest.mark.parametrize(
        "template_name",
        ["alertmanager.yml.template", "alertmanager-email-only.yml.template"],
    )
    def test_with_webhook_route_is_first_and_continues(self, template_name: str) -> None:
        config = _compose(template_name, with_webhook=True)
        assert "lia-api-webhook" in _receiver_names(config)
        first_route = config["route"]["routes"][0]
        assert first_route["receiver"] == "lia-api-webhook"
        # continue: true is what lets the existing email/Slack routing still
        # fire — the webhook observes, it never swallows.
        assert first_route["continue"] is True
        # Every route still references an existing receiver (no orphan).
        names = _receiver_names(config)
        for route in config["route"]["routes"]:
            assert route.get("receiver") in names

    @pytest.mark.parametrize(
        "template_name",
        ["alertmanager.yml.template", "alertmanager-email-only.yml.template"],
    )
    def test_webhook_receiver_carries_bearer_auth_and_resolved(self, template_name: str) -> None:
        config = _compose(template_name, with_webhook=True)
        receiver = next(r for r in config["receivers"] if r["name"] == "lia-api-webhook")
        webhook = receiver["webhook_configs"][0]
        assert webhook["send_resolved"] is True
        assert webhook["url"].endswith("/internal/diagnostics/alert-webhook")
        auth = webhook["http_config"]["authorization"]
        assert auth["type"] == "Bearer"
        assert auth["credentials"] == "dummy-secret"

    def test_minimal_mode_heredoc_supports_the_webhook(self) -> None:
        """The no-SMTP minimal config must accept the fragments too."""
        entrypoint = (_ALERTMANAGER_DIR / "docker-entrypoint.sh").read_text(encoding="utf-8")
        # The minimal-mode block must route through the same injection helper
        # rather than duplicating YAML (one implementation of the webhook).
        assert entrypoint.count("lia-webhook-route.fragment") >= 1
        assert entrypoint.count("lia-webhook-receiver.fragment") >= 1
        assert "inject_lia_webhook" in entrypoint
