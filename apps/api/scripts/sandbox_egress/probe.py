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
4. once the run is withdrawn, the same token is refused;
5. a skill's command (ADR-327 lot 3) reaches its declared hosts with npm,
   npx, git, pip and curl — each pointed at the proxy's CA — an undeclared
   host is refused, git refuses the proxy without ``GIT_SSL_CAINFO``, Node's
   own ``fetch`` goes through the proxy under ``NODE_USE_ENV_PROXY`` and finds
   no route without it, and the time of a per-run ``npm install`` is measured.

The echo upstream is httpbin.org, which answers with the headers and query it
received: the proof is what the UPSTREAM saw, not what the sandbox sent.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import textwrap
import uuid
from collections.abc import Callable
from pathlib import Path

from src.core.config import get_settings
from src.core.constants import (
    PYTHON_SANDBOX_EGRESS_CA_DIR,
    PYTHON_SANDBOX_EGRESS_CA_FILE,
    PYTHON_SANDBOX_EGRESS_CA_VOLUME,
    PYTHON_SANDBOX_EGRESS_CONFIG_DIR,
    PYTHON_SANDBOX_EGRESS_NETWORK,
)
from src.domains.agents.python_sandbox.egress.publisher import EgressPublisher
from src.domains.agents.python_sandbox.egress.registry import LiveRun, RunCredential
from src.domains.agents.python_sandbox.egress.ruleset import SECRETS_DIRNAME
from src.domains.agents.python_sandbox.egress.service import deployment_publisher
from src.domains.skills.command_bundle import pack_bundle
from src.domains.skills.command_sandbox import run_command
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


#: What a skill's command declares: the package registries and git's host.
COMMAND_HOSTS = ("registry.npmjs.org", "github.com", "pypi.org", "files.pythonhosted.org")

#: The command's own script, carried in the skill folder: one tab-separated
#: line per probe — label, ok/refused, milliseconds, the output's tail.
COMMAND_SCRIPT = """set -u
probe() {
  local label=$1; shift
  local start out status
  start=$(date +%s%N)
  if out=$("$@" 2>&1); then status=ok; else status=refused; fi
  printf '%s\\t%s\\t%s\\t%s\\n' "$label" "$status" "$(( ($(date +%s%N) - start) / 1000000 ))" \\
    "$(printf '%s' "$out" | tail -c 160 | tr '\\n\\t' '  ')"
}
probe npm_view npm view is-number@7.0.0 version
probe npm_install npm install --no-audit --no-fund --no-save docx@9
probe node_require node -e "require('docx'); console.log('loaded')"
probe npx npx --yes semver@7.6.3 1.2.3
probe git_clone git clone --quiet --depth 1 https://github.com/octocat/Hello-World hw
probe pip_download pip download --quiet --no-deps --dest pipdl six==1.16.0
probe curl_declared curl -sS --fail -o /dev/null -w '%{http_code}' https://registry.npmjs.org/is-number
probe curl_undeclared curl -sS --fail -o /dev/null https://www.wikipedia.org
probe node_fetch node -e "fetch('https://registry.npmjs.org/is-number').then(r => console.log(r.status))"
probe node_fetch_without_env_proxy env -u NODE_USE_ENV_PROXY node -e "fetch('https://registry.npmjs.org/is-number').then(r => console.log(r.status))"
probe node_version node --version
probe git_without_ca env -u GIT_SSL_CAINFO git ls-remote https://github.com/octocat/Hello-World HEAD
"""


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

    print("== 5. a skill's command")
    await _command_section(publisher, check)

    failed = [label for label, ok, _ in verdicts if not ok]
    print(f"\n{len(verdicts) - len(failed)}/{len(verdicts)} checks passed")
    return 1 if failed else 0


async def _command_section(
    publisher: EgressPublisher, check: Callable[[str, bool, str], None]
) -> None:
    """Run one command on the published hosts, through the real sandbox path."""
    settings = get_settings()
    run = LiveRun(
        run_id="probe-cmd-" + uuid.uuid4().hex[:12],
        user_id="probe",
        hosts=COMMAND_HOSTS,
        credentials=(),
    )
    with tempfile.TemporaryDirectory() as folder:
        Path(folder, "probe.sh").write_text(COMMAND_SCRIPT, encoding="utf-8")
        bundle = pack_bundle(Path(folder), [], max_bytes=1024 * 1024)
    async with publisher.serve(run, {}):
        output = await run_command(
            skill_name="egress-probe",
            command="bash probe.sh",
            bundle=bundle,
            settings=settings,
            user_id="probe",
            egress=_spec({}),
        )
    rows = {
        cells[0]: cells[1:]
        for line in output.stdout.splitlines()
        if len(cells := line.split("\t")) == 4
    }
    expected = {
        "npm_view": "ok",
        "npm_install": "ok",
        "node_require": "ok",
        "npx": "ok",
        "git_clone": "ok",
        "pip_download": "ok",
        "curl_declared": "ok",
        "curl_undeclared": "refused",
        # Node's own fetch follows HTTPS_PROXY only under NODE_USE_ENV_PROXY,
        # which the egress arguments set: without it, no route (measured on Node 24).
        "node_fetch": "ok",
        "node_fetch_without_env_proxy": "refused",
        "node_version": "ok",
        # Why git is pointed at the proxy's CA: its TLS library ignores
        # SSL_CERT_FILE, so without GIT_SSL_CAINFO it refuses the proxy's
        # certificate on a host it was allowed to reach.
        "git_without_ca": "refused",
    }
    for label, wanted in expected.items():
        status, millis, tail = rows.get(label, ("missing", "-", output.stderr[-160:]))
        check(f"command: {label} {wanted}", status == wanted, f"{millis} ms  {tail}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
