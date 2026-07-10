"""Reproducible TTFT / per-stage latency measurement protocol (latency lot, 2026-07).

Runs a fixed set of 10 representative chat requests against a running LIA
environment (dev Docker by default) and reports p50/p95 per scenario:

- client-side: TTFT (first `token` / `hitl_question_token` SSE event) and
  total stream duration — the user-perceived truth;
- server-side: per-stage wall-clock seconds, read as before/after deltas of
  `langgraph_stage_duration_seconds` (and `agent_node_duration_seconds` for
  node-body times) on the /metrics endpoint. Reliable on the single-worker
  dev API; on multi-worker deployments prefer the `graph_stage_durations`
  structlog event in Loki.

Scenario coverage (5 required turn types, both execution modes):
conversational, single-domain action, multi-domain action, ReAct, HITL
draft + resume. Scenarios use OAuth-free domains only (wikipedia, weather,
reminders) so a dedicated perf user without connectors works.

Each iteration uses a different natural variant of the query to bust the
exact-match LLM caches (semantic pivot Redis cache, TTL 300s) — identical
repeats would overstate cache benefits vs real usage. Pass --no-cache-bust
to measure the warm-cache path instead.

Usage (from repo root, host venv):
    apps/api/.venv/Scripts/python scripts/perf/measure_ttft.py \
        --email perf@example.com --password "..." [--register] \
        [--base-url https://localhost:8000] [--iterations 3] \
        [--modes pipeline,react] [--output scripts/perf/results/run.json]

WARNING: the script PATCHes the perf user's execution_mode preference while
running the ReAct scenarios and restores "pipeline" at the end — use a
dedicated perf account, not your personal one.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

API_PREFIX = "/api/v1"
SSE_DATA_PREFIX = "data: "
# Terminal SSE chunk types: the turn is over once one of these is received.
TERMINAL_CHUNK_TYPES = {"done", "error", "hitl_interrupt_complete"}
# Chunk types that count as "first token" for TTFT purposes.
FIRST_TOKEN_CHUNK_TYPES = {"token", "hitl_question_token"}

# Prometheus text-format line for a labelled sample, e.g.
# langgraph_stage_duration_seconds_sum{execution_mode="pipeline",stage="router",turn_kind="action"} 12.3
_PROM_LINE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)\{(?P<labels>[^}]*)\}\s+(?P<value>[^\s]+)$"
)
_PROM_LABEL_RE = re.compile(
    r'(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<value>(?:[^"\\]|\\.)*)"'
)

# Metrics whose per-request deltas we track (sum + count).
TRACKED_METRICS = (
    "langgraph_stage_duration_seconds",
    "agent_node_duration_seconds",
    "llm_api_latency_seconds",
    "sse_time_to_first_token_seconds",
)


@dataclass
class Scenario:
    """One measured request type.

    Attributes:
        key: Stable identifier used in reports.
        mode: Execution mode required for this scenario (pipeline | react).
        kind: Reporting family (conversation / action_single / action_multi /
            hitl_trigger / hitl_resume).
        variants: Natural query variants; iteration i uses variants[i % len].
        reset_before: Reset the conversation before sending (isolation). The
            HITL resume scenario must NOT reset (it continues the pending turn).
    """

    key: str
    mode: str
    kind: str
    variants: list[str]
    reset_before: bool = True
    # Optional unmeasured setup message sent (and fully consumed) before the
    # measured request — e.g. create the reminder that the measured HITL
    # cancellation will target. Variants indexed like `variants`.
    seed_variants: list[str] | None = None


SCENARIOS: list[Scenario] = [
    Scenario(
        key="conv_greeting",
        mode="pipeline",
        kind="conversation",
        variants=[
            "Bonjour !",
            "Salut, comment vas-tu ?",
            "Coucou, tu es là ?",
            "Hello, bien ou bien ?",
            "Bonsoir !",
        ],
    ),
    Scenario(
        key="conv_knowledge",
        mode="pipeline",
        kind="conversation",
        variants=[
            "Explique-moi en une phrase ce qu'est un arc-en-ciel.",
            "Explique-moi en une phrase ce qu'est la photosynthèse.",
            "Explique-moi en une phrase ce qu'est une marée.",
            "Explique-moi en une phrase ce qu'est un éclair.",
            "Explique-moi en une phrase ce qu'est une aurore boréale.",
        ],
    ),
    Scenario(
        key="action_wiki",
        mode="pipeline",
        kind="action_single",
        variants=[
            "Cherche sur Wikipédia qui était Ada Lovelace.",
            "Cherche sur Wikipédia qui était Marie Curie.",
            "Cherche sur Wikipédia qui était Alan Turing.",
            "Cherche sur Wikipédia qui était Grace Hopper.",
            "Cherche sur Wikipédia qui était Blaise Pascal.",
        ],
    ),
    Scenario(
        # Weather queries activate the SYSTEM skill `weather-dashboard`
        # (scripted skill → ReactSubAgentRunner, response fast-path): this
        # scenario deliberately measures the SKILL path in pipeline mode.
        # It must stay separate from action_wiki (pure tool path) — mixing
        # them makes p50/p95 uninterpretable.
        key="skill_weather_pipeline",
        mode="pipeline",
        kind="skill",
        variants=[
            "Quel temps fait-il à Paris ?",
            "Quel temps fait-il à Lyon ?",
            "Quel temps fait-il à Marseille ?",
            "Quel temps fait-il à Lille ?",
            "Quel temps fait-il à Bordeaux ?",
        ],
    ),
    Scenario(
        key="action_multi",
        mode="pipeline",
        kind="action_multi",
        variants=[
            "Quel temps fait-il à Nantes, et cherche sur Wikipédia l'histoire de Nantes.",
            "Quel temps fait-il à Strasbourg, et cherche sur Wikipédia l'histoire de Strasbourg.",
            "Quel temps fait-il à Rennes, et cherche sur Wikipédia l'histoire de Rennes.",
            "Quel temps fait-il à Dijon, et cherche sur Wikipédia l'histoire de Dijon.",
            "Quel temps fait-il à Nice, et cherche sur Wikipédia l'histoire de Nice.",
        ],
    ),
    Scenario(
        # cancel_reminder_tool prepares a deletion DRAFT (HITL draft critique
        # interrupt) and needs no OAuth connector — unlike create_reminder,
        # which creates the row directly without confirmation.
        key="hitl_draft",
        mode="pipeline",
        kind="hitl_trigger",
        variants=[
            "Annule mon prochain rappel.",
            "Supprime mon prochain rappel.",
            "Annule le prochain rappel prévu.",
            "Supprime le prochain rappel en attente.",
            "Annule mon rappel à venir.",
        ],
        seed_variants=[
            "Crée un rappel pour demain à 9h : appeler le plombier.",
            "Crée un rappel pour demain à 10h : envoyer le rapport.",
            "Crée un rappel pour demain à 11h : réserver le restaurant.",
            "Crée un rappel pour demain à 14h : appeler le garagiste.",
            "Crée un rappel pour demain à 16h : préparer la réunion.",
        ],
    ),
    Scenario(
        key="hitl_resume",
        mode="pipeline",
        kind="hitl_resume",
        variants=["Oui, confirme."],
        reset_before=False,  # must continue the pending HITL turn
    ),
    Scenario(
        key="react_conv",
        mode="react",
        kind="conversation",
        variants=[
            "Bonjour, quoi de neuf ?",
            "Salut, tout va bien ?",
            "Coucou, comment ça se passe ?",
            "Hello, en forme ?",
            "Bonsoir, ça roule ?",
        ],
    ),
    Scenario(
        # Pure single-domain tool path in ReAct mode (wikipedia, no skill
        # interference) — the ReAct counterpart of action_wiki.
        key="react_wiki",
        mode="react",
        kind="action_single",
        variants=[
            "Cherche sur Wikipédia qui était Nikola Tesla.",
            "Cherche sur Wikipédia qui était Rosalind Franklin.",
            "Cherche sur Wikipédia qui était Louis Pasteur.",
            "Cherche sur Wikipédia qui était Katherine Johnson.",
            "Cherche sur Wikipédia qui était Évariste Galois.",
        ],
    ),
    Scenario(
        # SKILL path in ReAct mode (weather-dashboard) — counterpart of
        # skill_weather_pipeline; see that scenario's note.
        key="skill_weather_react",
        mode="react",
        kind="skill",
        variants=[
            "Quel temps fait-il à Toulouse ?",
            "Quel temps fait-il à Montpellier ?",
            "Quel temps fait-il à Grenoble ?",
            "Quel temps fait-il à Angers ?",
            "Quel temps fait-il à Tours ?",
        ],
    ),
    Scenario(
        # HITL draft prepared by a mutation tool inside the ReAct loop
        # (react_execute_tools → hitl_dispatch handoff, ADR-070 parity).
        key="react_hitl_draft",
        mode="react",
        kind="hitl_trigger",
        variants=[
            "Annule mon prochain rappel.",
            "Supprime mon prochain rappel.",
            "Annule le prochain rappel prévu.",
            "Supprime le prochain rappel en attente.",
            "Annule mon rappel à venir.",
        ],
        seed_variants=[
            "Crée un rappel pour après-demain à 9h : arroser les plantes.",
            "Crée un rappel pour après-demain à 10h : payer la facture.",
            "Crée un rappel pour après-demain à 11h : relancer le client.",
            "Crée un rappel pour après-demain à 14h : réserver le train.",
            "Crée un rappel pour après-demain à 16h : sortir les poubelles.",
        ],
    ),
    Scenario(
        key="react_hitl_resume",
        mode="react",
        kind="hitl_resume",
        variants=["Oui, confirme."],
        reset_before=False,  # must continue the pending HITL turn
    ),
    Scenario(
        key="react_multi",
        mode="react",
        kind="action_multi",
        variants=[
            "Quel temps fait-il à Metz, et cherche sur Wikipédia l'histoire de Metz.",
            "Quel temps fait-il à Reims, et cherche sur Wikipédia l'histoire de Reims.",
            "Quel temps fait-il à Caen, et cherche sur Wikipédia l'histoire de Caen.",
            "Quel temps fait-il à Brest, et cherche sur Wikipédia l'histoire de Brest.",
            "Quel temps fait-il à Nancy, et cherche sur Wikipédia l'histoire de Nancy.",
        ],
    ),
]


@dataclass
class RequestResult:
    """Measured outcome of a single chat request."""

    scenario: str
    mode: str
    kind: str
    iteration: int
    query: str
    ttft_s: float | None
    total_s: float
    intention: str | None
    terminal_type: str | None
    token_count: int
    error: str | None
    # Server-side per-stage seconds for this request (metric deltas).
    stages_s: dict[str, float] = field(default_factory=dict)
    node_body_s: dict[str, float] = field(default_factory=dict)
    # LLM-call seconds per node (llm_api_latency_seconds deltas): the
    # difference stages_s[stage] - llm_s[stage] is the non-LLM overhead.
    llm_s: dict[str, float] = field(default_factory=dict)
    # Client-side arrival timeline of execution_step events (cross-check).
    client_steps: list[dict[str, Any]] = field(default_factory=list)


def parse_prometheus_samples(
    text: str,
) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
    """Parse the samples we track from a Prometheus text exposition.

    Args:
        text: Raw body of the /metrics endpoint.

    Returns:
        Mapping of (sample_name, sorted label tuples) to value, restricted to
        `TRACKED_METRICS` `_sum` / `_count` samples.
    """
    samples: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
    tracked_prefixes = tuple(f"{m}_" for m in TRACKED_METRICS)
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(tracked_prefixes):
            continue
        match = _PROM_LINE_RE.match(line)
        if match is None:
            # Unlabelled sample (no series observed yet for labelled metrics).
            parts = line.split()
            if len(parts) == 2 and parts[0].startswith(tracked_prefixes):
                try:
                    samples[(parts[0], ())] = float(parts[1])
                except ValueError:
                    pass
            continue
        name = match.group("name")
        if not (name.endswith("_sum") or name.endswith("_count")):
            continue
        labels = tuple(
            sorted(
                (m.group("key"), m.group("value"))
                for m in _PROM_LABEL_RE.finditer(match.group("labels"))
            )
        )
        try:
            samples[(name, labels)] = float(match.group("value"))
        except ValueError:
            continue
    return samples


def diff_stage_seconds(
    before: dict[tuple[str, tuple[tuple[str, str], ...]], float],
    after: dict[tuple[str, tuple[tuple[str, str], ...]], float],
    metric: str,
    label_key: str,
) -> dict[str, float]:
    """Compute per-label-value deltas of `<metric>_sum` between two scrapes.

    Args:
        before: Samples scraped before the request.
        after: Samples scraped after the request.
        metric: Base metric name (histogram).
        label_key: Label whose values become the dict keys (e.g. "stage").

    Returns:
        Mapping label value -> seconds delta (only non-zero deltas).
    """
    deltas: dict[str, float] = {}
    sum_name = f"{metric}_sum"
    for (name, labels), value in after.items():
        if name != sum_name:
            continue
        prev = before.get((name, labels), 0.0)
        delta = value - prev
        if delta <= 1e-9:
            continue
        label_map = dict(labels)
        key = label_map.get(label_key, "?")
        deltas[key] = deltas.get(key, 0.0) + delta
    return deltas


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (small-N friendly, no interpolation surprises)."""
    if not values:
        return math.nan
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[rank - 1]


