"""Catalogue manifest of the ephemeral-Python tool (ADR-249).

Everything the tool enforces is stated here, because a model can only respect a
bound it can read (ADR-184): the sandbox has no network, the data arrives on
stdin, the libraries are the ones listed, and the budgets are finite. The
description also says when NOT to reach for it — without that sentence a
capable tool becomes a hammer.
"""

from src.core.constants import EXECUTION_MODE_REACT, PYTHON_SANDBOX_AGENT_NAME
from src.domains.agents.registry.catalogue import (
    REASON_SANDBOXED_CONTAINER,
    CostProfile,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

_DESCRIPTION = (
    "**Tool: run_python_tool** - Run a short Python script in an isolated sandbox "
    "and get its stdout back.\n"
    "**Use for** what a language model does badly: arithmetic over many rows, "
    "joining or deduplicating records on a key, durations and dates across "
    "timezones, sorting on several keys, statistics, parsing a CSV/XLSX payload.\n"
    "**Do not use** for a single API call, a simple lookup, a two-number calculation "
    "or anything you can answer directly — it costs a container.\n"
    "**Input**: the data already collected this turn is handed to your script on "
    'stdin as JSON. `json.load(sys.stdin)["items"]` is a dict of collected items '
    "keyed by id — reference it instead of re-typing the data.\n"
    "**Output**: whatever you print to stdout comes back to you. Print a result, "
    "not a log.\n"
    "**Environment**: NO NETWORK (no HTTP, no DNS), no database, no filesystem "
    "beyond /tmp, fresh container each run. Available: the standard library plus "
    "numpy, pandas, openpyxl, python-dateutil, pytz. Bounds: 30 s, 512 MB, 50 KB "
    "of stdout, a few runs per turn."
)

run_python_catalogue_manifest = ToolManifest(
    name="run_python_tool",
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
                "to stdout. No network calls."
            ),
        ),
        ParameterSchema(
            name="purpose",
            type="string",
            required=True,
            description="One short sentence on what this computes (shown to administrators).",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="stdout", type="string", description="What the script printed."),
        OutputFieldSchema(
            path="traceback", type="string", description="The error, when the script failed."
        ),
    ],
    cost=CostProfile(est_tokens_in=400, est_tokens_out=300, est_latency_ms=1500),
    permissions=PermissionProfile(required_scopes=[]),
    semantic_keywords=[
        "compute calculate aggregate combine rows",
        "python script sandbox arithmetic statistics",
        "deduplicate join sort group durations",
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
