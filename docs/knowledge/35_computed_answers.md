# Computed Answers (Sandboxed Scripts)

## Can LIA actually calculate, or does it estimate like other AIs?
It can calculate. Since v1.37 (ADR-249), when a question needs real computation — adding up many durations, matching two lists against each other, converting times across timezones, deduplicating entries — LIA writes a few lines of Python and **runs them**, then answers from the result. A language model asked the same question answers plausibly and gives you no way to see that it is wrong; a script gives an answer you could check yourself.

## When does LIA use a script instead of just answering?
The assistant decides, and it is told explicitly not to reach for a script when it can answer directly: a simple lookup, a two-number sum, or a question about text does not need one. Scripts are for arithmetic over many rows, joins by key, timezone-aware durations, sorting or deduplication — cases where a model's fluency is exactly the problem. Most conversations never trigger one.

## Which mode does this work in?
The **autonomous (ReAct)** mode only. The deterministic pipeline mode does not offer the tool at all — it plans its steps in advance, and it already has skills and plugins for structured work. Switch modes from the chat header; the choice is saved per user.

## What can a sandboxed script reach?
Nothing you would not want it to. Each run starts a **throwaway container** with no database access, no Docker socket, a read-only root filesystem apart from a temporary directory, an unprivileged account and every Linux capability dropped. A script that declares no host has **no network at all**; a script that declares hosts reaches them — and nothing else — through one dedicated proxy (see below). The only data a script sees is what the current turn already collected and passed to it, and the container is discarded when the run ends. It is the same sandbox LIA uses for user-installed skills, which was built and hardened for exactly this threat.

## Can a script LIA writes reach the Internet?
Yes, since v1.46.0 (ADR-298), in ReAct mode only, and never directly. When a step needs a service no tool covers — checking that an API answers, reading a feed, calling an endpoint you use — the script declares the hosts it needs and goes out through a **dedicated egress proxy**: HTTPS only, to those hosts and nowhere else. Private networks, the server itself and cloud metadata are always refused. A script that declares no host stays fully offline, as before. Your administrator can switch the network off from the capability map (**Sandbox network access**) while keeping the calculator.

## Do my API keys ever enter the script?
No. The services you connected with your own API key (web search, answer engine, weather) are reachable without a question, and the script only ever sees a **temporary token** valid for that single run: the proxy swaps it for your real key on the host of that connector alone. The key never enters the container, and LIA's own account keys, OAuth tokens and your sign-in credentials are never offered to a script at all.

## What does the question with three answers mean?
When a script wants a host that is neither one of your connectors nor on your instance's list, LIA stops and asks you, in the chat, with three answers:
- **Allow with the data** — the script may send what LIA gathered this turn (your mails, events…) to that host.
- **Allow without the data** — the script runs, but receives nothing of what LIA gathered; it can only reach the host.
- **Refuse** — LIA answers with what it already has.

The rest of your request then goes on — a question is not the end of the answer — and your answer is remembered as a permission. Past a number of permissions, a new approval holds for its run only.

## Where do I see and revoke the hosts I allowed?
In **Settings → Sandbox network**, which appears once your administrator enabled the network. It lists the hosts a script may reach without asking (your connectors, the hosts your instance allows for everyone) and every permission you gave, each with the date it was last used, a switch to change its scope — with or without the data of the turn — and a **Revoke** button; LIA will ask again the next time a script wants that host. Deleting your account deletes them all.

## What roles does a script serve?
Four, stated to the assistant: **compute** (arithmetic over many rows, joins, durations across timezones), **diagnose** (check that a service answers, read a status endpoint), **fill a gap** no tool covers (call an API you use), and **transform** data (parse a feed, a calendar file, an XML, a spreadsheet). Twenty-two libraries are declared to the assistant and verified in the built image on every CI run.

## Can I see the code that ran?
Administrators can, in the **debug panel**, with the script's stated purpose, its full source and its output. Hiding it would buy no security — the model wrote the code, so it is already in the conversation's context — and would cost all of the verifiability. Regular users see the answer, not the plumbing.

## Are the results trusted?
The output is explicitly marked as **untrusted content** before it reaches the model, exactly like the body of an incoming e-mail: it is model-written code running over third-party data. That marking is what keeps a hostile document from turning a script's output into instructions.

## What are the limits?
A turn may spend a small number of script runs (5 by default; a question asked about a host costs none of them) so a repair loop cannot spin, each run is bounded in time and memory by the skills sandbox settings, a network run has its own wall-clock budget and a bound on the hosts it may declare, and a per-user rate limit applies (20 runs per 5 minutes by default). The available libraries are published to the assistant up front — the Python standard library plus twenty-two declared libraries for HTTP and parsing, data and tables, dates and calendars, documents, text and formats — along with every bound, so it never wastes an attempt discovering a limit by hitting it.

## How do I turn it off on my own server?
Set `PYTHON_SANDBOX_TOOL_ENABLED=false` in your `.env`. It is on by default. With the flag off the tool does not exist at runtime — the assistant is never offered it and never mentions it. The runs-per-turn and rate-limit bounds are configurable too (`PYTHON_SANDBOX_MAX_RUNS_PER_TURN`, `PYTHON_SANDBOX_RATE_LIMIT_CALLS`, `PYTHON_SANDBOX_RATE_LIMIT_WINDOW`).

## How do I control the network on my own server?
The egress proxy ships with the skill-sandbox Compose overlay, which switches the network on (`PYTHON_SANDBOX_EGRESS_ENABLED=true`) together with the proxy it needs; the base install keeps it off. `PYTHON_SANDBOX_EGRESS_HOSTS` lists the hosts every account may reach without being asked, `PYTHON_SANDBOX_EGRESS_ASK_ENABLED=false` refuses an unknown host instead of asking, and `PYTHON_SANDBOX_MAX_GRANTS_PER_USER`, `PYTHON_SANDBOX_MAX_HOSTS_PER_RUN` and `PYTHON_SANDBOX_NETWORK_TIMEOUT_SECONDS` bound the permissions, the hosts of a run and its duration. The admin panel's capability map switches the whole network off without a restart, and the alert `SandboxEgressProxyDown` watches the proxy's health.

## Does it need Docker?
Yes. Script execution requires the container sandbox; the older in-process sandbox mode is **refused** for this feature, because it only isolates when the API itself runs as root — an acceptable trade-off for a skill you installed deliberately, not for code a model wrote after reading an e-mail. On an install without the container sandbox available, LIA simply answers without scripts.
