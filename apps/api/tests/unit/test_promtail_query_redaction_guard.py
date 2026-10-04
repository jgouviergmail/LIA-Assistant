"""Guard: Loki never receives a URL's credentials, nor its search text above DEBUG.

The API's PII filter masks a query parameter's VALUE in its own lines
(``sanitize_url_query``): credentials and coordinates at every level, the
person's search text above DEBUG. Every other container writes raw text, and
Promtail ships it as written: while the API restarted, Next.js logged « Failed
to proxy <url> » with the proxied request's whole query string — the Pub/Sub
webhook's ``?token=`` on 322 production lines in a week, deleted from Loki on
2026-09-25 (ADR-317). Promtail now applies the same two rules to every line.

Two lists written in two languages drift, so this guard holds the parameter
names of the Promtail expressions EQUAL to the filter's tuples, and runs the
expressions — Python's ``re`` reads the RE2 subset they use — against the
filter itself over the shapes they exist for: the two must agree line for line.
One divergence is deliberate and pinned: Promtail reads the API's lines
JSON-ESCAPED, so its value also stops at a backslash — eating the ``\\`` of an
escaped quote would break the line's JSON.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
import yaml

from src.infrastructure.observability.pii_filter import (
    _CONTENT_QUERY_PARAMS,
    _SENSITIVE_QUERY_PARAMS,
    sanitize_url_query,
)
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
PROMTAIL_CONFIG = (
    REPO_ROOT / "infrastructure" / "observability" / "promtail" / "promtail-config.yml"
)

#: The selector under which the content stage runs: every line but a DEBUG one. The
#: ``project`` label is on every shipped line (a target label, and the discovery
#: keeps that compose project alone); a line with no level (any container but the
#: API) is therefore above DEBUG.
CONTENT_SELECTOR = '{project="lia", level!="debug"}'

REDACTED = "[REDACTED]"

_ALTERNATION = re.compile(r"\(\?:([^)]*)\)=")


def _docker_scrape() -> dict[str, Any]:
    config = yaml.safe_load(PROMTAIL_CONFIG.read_text(encoding="utf-8"))
    for scrape in config.get("scrape_configs") or []:
        if scrape.get("job_name") == "docker":
            return dict(scrape)
    return {}


def _docker_stages() -> list[dict[str, Any]]:
    return list(_docker_scrape().get("pipeline_stages") or [])


def _credential_stage() -> dict[str, Any]:
    stages: list[dict[str, Any]] = [
        stage["replace"] for stage in _docker_stages() if "replace" in stage
    ]
    assert len(stages) == 1, f"expected ONE top-level replace stage, found {len(stages)}"
    return stages[0]


def _content_match() -> dict[str, Any]:
    matches: list[dict[str, Any]] = [
        stage["match"] for stage in _docker_stages() if "match" in stage
    ]
    assert len(matches) == 1, f"expected ONE match stage, found {len(matches)}"
    return matches[0]


def _content_stage() -> dict[str, Any]:
    stages: list[dict[str, Any]] = [
        stage["replace"] for stage in _content_match()["stages"] if "replace" in stage
    ]
    assert len(stages) == 1, f"expected ONE replace stage under the match, found {len(stages)}"
    return stages[0]


def _names(expression: str) -> set[str]:
    found = _ALTERNATION.search(expression)
    assert found, f"no `(?:a|b)=` alternation in {expression!r}"
    return {name.replace("\\$", "$").lower() for name in found.group(1).split("|")}


def _promtail_replace(stage: dict[str, Any], line: str) -> str:
    """Promtail's ``replace``: every capture group of every match becomes ``replace``."""
    pattern = re.compile(stage["expression"])
    parts: list[str] = []
    cursor = 0
    for match in pattern.finditer(line):
        for group in range(1, pattern.groups + 1):
            start, end = match.span(group)
            if start < 0:
                continue
            parts.extend((line[cursor:start], stage["replace"]))
            cursor = end
    parts.append(line[cursor:])
    return "".join(parts)


def test_the_config_is_readable() -> None:
    """A guard that parses nothing asserts nothing."""
    assert PROMTAIL_CONFIG.is_file(), f"{PROMTAIL_CONFIG} not found"
    assert _credential_stage()["expression"]
    assert _content_stage()["expression"]


def test_credential_names_are_the_filter_s() -> None:
    assert _names(_credential_stage()["expression"]) == set(_SENSITIVE_QUERY_PARAMS)


def test_content_names_are_the_filter_s() -> None:
    assert _names(_content_stage()["expression"]) == set(_CONTENT_QUERY_PARAMS)