class MeasureClient:
    """Thin authenticated client around the LIA HTTP API for measurements."""

    def __init__(self, base_url: str, timeout_s: float, verify_tls: bool) -> None:
        self.base_url = base_url.rstrip("/")
        # The dev API serves HTTPS with a self-signed certificate (Google OAuth
        # callbacks require TLS) — verification is opt-in via --verify-tls.
        self.http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_s, connect=15.0),
            verify=verify_tls,
        )
        self.user_id: str | None = None
        self.session_id: str | None = None

    async def close(self) -> None:
        await self.http.aclose()

    async def login_or_register(
        self, email: str, password: str, register: bool
    ) -> None:
        """Authenticate (cookie session); optionally create the perf user first."""
        resp = await self.http.post(
            f"{API_PREFIX}/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code == 401 and register:
            reg = await self.http.post(
                f"{API_PREFIX}/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "full_name": "Perf Bot",
                    "language": "fr",
                    "timezone": "Europe/Paris",
                },
            )
            reg.raise_for_status()
            resp = reg
        resp.raise_for_status()
        payload = resp.json()
        self.user_id = payload["user"]["id"]
        self.session_id = f"session_{self.user_id}"

    async def set_execution_mode(self, mode: str) -> None:
        resp = await self.http.patch(
            f"{API_PREFIX}/auth/me/execution-mode-preference",
            json={"execution_mode": mode},
        )
        resp.raise_for_status()

    async def reset_conversation(self) -> None:
        """Reset the active conversation; tolerate 'no active conversation'."""
        resp = await self.http.post(f"{API_PREFIX}/conversations/me/reset")
        if resp.status_code >= 500:
            resp.raise_for_status()

    async def scrape_metrics(
        self,
    ) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
        resp = await self.http.get("/metrics")
        resp.raise_for_status()
        return parse_prometheus_samples(resp.text)

    async def stream_chat(self, message: str) -> dict[str, Any]:
        """Send one chat message and consume the SSE stream with timings.

        Returns:
            Dict with ttft_s, total_s, intention, terminal_type, token_count,
            client_steps, error.
        """
        body = {
            "message": message,
            "user_id": self.user_id,
            "session_id": self.session_id,
        }
        ttft: float | None = None
        intention: str | None = None
        terminal: str | None = None
        error: str | None = None
        token_count = 0
        client_steps: list[dict[str, Any]] = []
        start = time.perf_counter()

        # 409 = previous run still holds the conversation lock (ADR-117):
        # retry a few times before failing the iteration.
        for attempt in range(5):
            async with self.http.stream(
                "POST", f"{API_PREFIX}/agents/chat/stream", json=body
            ) as resp:
                if resp.status_code == 409:
                    await resp.aread()
                    await asyncio.sleep(2.0 + attempt)
                    start = time.perf_counter()
                    continue
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith(SSE_DATA_PREFIX):
                        continue
                    now = time.perf_counter()
                    try:
                        chunk = json.loads(line[len(SSE_DATA_PREFIX) :])
                    except json.JSONDecodeError:
                        continue
                    ctype = chunk.get("type")
                    if ctype in FIRST_TOKEN_CHUNK_TYPES:
                        token_count += 1
                        if ttft is None:
                            ttft = now - start
                    elif ctype == "router_decision":
                        meta = chunk.get("metadata") or {}
                        intention = meta.get("intention") or intention
                    elif ctype == "execution_step":
                        meta = chunk.get("metadata") or {}
                        client_steps.append(
                            {
                                "t_s": round(now - start, 3),
                                "step": meta.get("step_name") or meta.get("step_label"),
                                "step_type": meta.get("step_type"),
                            }
                        )
                    elif ctype == "error":
                        error = str(chunk.get("content"))[:200]
                    if ctype in TERMINAL_CHUNK_TYPES:
                        terminal = ctype
                        break
                break

        return {
            "ttft_s": ttft,
            "total_s": time.perf_counter() - start,
            "intention": intention,
            "terminal_type": terminal,
            "token_count": token_count,
            "client_steps": client_steps,
            "error": error,
        }


