"""Measure the sandbox egress path on a running deployment (ADR-298).

A MEASUREMENT, never a gate (the ``mobile:probe`` shape): it needs the Docker
socket, the egress proxy, the shared config volume and the Internet, none of
which a unit test has — and a test that mocks the proxy proves nothing about
the topology. Run it inside the API container::

    task sandbox:egress:probe

What it proves, each on the REAL proxy through the REAL publisher and the
REAL executor (no flag is duplicated here):

1. the proxy answers /healthz and accepts an authenticated reload;
2. from a published run, a raw socket has nowhere to go, a declared host
   answers through the proxy, an undeclared host is refused (403), a private
   address is refused;
3. a per-run token is swapped for the real key on the declared host — in a
   header AND in a query string — and the sandbox never saw the key;
4. once the run is withdrawn, the same token is refused.

The echo upstream is httpbin.org, which answers with the headers and query it
received: the proof is what the UPSTREAM saw, not what the sandbox sent.
"""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
import uuid

from src.core.config import get_settings
from src.core.constants import (
    PYTHON_SANDBOX_EGRESS_CA_DIR,
    PYTHON_SANDBOX_EGRESS_CA_FILE,
    PYTHON_SANDBOX_EGRESS_CA_VOLUME,
    PYTHON_SANDBOX_EGRESS_CONFIG_DIR,
    PYTHON_SANDBOX_EGRESS_NETWORK,
)
from src.domains.agents.python_sandbox.egress.registry import LiveRun, RunCredential
from src.domains.agents.python_sandbox.egress.ruleset import SECRETS_DIRNAME
from src.domains.agents.python_sandbox.egress.service import deployment_publisher
from src.domains.skills.executor import EgressSpec, SkillScriptExecutor

ECHO_HOST = "httpbin.org"
ALLOWED_HOST = "example.com"
REAL_HEADER_KEY = "REAL-HEADER-SECRET-" + uuid.uuid4().hex[:8]
REAL_QUERY_KEY = "REAL-QUERY-SECRET-" + uuid.uuid4().hex[:8]

SCRIPT = textwrap.dedent("""
    import json, os, socket, sys
    import requests
    out = {}
    def probe(label, fn):
        try:
            out[label] = ["ok", fn()]
        except Exception as e:
            out[label] = ["refused", type(e).__name__ + ": " + str(e)[-160:]]
    probe("raw_dns", lambda: socket.gethostbyname("example.com"))
    probe("raw_tcp", lambda: socket.create_connection(("1.1.1.1", 443), timeout=3) and "connected")
    probe("allowed_host", lambda: requests.get("https://example.com", timeout=15).status_code)
    probe("undeclared_host", lambda: requests.get("https://www.wikipedia.org", timeout=15).status_code)
    probe("private_ip", lambda: requests.get("https://10.0.0.1/", timeout=5).status_code)
    tok_h = os.environ.get("LIA_KEY_PROBE_HEADER", "")
    tok_q = os.environ.get("LIA_KEY_PROBE_QUERY", "")
    probe("echo_header", lambda: requests.get(
        "https://httpbin.org/headers", headers={"X-Probe-Key": tok_h}, timeout=20).json()["headers"].get("X-Probe-Key"))
    probe("echo_query", lambda: requests.get(
        "https://httpbin.org/get", params={"appid": tok_q}, timeout=20).json()["args"].get("appid"))
    out["sandbox_env_has_real_key"] = any("REAL-" in v for v in os.environ.values())
    out["tokens_seen"] = {"header": tok_h[:4], "query": tok_q[:4]}
    print(json.dumps(out))
    """)

RETRY_SCRIPT = textwrap.dedent("""
    import json, os, requests
    tok = os.environ.get("LIA_KEY_PROBE_HEADER", "")
    try:
        r = requests.get("https://httpbin.org/headers", headers={"X-Probe-Key": tok}, timeout=20)
        print(json.dumps({"status": r.status_code, "echoed": r.json()["headers"].get("X-Probe-Key")}))
    except Exception as e:
        print(json.dumps({"status": "refused", "error": type(e).__name__}))
    """)


