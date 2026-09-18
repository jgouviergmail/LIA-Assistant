"""Catalogue manifest of the ephemeral-Python tool (ADR-249, ADR-298).

Everything the tool enforces is stated here, because a model can only respect a
bound it can read (ADR-184): the data arrives on stdin, the libraries are the
ones :mod:`libraries` declares, the network is the hosts a run DECLARES, and
the budgets are the settings that enforce them — never a number in prose. The
description also says what the tool is FOR (four roles: calculate, diagnose,
fill a gap, transform) and when NOT to reach for it — without that sentence a
capable tool becomes a hammer.
"""

from src.core.config import settings
from src.core.constants import (
    EXECUTION_MODE_REACT,
    PYTHON_SANDBOX_AGENT_NAME,
    PYTHON_SANDBOX_TOOL_NAME,
)
from src.domains.agents.python_sandbox.libraries import render_libraries
from src.domains.agents.registry.catalogue import (
    REASON_SANDBOXED_CONTAINER,
    CostProfile,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

_DESCRIPTION = (
    "**Tool: run_python_tool** - Write a short Python script, run it in a fresh "
    "sandbox, get its stdout back. Four jobs:\n"
    "1. **Calculate** what a language model does badly: arithmetic over many rows, "
    "joins and deduplication on a key, durations and dates across timezones, "
    "multi-key sorting, statistics.\n"
    "2. **Diagnose** a tool that failed with EXTERNAL_API_ERROR or TIMEOUT: probe "
    "the service over HTTPS and tell « the service is down », « authentication "
    "refused » and « the failure is ours » apart, with the status code and latency "
    "you measured.\n"
    "3. **Fill a gap**: when no tool does what the step needs and a reachable "
    "service does, write a temporary client — a request, a parse, the fields you "
    "need — and correct your own code from the traceback.\n"
    "4. **Transform**: parse CSV/XLSX/XML/RSS/HTML/ICS payloads, normalise phone "
    "numbers, countries or accents, reshape a table.\n"
    "**Do not use** for what an existing tool already does, a single lookup, a "
    "two-number calculation or a reformulation.\n"
    "**Input**: the data collected this turn is handed to your script on stdin as "
    'JSON — `json.load(sys.stdin)["items"]` is a dict of items keyed by id; '
    "reference it, never re-type it.\n"
    "**Output**: whatever you print comes back to you. Print a result, not a log.\n"
    "**Network**: HTTPS only, through the sandbox proxy, to the hosts you declare "
    f"in `hosts` (at most {settings.python_sandbox_max_hosts_per_run}); an undeclared "
    "host is refused. A host of the person's connectors carries a credential token in "
    'the environment: send `os.environ["LIA_KEY_<CONNECTOR>"]` — the value, never the '
    "name — in that host's own header or query; the proxy swaps it for the real key. "
    "Never print it.\n"
    "**Environment**: fresh container each run, no database, no filesystem beyond "
    f"/tmp. Bounds: {settings.skills_script_timeout_seconds} s, "
    f"{settings.skills_script_max_memory_mb} MB, "
    f"{settings.skills_script_max_output_kb} KB of stdout, "
    f"{settings.python_sandbox_max_runs_per_turn} run(s) per turn. "
    f"Beyond the standard library:\n{render_libraries()}"
)

run_python_catalogue_manifest = ToolManifest(
    name=PYTHON_SANDBOX_TOOL_NAME,
    mutation_policy="sandboxed",
    mutation_policy_reason=REASON_SANDBOXED_CONTAINER,
    agent=PYTHON_SANDBOX_AGENT_NAME,
    description=_DESCRIPTION,
    parameters=[
        ParameterSchema(
            name="code",
            type="string",
            required=True,
            description=(
                "Python source. Reads its input from stdin as JSON; prints its result "
                "to stdout. Reaches only the hosts declared in `hosts`."
            ),
        ),
        ParameterSchema(
            name="purpose",
            type="string",
            required=True,
            description="One short sentence on what this computes (shown to administrators).",
        ),
        ParameterSchema(
            name="hosts",
            type="array",
            required=False,
            description=(
                "Hosts the script will reach over HTTPS, as bare lowercase hostnames "
                "(no scheme, port, path or IP). Omit for a run with no network. A host "
                "must be permitted: one of the person's connectors, the operator's "
                "list, or the person's own approval — an unknown host is asked of the "
                "person before the run, or refused."
            ),
            # ADR-184: the bound the tool enforces is the bound the model reads.
            constraints=[
                ParameterConstraint(
                    kind="max_length", value=settings.python_sandbox_max_hosts_per_run
                )
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="stdout", type="string", description="What the script printed."),
        OutputFieldSchema(
            path="traceback", type="string", description="The error, when the script failed."
        ),
        OutputFieldSchema(
            path="hosts", type="array", description="The hosts a network run could reach."
        ),
        OutputFieldSchema(
            path="turn_data_shared",
            type="boolean",
            description="Whether the turn's collected data reached the script on stdin.",
        ),
    ],
    cost=CostProfile(est_tokens_in=400, est_tokens_out=300, est_latency_ms=1500),
    permissions=PermissionProfile(required_scopes=[]),
    semantic_keywords=[
        "compute calculate aggregate combine rows",
        "python script sandbox arithmetic statistics",
        "deduplicate join sort group durations",
        "diagnose outage service down probe latency status code",
        "api client integration missing tool temporary code",
        "parse transform csv xlsx xml rss html ics payload",
    ],
    tool_category="readonly",
    version="1.0.0",
    maintainer="Team AI",
    initiative_eligible=False,
    # ADR-249: the pipeline plans ahead and cannot repair a failing script from
    # its traceback; it uses skills and plugins instead (owner arbitration).
    execution_modes=frozenset({EXECUTION_MODE_REACT}),
)

PYTHON_SANDBOX_CATALOGUE_MANIFESTS = (run_python_catalogue_manifest,)