async def run_scenario_iteration(
    client: MeasureClient,
    scenario: Scenario,
    iteration: int,
) -> RequestResult:
    """Run one iteration of one scenario, with metric scrapes around it.

    The variant index is the iteration number: passing 0 on every iteration
    (--no-cache-bust) measures the warm-cache path instead.
    """
    query = scenario.variants[iteration % len(scenario.variants)]

    if scenario.reset_before:
        await client.reset_conversation()
        # Small settle delay: reset invalidates caches server-side.
        await asyncio.sleep(0.5)

    if scenario.seed_variants:
        # Unmeasured setup turn (e.g. create the reminder the measured HITL
        # cancellation will target). Consumed fully before measuring.
        seed = scenario.seed_variants[iteration % len(scenario.seed_variants)]
        await client.stream_chat(seed)
        await asyncio.sleep(0.5)

    before = await client.scrape_metrics()
    outcome = await client.stream_chat(query)
    # Metrics flush happens in the same coroutine that ends the stream, but the
    # done chunk can be emitted before the flush line executes: settle briefly.
    await asyncio.sleep(0.7)
    after = await client.scrape_metrics()

    stages = diff_stage_seconds(
        before, after, "langgraph_stage_duration_seconds", "stage"
    )
    node_body = diff_stage_seconds(
        before, after, "agent_node_duration_seconds", "node_name"
    )
    llm = diff_stage_seconds(before, after, "llm_api_latency_seconds", "node_name")

    return RequestResult(
        scenario=scenario.key,
        mode=scenario.mode,
        kind=scenario.kind,
        iteration=iteration,
        query=query,
        ttft_s=outcome["ttft_s"],
        total_s=outcome["total_s"],
        intention=outcome["intention"],
        terminal_type=outcome["terminal_type"],
        token_count=outcome["token_count"],
        error=outcome["error"],
        stages_s={k: round(v, 3) for k, v in stages.items()},
        node_body_s={k: round(v, 3) for k, v in node_body.items()},
        llm_s={k: round(v, 3) for k, v in llm.items()},
        client_steps=outcome["client_steps"],
    )


