# Computed Answers (Sandboxed Scripts)

## Can LIA actually calculate, or does it estimate like other AIs?
It can calculate. Since v1.37 (ADR-249), when a question needs real computation — adding up many durations, matching two lists against each other, converting times across timezones, deduplicating entries — LIA writes a few lines of Python and **runs them**, then answers from the result. A language model asked the same question answers plausibly and gives you no way to see that it is wrong; a script gives an answer you could check yourself.

## When does LIA use a script instead of just answering?
The assistant decides, and it is told explicitly not to reach for a script when it can answer directly: a simple lookup, a two-number sum, or a question about text does not need one. Scripts are for arithmetic over many rows, joins by key, timezone-aware durations, sorting or deduplication — cases where a model's fluency is exactly the problem. Most conversations never trigger one.

## Which mode does this work in?
The **autonomous (ReAct)** mode only. The deterministic pipeline mode does not offer the tool at all — it plans its steps in advance, and it already has skills and plugins for structured work. Switch modes from the chat header; the choice is saved per user.

## What can a sandboxed script reach?
Nothing you would not want it to. Each run starts a **throwaway container** with **no network at all**, no database access, no Docker socket, a read-only root filesystem apart from a temporary directory, an unprivileged account and every Linux capability dropped. The only data a script sees is what the current turn already collected and passed to it, and the container is discarded when the run ends. It is the same sandbox LIA uses for user-installed skills, which was built and hardened for exactly this threat.

## Can I see the code that ran?
Administrators can, in the **debug panel**, with the script's stated purpose, its full source and its output. Hiding it would buy no security — the model wrote the code, so it is already in the conversation's context — and would cost all of the verifiability. Regular users see the answer, not the plumbing.

## Are the results trusted?
The output is explicitly marked as **untrusted content** before it reaches the model, exactly like the body of an incoming e-mail: it is model-written code running over third-party data. That marking is what keeps a hostile document from turning a script's output into instructions.

## What are the limits?
A turn may spend a small number of script runs (3 by default) so a repair loop cannot spin, each run is bounded in time and memory by the skills sandbox settings, and a per-user rate limit applies (20 runs per 5 minutes by default). The available libraries are published to the assistant up front — the Python standard library plus numpy, pandas, openpyxl, python-dateutil and pytz — along with every bound, so it never wastes an attempt discovering a limit by hitting it.

## How do I turn it off on my own server?
Set `PYTHON_SANDBOX_TOOL_ENABLED=false` in your `.env`. It is on by default. With the flag off the tool does not exist at runtime — the assistant is never offered it and never mentions it. The runs-per-turn and rate-limit bounds are configurable too (`PYTHON_SANDBOX_MAX_RUNS_PER_TURN`, `PYTHON_SANDBOX_RATE_LIMIT_CALLS`, `PYTHON_SANDBOX_RATE_LIMIT_WINDOW`).

## Does it need Docker?
Yes. Script execution requires the container sandbox; the older in-process sandbox mode is **refused** for this feature, because it only isolates when the API itself runs as root — an acceptable trade-off for a skill you installed deliberately, not for code a model wrote after reading an e-mail. On an install without the container sandbox available, LIA simply answers without scripts.