def _spec(tokens: dict[str, str]) -> EgressSpec:
    settings = get_settings()
    return EgressSpec(
        network=PYTHON_SANDBOX_EGRESS_NETWORK,
        proxy_url=settings.python_sandbox_egress_proxy_url,
        ca_volume=PYTHON_SANDBOX_EGRESS_CA_VOLUME,
        ca_dir=PYTHON_SANDBOX_EGRESS_CA_DIR,
        ca_file=PYTHON_SANDBOX_EGRESS_CA_FILE,
        tokens=tokens,
    )


async def main() -> int:
    settings = get_settings()
    verdicts: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str) -> None:
        verdicts.append((label, ok, detail))
        print(f"  [{'OK' if ok else 'KO'}] {label:42s} {detail}")

    print("== 1. proxy")
    publisher = await deployment_publisher()
    healthy = await publisher.proxy.healthy()
    check("proxy /healthz", healthy, settings.python_sandbox_egress_health_url)
    await publisher.publish()
    check("authenticated reload", True, "POST /v1/reload -> ok")

    run_id = "probe-" + uuid.uuid4().hex[:12]
    tok_h, tok_q = "sbx_probe_h_" + uuid.uuid4().hex[:8], "sbx_probe_q_" + uuid.uuid4().hex[:8]
    secrets_dir = f"{PYTHON_SANDBOX_EGRESS_CONFIG_DIR}/{SECRETS_DIRNAME}/{run_id}"
    run = LiveRun(
        run_id=run_id,
        user_id="probe",
        hosts=(ALLOWED_HOST, ECHO_HOST),
        credentials=(
            RunCredential(
                connector="probe_header",
                host=ECHO_HOST,
                token=tok_h,
                auth_method="header",
                auth_name="X-Probe-Key",
                secret_path=f"{secrets_dir}/probe_header.key",
            ),
            RunCredential(
                connector="probe_query",
                host=ECHO_HOST,
                token=tok_q,
                auth_method="query",
                auth_name="appid",
                secret_path=f"{secrets_dir}/probe_query.key",
            ),
        ),
    )
    tokens = {"LIA_KEY_PROBE_HEADER": tok_h, "LIA_KEY_PROBE_QUERY": tok_q}

    print("== 2-3. a published run")
    async with publisher.serve(
        run, {"probe_header": REAL_HEADER_KEY, "probe_query": REAL_QUERY_KEY}
    ):
        result = await SkillScriptExecutor.execute_source(
            source=SCRIPT,
            payload={"items": {}},
            label="egress-probe",
            timeout_seconds=settings.python_sandbox_network_timeout_seconds,
            user_id="probe",
            egress=_spec(tokens),
        )
    if not result.success:
        print("script failed:", result.error)
        return 2
    out = json.loads(result.output.strip().splitlines()[-1])
    check("raw DNS refused", out["raw_dns"][0] == "refused", out["raw_dns"][1])
    check("raw TCP refused", out["raw_tcp"][0] == "refused", out["raw_tcp"][1])
    check(
        "declared host answers via proxy",
        out["allowed_host"] == ["ok", 200],
        str(out["allowed_host"]),
    )
    check(
        "undeclared host refused (403)",
        out["undeclared_host"][0] == "refused" and "403 Forbidden" in out["undeclared_host"][1],
        str(out["undeclared_host"]),
    )
    check("private address refused", out["private_ip"][0] == "refused", str(out["private_ip"]))
    check(
        "header token swapped for the real key",
        out["echo_header"] == ["ok", REAL_HEADER_KEY],
        str(out["echo_header"]),
    )
    check(
        "query token swapped for the real key",
        out["echo_query"] == ["ok", REAL_QUERY_KEY],
        str(out["echo_query"]),
    )
    check(
        "sandbox never saw a real key",
        out["sandbox_env_has_real_key"] is False,
        str(out["tokens_seen"]),
    )

    print("== 4. after withdrawal")
    result = await SkillScriptExecutor.execute_source(
        source=RETRY_SCRIPT,
        payload={"items": {}},
        label="egress-probe",
        timeout_seconds=settings.python_sandbox_network_timeout_seconds,
        user_id="probe",
        egress=_spec(tokens),
    )
    out = json.loads(result.output.strip().splitlines()[-1]) if result.success else {}
    check(
        "withdrawn run: host refused, token dead",
        out.get("status") == "refused" or out.get("echoed") not in (REAL_HEADER_KEY, tok_h),
        str(out),
    )

    failed = [label for label, ok, _ in verdicts if not ok]
    print(f"\n{len(verdicts) - len(failed)}/{len(verdicts)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