def render_report(results: list[RequestResult]) -> str:
    """Render the p50/p95 per-scenario, per-stage markdown report."""
    lines: list[str] = []
    lines.append("## TTFT / total par scénario (client-side)\n")
    lines.append(
        "| scénario | mode | type | n | TTFT p50 | TTFT p95 | total p50 | total p95 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    by_scenario: dict[str, list[RequestResult]] = {}
    for r in results:
        by_scenario.setdefault(r.scenario, []).append(r)
    for key, rs in by_scenario.items():
        ttfts = [r.ttft_s for r in rs if r.ttft_s is not None]
        totals = [r.total_s for r in rs]
        lines.append(
            f"| {key} | {rs[0].mode} | {rs[0].kind} | {len(rs)} "
            f"| {percentile(ttfts, 50):.2f}s | {percentile(ttfts, 95):.2f}s "
            f"| {percentile(totals, 50):.2f}s | {percentile(totals, 95):.2f}s |"
        )
    lines.append("")
    lines.append(
        "## Secondes par étape (server-side, langgraph_stage_duration_seconds)\n"
    )
    for key, rs in by_scenario.items():
        stage_values: dict[str, list[float]] = {}
        for r in rs:
            for stage, seconds in r.stages_s.items():
                stage_values.setdefault(stage, []).append(seconds)
        if not stage_values:
            continue
        lines.append(f"### {key} (mode={rs[0].mode}, n={len(rs)})\n")
        lines.append("| étape | p50 (s) | p95 (s) | part p50 |")
        lines.append("|---|---|---|---|")
        p50_total = sum(percentile(v, 50) for v in stage_values.values())
        ordered = sorted(stage_values.items(), key=lambda kv: -percentile(kv[1], 50))
        for stage, values in ordered:
            p50 = percentile(values, 50)
            share = (p50 / p50_total * 100.0) if p50_total > 0 else 0.0
            lines.append(
                f"| {stage} | {p50:.2f} | {percentile(values, 95):.2f} | {share:.0f}% |"
            )
        lines.append("")
        # LLM call sites are finer-grained than graph stages (the router stage
        # contains semantic_pivot + memory_reference_extraction + query_analyzer).
        llm_values: dict[str, list[float]] = {}
        for r in rs:
            for site, seconds in r.llm_s.items():
                llm_values.setdefault(site, []).append(seconds)
        if llm_values:
            lines.append("Appels LLM par site :")
            lines.append("")
            lines.append("| site LLM | p50 (s) | p95 (s) |")
            lines.append("|---|---|---|")
            for site, values in sorted(
                llm_values.items(), key=lambda kv: -percentile(kv[1], 50)
            ):
                lines.append(
                    f"| {site} | {percentile(values, 50):.2f} | {percentile(values, 95):.2f} |"
                )
            lines.append("")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LIA_PERF_BASE_URL", "https://localhost:8000"),
    )
    parser.add_argument(
        "--verify-tls",
        action="store_true",
        help="Verify TLS certificates (default off: dev uses a self-signed cert)",
    )
    parser.add_argument("--email", default=os.environ.get("LIA_PERF_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("LIA_PERF_PASSWORD"))
    parser.add_argument(
        "--register", action="store_true", help="Create the perf user if login fails"
    )
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument(
        "--modes", default="pipeline,react", help="Comma-separated: pipeline,react"
    )
    parser.add_argument(
        "--scenarios",
        default="",
        help="Comma-separated scenario keys filter (default: all)",
    )
    parser.add_argument(
        "--timeout", type=float, default=300.0, help="Per-request timeout (seconds)"
    )
    parser.add_argument(
        "--no-cache-bust",
        action="store_true",
        help="Reuse variant 0 on every iteration",
    )
    parser.add_argument(
        "--output",
        default="",
        help="JSON output path (default: scripts/perf/results/<ts>.json)",
    )
    args = parser.parse_args()

    if not args.email or not args.password:
        parser.error(
            "--email/--password (or LIA_PERF_EMAIL/LIA_PERF_PASSWORD) are required"
        )

    modes = {m.strip() for m in args.modes.split(",") if m.strip()}
    wanted = {s.strip() for s in args.scenarios.split(",") if s.strip()}
    scenarios = [
        s for s in SCENARIOS if s.mode in modes and (not wanted or s.key in wanted)
    ]
    # A resume scenario only makes sense right after its draft scenario.
    keys = [s.key for s in scenarios]
    if "hitl_resume" in keys and "hitl_draft" not in keys:
        scenarios = [s for s in scenarios if s.key != "hitl_resume"]
    if "react_hitl_resume" in keys and "react_hitl_draft" not in keys:
        scenarios = [s for s in scenarios if s.key != "react_hitl_resume"]

    client = MeasureClient(args.base_url, args.timeout, args.verify_tls)
    results: list[RequestResult] = []
    current_mode: str | None = None
    try:
        await client.login_or_register(args.email, args.password, args.register)
        print(
            f"# measure_ttft — {args.base_url} — user {client.user_id} — {datetime.now(UTC).isoformat()}"
        )

        for iteration in range(args.iterations):
            for scenario in scenarios:
                if scenario.mode != current_mode:
                    await client.set_execution_mode(scenario.mode)
                    current_mode = scenario.mode
                effective_iteration = 0 if args.no_cache_bust else iteration
                result = await run_scenario_iteration(
                    client, scenario, effective_iteration
                )
                results.append(result)
                status = result.error or result.terminal_type or "?"
                ttft_str = (
                    f"{result.ttft_s:.2f}s" if result.ttft_s is not None else "n/a"
                )
                print(
                    f"  [{iteration + 1}/{args.iterations}] {scenario.key:<16} ttft={ttft_str:<8} "
                    f"total={result.total_s:.2f}s tokens={result.token_count} end={status}"
                )
    finally:
        # Always restore a deterministic preference for the perf user.
        try:
            if current_mode != "pipeline":
                await client.set_execution_mode("pipeline")
        except httpx.HTTPError:
            pass
        await client.close()

    report = render_report(results)
    print("\n" + report)

    output = (
        Path(args.output)
        if args.output
        else (
            Path(__file__).parent
            / "results"
            / f"ttft_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "run_id": str(uuid.uuid4()),
                "timestamp": datetime.now(UTC).isoformat(),
                "base_url": args.base_url,
                "iterations": args.iterations,
                "results": [r.__dict__ for r in results],
                "report_markdown": report,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nJSON: {output}")

    failures = [r for r in results if r.error or r.terminal_type is None]
    return 1 if failures and len(failures) == len(results) else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
