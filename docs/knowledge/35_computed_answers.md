# Computed Answers (Sandboxed Scripts)

## Does LIA calculate, or estimate like other AIs?

It calculates. A language model asked for a figure answers plausibly, with nothing to tell you when it is wrong — so LIA is told to hand every figure it must compute to a tool, never to work it out in its head:
• **arithmetic** in exact decimal — percentages, totals, splits, VAT, interest
• **dates and times** on real instants — days until a date, working days, ages, time zones, clock changes
• **currencies** at the European Central Bank reference rate, with its date

These work in both modes, with nothing to set up. When a result had to be rounded, LIA says "about".

For what no tool covers — adding up dozens of rows, matching two lists, reading a feed — LIA can, in ReAct mode, write a few lines of Python, run them in a sandbox and answer from the result.

## Can LIA do exact calculations, count days or convert currencies?

Yes, and it does not do them in its head.

**🧮 Calculations:**
• *What is 17.5% of €1,234.56?*
• *Split €1,550 between four people*

LIA computes in exact decimal: 0.1 + 0.2 is 0.3. When a result had to be rounded — a division that does not come out even, a square root —, it says so ("about").

**📅 Dates:**
• *How many days until 14 July?*
• *Add 10 working days to today*
• *What time is it in Tokyo?*

Working days run Monday to Friday, **public holidays not deducted** — it says so. A duration in hours counts the time really elapsed, clock changes included.

**💱 Currencies:**
• *How much is 250 dollars in euros?*

At the **European Central Bank** reference rate, whose date LIA gives. A bank or a card applies its own rate and fees: it is a reliable order of magnitude, not the amount on your statement.

These calculations work in Pipeline and ReAct mode alike, with nothing to set up.

## When does LIA write a script instead of just answering?

In ReAct mode, when computing beats guessing. A script serves four purposes:
• **compute** what a model does badly: totals over many rows, joins by key, deduplication, durations across time zones
• **transform** data: a spreadsheet, a CSV, an XML file, an RSS feed, a calendar file
• **diagnose** a service a tool failed to reach: does it answer, how fast
• **fill a gap** no tool covers, by calling a service directly

The last two need network access, which your administrator may or may not have enabled.

LIA is told not to write one for a simple lookup, a sum of two numbers or a question about text: most conversations never use one. For example:
• *How many hours of meetings did I have this month, week by week?*
• *Among my last 50 e-mails, which senders wrote to me more than three times?*

## Which mode do I need for calculations and scripts?

**Calculations, dates and currency conversions** work in both Pipeline (🔀) and ReAct (⚡) mode.

**Scripts** run in **ReAct mode** only. The Pipeline mode plans every step in advance and cannot read a script's error to correct it, so the script tool is never offered there — it relies on its tools, skills and plugins instead.

Switch with the 🔀/⚡ toggle in the chat header; your choice is saved.

## What can a script LIA writes reach?

Very little, by design. Each run starts in a **throwaway container**, discarded when it ends:
• no access to your mailbox, calendar, connectors or LIA's database
• the only data it receives is what LIA already gathered for the current request, handed to it as input — never re-typed into the code
• a read-only system apart from a temporary folder, an unprivileged account, no system privileges
• **no network**, unless it declares the hosts it needs and your instance allows it (next question)

A script answers with text: it does not hand you a file — for a document, LIA uses document generation or a skill.

## Can a script LIA writes reach the Internet? What does the three-answer question mean?

Only if your administrator enabled the sandbox network, and only in **ReAct mode** (⚡). When a step needs a service no tool covers — checking that an API answers, reading a feed — the short Python script LIA writes may reach it.

**🚪 One door, never a direct line**
• the script goes out through a dedicated proxy, HTTPS only, to the hosts it declares — and nowhere else
• a script that declares no host stays fully offline
• private networks, the server itself and cloud metadata are always refused
• the services you connected with your own API key (web search, answer engine, weather) are reachable without a question — their key never enters the script

**🙋 An unknown host is asked, with three answers**
• **Allow, with the data** — the script may send what LIA gathered this turn (your mails, events…) to that host
• **Allow, without the data** — the script runs, but receives none of it
• **Refuse** — LIA answers with what it already has

The rest of your request then goes on, and your answer is remembered as a permission you can revoke in **Settings › Skill permissions**.

**💡 Good to know**: the question is only asked in a ReAct turn you are watching. Every network run is written to your register before it starts; a routine cannot stop to ask — it refuses and says where to allow the host; some instances refuse unknown hosts outright.

## Do my API keys ever enter the script?