@pytest.mark.parametrize("stage", ["credentials", "content"])
def test_only_the_value_is_captured(stage: str) -> None:
    """Promtail replaces EVERY capture group: a captured name would vanish with its value."""
    declared = _credential_stage() if stage == "credentials" else _content_stage()
    assert re.compile(declared["expression"]).groups == 1
    assert declared["replace"] == REDACTED


def test_the_content_stage_spares_debug_lines_only() -> None:
    """The selector reads labels set BEFORE the match runs, and every line carries them.

    ``project`` is a target label (relabelled before any stage runs) and the
    discovery keeps that compose project alone, so the selector covers every
    shipped line; ``level`` is promoted by an earlier stage. It used to read a
    static ``job`` label set on every line, which made ``{job="api"}`` select
    every container on the dashboards too.
    """
    scrape = _docker_scrape()
    stages = _docker_stages()
    position = next(i for i, stage in enumerate(stages) if "match" in stage)
    assert _content_match()["selector"] == CONTENT_SELECTOR
    assert any(stage.get("labels", {}).get("level") == "level" for stage in stages[:position])
    project = "__meta_docker_container_label_com_docker_compose_project"
    assert any(
        rule.get("target_label") == "project" and rule.get("source_labels") == [project]
        for rule in scrape.get("relabel_configs") or []
    )
    filters = [f for sd in scrape.get("docker_sd_configs") or [] for f in sd.get("filters") or []]
    assert {"name": "label", "values": ["com.docker.compose.project=lia"]} in filters


_CORPUS = [
    "Failed to proxy http://api:8000/api/v1/webhooks/google/pubsub?token=s3cr3tV4lue "
    "Error: connect ECONNREFUSED 192.0.2.10:8000",
    "Failed to proxy http://api:8000/api/v1/auth/google/callback?code=4/0AbCd"
    "&state=Zx9yW8vU7tS6rQ5p&scope=email Error: socket hang up",
    "GET /x?TOKEN=a1&Key=AIza9&lat=48.85&lng=2.35&page=3 200",
    "Failed to proxy http://api:8000/api/v1/rag-spaces/documents?q=Jean%20Dupont&limit=20",
    "GET https://graph.example/v1.0/me/messages?$search=%22invoice%22&$top=10",
    '{"event": "e", "url": "https://maps.example/s?address=1%20rue%20X&key=AIza9#frag"}',
    "status code=200 ok, token=free-text-not-a-query-parameter",
    "GET /_next/image?url=%2Fa.png&w=640&q=75 400",
]


@pytest.mark.parametrize("line", _CORPUS)
def test_promtail_agrees_with_the_filter(line: str) -> None:
    """Credentials alone on a DEBUG line; credentials, then content, above it."""
    debug = _promtail_replace(_credential_stage(), line)
    above = _promtail_replace(_content_stage(), debug)
    assert debug == sanitize_url_query(line)
    assert above == sanitize_url_query(line, redact_content=True)


@pytest.mark.parametrize(
    "payload",
    [
        # The API's line: its filter ran first, the value is already `[REDACTED]`.
        {
            "event": "vendor_error",
            "vendor_payload": sanitize_url_query(
                '{"url": "https://maps.example/s?key=AIza9&q=Jean"}', redact_content=True
            ),
        },
        # Another container's JSON line: nothing masked it before Promtail.
        {"msg": 'GET "https://x.example/cb?page=2&token=s3cr3t" failed'},
    ],
)
def test_a_json_line_stays_json(payload: dict[str, str]) -> None:
    """Promtail reads a JSON line ESCAPED, where the filter read the value raw.

    A value followed by an escaped quote must lose the value, never the backslash
    of the escape: the line would stop being JSON, and lose its timestamp, its
    level and every ``| json`` query.
    """
    line = json.dumps(payload)
    shipped = _promtail_replace(_content_stage(), _promtail_replace(_credential_stage(), line))
    assert json.loads(shipped) == {
        key: sanitize_url_query(value, redact_content=True) for key, value in payload.items()
    }


def test_the_corpus_exercises_both_stages() -> None:
    """An agreement over lines neither stage touches would prove nothing."""
    credentials = sum(_promtail_replace(_credential_stage(), line) != line for line in _CORPUS)
    content = sum(_promtail_replace(_content_stage(), line) != line for line in _CORPUS)
    untouched = [line for line in _CORPUS if sanitize_url_query(line, redact_content=True) == line]
    assert credentials >= 4
    assert content >= 3
    assert untouched == ["status code=200 ok, token=free-text-not-a-query-parameter"]