No. The services you connected with your own API key (web search, answer engine, weather) are reachable without a question, and the script only ever sees a **temporary token** valid for that single run: the proxy swaps it for your real key on the host of that connector alone. The key never enters the container, and LIA's own account keys, sign-in tokens and your credentials are never offered to a script at all.

## What is the "Skill permissions" section for?

It shows what a script LIA writes may reach on the network, and lets you take back what you allowed. It only appears once your administrator enabled the sandbox network, and it covers skill commands as well as scripts.

**🌐 Reachable without asking**
• your own connectors (web search, answer engine, weather) — their key travels through the proxy, never into the script
• the hosts your instance allows for everyone

**🙋 Your permissions**
• one line per host you allowed, with the date it was last used
• a switch to change its scope — with or without the data of the turn
• a **Revoke** button: LIA will ask again the next time a script wants that host

The section shows your account's capacity; past it, a new approval holds for its run only. Deleting your account deletes them all.

## Can I allow a host before LIA asks?

Yes, in **Settings › Skill permissions**, under **Allow a host**. Type the bare host name — no https://, no path, no port and no IP address — and choose whether it may receive the data of the conversation turn.

It matters wherever LIA cannot stop to ask you: a routine, or a skill's command in Pipeline mode, reaches only the hosts already listed on that page. The new permission appears with the others, with its date of last use and a **Revoke** button.

Your account holds a limited number of permissions, shown as **Account capacity**. Some instances do not let you add hosts yourself, or refuse every unlisted host without asking — the section then says so.

## Can I see the code a script ran?

The answer never shows it: you get the result, not the plumbing. The code is in the **debug panel**, under **Sandboxed scripts** — what the script was for, its full source, and the beginning of its output or error.

**👀 Who can open it:**
• an administrator, when the debug panel is enabled
• any other user only if the administrator allows users to access the debug panel **and** you turn on **Debug Panel** in your own settings

Hiding the code would protect nothing — the model wrote it — and would make the result impossible to check. A script that reached the network also appears in your **Registers**, as an action LIA performed.

## Does LIA trust what a script returns?

It treats it as data, never as instructions. A script is model-written code running over content that may come from third parties — an e-mail, a web page — so its output is marked as **untrusted** before LIA reads it, exactly like the body of an incoming e-mail. A hostile document cannot turn a script's output into orders.

**When a script fails**, LIA reads the error and may correct its code and run it again, within the turn's small budget of runs. If the sandbox is unavailable on your instance, or the budget is spent, LIA answers with what it already has and says what is missing — it does not make the figure up.

## What are the limits of a script?

Every limit is set by your administrator and stated to LIA in advance, so it never wastes an attempt discovering one:
• a small number of runs per request — a question about a host costs none
• a rate limit per person
• a time and memory budget per run; a network run has its own time budget and a cap on the hosts it may declare
• the Python standard library plus a fixed, published set of libraries for HTTP and parsing, tables, dates and calendars, documents (PDF, Word) and text formats

Most requests never come near these limits: they exist so a script that keeps failing cannot spin in a loop.

## How does an administrator control scripts on a self-hosted server?

**Without a restart**, in **Settings › Administration › Platform capabilities**:
• **Ephemeral Python** — off, LIA never runs a script
• **Sandbox network access** — off, every run stays offline

**In the server configuration** (`.env`):
• `PYTHON_SANDBOX_TOOL_ENABLED=false` removes the tool entirely; the runs per request and the rate limit are configurable too (`PYTHON_SANDBOX_MAX_RUNS_PER_TURN`, `PYTHON_SANDBOX_RATE_LIMIT_CALLS`, `PYTHON_SANDBOX_RATE_LIMIT_WINDOW`)
• the network needs the egress proxy shipped with the skill-sandbox Compose overlay, which turns it on (`PYTHON_SANDBOX_EGRESS_ENABLED=true`); a base install keeps it off. `PYTHON_SANDBOX_EGRESS_HOSTS` lists hosts every account may reach without being asked, `PYTHON_SANDBOX_EGRESS_ASK_ENABLED=false` refuses unknown hosts instead of asking, and `PYTHON_SANDBOX_MAX_GRANTS_PER_USER`, `PYTHON_SANDBOX_MAX_HOSTS_PER_RUN` and `PYTHON_SANDBOX_NETWORK_TIMEOUT_SECONDS` bound the permissions, the hosts of a run and its duration
• scripts need the **container sandbox** (Docker): the in-process mode is refused for code a model wrote, because it only isolates when the API itself runs as root; without the container sandbox, LIA answers without scripts
