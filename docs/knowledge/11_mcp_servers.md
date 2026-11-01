# MCP Servers

## What is an MCP server?
An MCP (Model Context Protocol) server is an **external service** that exposes tools usable by LIA:

**🔌 How it works:**
• MCP is an open standard (Anthropic) for connecting tools to an AI assistant
• Each server exposes one or more **tools** (functions) that LIA can call
• MCP tools integrate seamlessly alongside native tools (Google, weather, etc.)

**📌 Example MCP servers:**
• **HuggingFace Hub**: search ML models
• **GitHub**: manage repositories and issues
• **Slack**: send messages
• **Database**: SQL queries

**💡 Benefit:**
Extend your account's tools with supported MCP services, within the instance's configured limits.

## How do I add an MCP server?
Add a server in a few steps:

**⚙️ Access:**
Settings → "*MCP Servers*" section → **Add** button

**📝 Configuration:**
1. **Name**: descriptive name (e.g., "HuggingFace Hub")
2. **URL**: HTTPS Streamable HTTP endpoint of the MCP server
3. **Description** (optional): describe what the server does so LIA knows when to use it
4. **Authentication**: choose the type (none, API key, bearer token, OAuth 2.1)
5. **Timeout**: maximum call duration (5-120 seconds)

6. **Who drives it**: LIA uses its tools directly, a dedicated agent in Pipeline with the tools directly in ReAct, or a dedicated agent in both modes (see *Who drives an MCP server*).
7. **Confirmation**: like your strategy, always ask, or follow the server's declarations (see *How do I decide when LIA asks before using an MCP tool?*).

**🔗 After creation:**
Click **Test Connection** to verify the server is reachable and discover available tools.

## What authentication types are supported?
Four authentication types are available:

**🔓 None:**
For public servers that do not require authentication. Personal connections still undergo the HTTPS and destination-address checks.

**🔑 API Key:**
• Sent in a customizable HTTP header
• Default header: X-API-Key
• Ideal for simple APIs (HuggingFace, etc.)

**🎫 Bearer Token:**
• Token sent in the Authorization: Bearer header
• For APIs using static access tokens

**🔐 OAuth 2.1:**
• OAuth authorization with PKCE S256 when supported by the server
• Optional Client ID and Client Secret (pre-registration)
• Automatic refresh of expired tokens
• For APIs requiring user authorization (GitHub, Slack...)

**💡 Security:**
Configured credentials are **encrypted before database storage** and decrypted when needed to authenticate to the chosen server. Choose that server carefully; encryption at rest does not make its operator trustworthy.

## How do I test the connection to an MCP server?
You can test a server in two ways:

**⚡ From the list:**
• Hover over the server → click the **lightning bolt** icon
• Results appear in a popup window

**⚡ From the edit form:**
• Open the server settings
• Click **Test Connection**
• Results appear below the button

**✅ On success:**
• The number of discovered tools is displayed
• A detailed tool list (name + description) appears
• Status changes to "Active"

**❌ On failure:**
• A detailed error message is shown
• Status changes to "Error"
• Check the URL, authentication, and server availability

## How do I configure OAuth 2.1 for an MCP server?
OAuth setup is a two-step process:

**📝 Step 1 — Configuration:**
1. Select auth type "*OAuth 2.1*"
2. Enter **Client ID** and **Client Secret** if required by the provider (optional)
3. Add the required **OAuth Scopes** (e.g., repo project read:org for GitHub) — check the provider's documentation
4. Save the server

**🔗 Step 2 — Authorization:**
1. A "*Connect OAuth*" button appears on the server card
2. Click it → you're redirected to the provider
3. Grant access → automatic return to LIA
4. Status changes to "Active" ✅

**🔄 Token refresh:**
• Tokens are refreshed automatically
• If refresh fails, status reverts to "Authentication required"
• Click "Connect OAuth" again to re-authorize

## How does LIA use MCP tools in a conversation?

LIA selects MCP tools alongside native tools using your question and the server's description. Write that description carefully, test discovery, and use the server switch to pause it without deleting its configuration.

Results appear as cards that preserve lists, structured objects and simple values. They identify the server and tool, plus the method and source URL when supplied; an absent field is never invented. Opening stored detail makes no new call.

A server rate limit starts a bounded cooldown shared across calls to that server, so repeated requests do not hammer it. A server connected to your personal account tells LIA which account “my repositories” or “my accounts” means.

## What are OAuth scopes and why are they important?
OAuth scopes define the **permissions** requested during authorization:

**🔐 Why scopes matter:**
• Without scopes, the OAuth token has **minimal permissions**
• Tool discovery (list_tools) works without scopes (metadata only)
• But tool calls (call_tool) return **403 Forbidden** without the right scopes

**📋 Common scopes by provider:**
• **GitHub**: repo project read:org
• **Slack**: channels:read chat:write
• Check your provider's documentation for required scopes

**⚙️ How to configure:**
1. Edit your MCP server
2. Fill in the "*OAuth Scopes*" field (space-separated)
3. Save, then click "*Connect OAuth*" again to re-authorize with the new scopes

**💡 Tip:**
If your MCP tools return 403 errors after a successful OAuth connection, it's likely a missing scopes issue.

## How does automatic description generation work?
LIA can **auto-generate** a domain description for your MCP servers:

**🤖 Automatic generation:**
• During **connection testing**, if no description is set, an LLM analyzes the discovered tools
• It generates an intelligent description that helps LIA understand **when** to use this server
• The description is optimized for query routing (selecting the right server based on the question)

**✨ Manual regeneration:**
• In edit mode, click the **Generate description** button (sparkle icon) next to the description field
• This overwrites the existing description with a fresh tool analysis
• Requires having tested the connection first (to discover tools)

**💡 Tips:**
• You can always write a **manual** description that won't be overwritten by the connection test
• Auto-generation is a good starting point that you can refine afterwards
• Generation knows whether the server is authenticated with your account: it then describes capabilities over your data, never a "public-only" access

## Who drives an MCP server: tools used directly or a dedicated agent?

It is one choice on each server's form, with three options:

**🔧 LIA uses its tools directly:** LIA plans with the server's individual tools and fills in their parameters at once — ideal for simple, independent tools such as a search.

**🔄 A dedicated agent in Pipeline, the tools directly in ⚡ ReAct:** in Pipeline, LIA hands the request to a dedicated agent that works with that server step by step — it reads the documentation the server offers, calls a tool, reads the result, chooses the next one and recovers from an error, within a bounded number of steps and time; in ReAct, LIA already works step by step and uses the server's tools directly.

**🤖 A dedicated agent in both modes:** the agent works in ReAct too — useful when the tools must be called in sequence or the server asks to read its documentation first (a drawing server, for instance).

**🛡️ Confirmation with a dedicated agent:** LIA asks once before handing it a task, as soon as one of its tools would need your approval; your answer covers the agent's calls for that task, which runs to completion. In ReAct, LIA may give the agent several tasks in a row: one question each.

**💡 Good to know:** a dedicated agent makes several model calls per request, so it costs more and does not guarantee success. Servers that draw interactive widgets keep their agent in ReAct. Your administrator can switch dedicated agents off for the whole instance.

**🤖 Which model:** servers with interactive widgets use a more capable model, the others a faster and cheaper one; the administrator sets both in **LLM Configuration**.

**🩺 Widgets:** an interactive widget is kept with the conversation and reopens after a reload or on another device. A widget that never starts shows a notice with an explanation, a **Retry** button and the technical detail, so a report from any device names the culprit. With unchanged content, interactive cards and widgets retain their state during automatic display updates.

**⚙️ For administrators:** dedicated agents are available unless `MCP_REACT_ENABLED=false`; `REACT_MCP_EXPAND_ITERATIVE_ENABLED` is the default ReAct shape of a server whose owner never chose one, and the rule of the administrator's own iterative servers.

## How do I generate Excalidraw diagrams and schemas?
LIA can create architecture diagrams, workflows, org charts and more using the Excalidraw MCP server:

**📝 How to use:**
Simply describe what you want in natural language:
• "*Create a client-server architecture with a database*"
• "*Draw a 5-step onboarding workflow*"
• "*Make an org chart for a marketing team*"

**⚙️ How it works (3-step process):**
1. LIA generates a **structured intent** describing components and relationships
2. A first dedicated LLM call creates the **shapes** (boxes, circles, text)
3. A second LLM call adds the **arrows** (connections between shapes)

**💡 Tips for best results:**
• Describe the **components** you want (servers, databases, users...)
• Specify **relationships** between them (connects to, sends data to...)
• Mention the **layout type** if desired (flowchart, hierarchy, network...)

**⚠️ Prerequisite:**
The Excalidraw MCP server must be configured and active in your MCP server settings.

## Which versions of the MCP protocol does LIA support?
LIA supports the stateless MCP revision and compatible classic handshakes:

**🔌 Supported revisions:**
• The **new stateless revision (2026)** — used by new-generation servers
• The **classic handshake** for compatible earlier revisions
• Negotiation selects the supported exchange per server. This does not guarantee compatibility with every server or extension.

**🧭 Clear diagnostics:**
If a server requires a revision LIA does not speak, the connection test shows a clear explanation instead of a technical error.

**🔐 Hardened OAuth:**
• The authorization server's identity is verified before your authorization code is used
• Stored client credentials are never sent to a different authorization server than the one that issued them — LIA re-registers automatically instead
• Declining the consent screen brings you back to your settings with an informational message — declining is a choice, not an error

**🧩 Reading what a server declares:**
LIA shares one interpretation between the model's tool signature and the planner's catalogue. It handles supported unions, references, closed choices and constraints, and preserves declared constraints where provider converters are more limited. This does not implement every JSON Schema keyword or every server-specific behavior. The server remains responsible for validating its inputs.

## Why do some MCP tools have a readable name, and why do some ask for confirmation?

**🏷️ The displayed name:**
The protocol lets a server publish a **readable name** alongside a tool's technical identifier. When it does, that is what appears in the discovered-tools list — *Financial accounts* rather than `accounts__list_financial_accounts`. The technical identifier stays beside it: that is the one found again in logs and in rules.

**🛡️ The confirmation:**
A server can also declare that a tool is **destructive**. LIA believes that declaration in one direction only: a server claiming to be harmless never earns a free pass — a third-party server's annotations may strengthen a protection, never lift one. Only **your** choice can lift a question: “Never ask” for that one tool, bound to what it declares; if the server changes that declaration, your choice is suspended; the server and account rules apply until you choose anew.

The rule is the same for every server — yours or your administrator's — and in both modes:
• **A tool asks for confirmation** according to its own choice, then its server's, then your strategy, then the instance's default — and, when it follows the declarations, when the server announces it as modifying or destructive
• **Tools used directly, in ⚡ ReAct mode**: LIA asks before the tool runs, then carries on
• **Tools used directly, in Pipeline mode**: the task does everything it can; each action awaiting your approval is prepared, never performed, and shown after the task, one card at a time. A step that comes after such an action waits for your answer: if it needs the action's result, it runs on the real result once you approve — refused, it does not run and LIA says so; otherwise it runs either way, like the updated list you asked for. With the outcome, LIA tells you what else the task did
• **A dedicated agent, in both modes**: LIA asks once before handing it a task, as soon as one of its tools would need your approval; your answer covers its calls and the task runs to completion
• **In a scheduled action**: nobody is there to answer, so such a tool — or a dedicated agent's whole task — is refused, unless the action's form confirms that server in advance (see *Scheduled actions*); a tool set to “Never ask” runs. An assistant can never tick that box for you
• **Afterwards**: every action performed appears in the **Actions** register, named after its server

## How do I decide when LIA asks before using an MCP tool?

In **Settings › MCP Servers**, at three levels, from the most general to the most precise:
• **🌐 Your strategy**: “Always ask” before every MCP tool, or “Follow its declarations” — LIA then asks only for the tools the server announces as modifying or deleting. An account that never chose follows the instance's default
• **🖥️ Each server**: like your strategy, always, or according to its declarations
• **🔧 Each tool**: “Always ask” or “Never ask” — the latter, shown in red, means LIA uses the tool without asking you, as if you had said yes; the act is still recorded in the **Actions** register. You choose it in **What it will do** or in the server's form

The **What it will do** button shows, mode by mode and tool by tool, whether LIA will ask, when (before the call, or before a dedicated agent's task) and why. Before any change that would make LIA ask less, the page lists what LIA would no longer ask about: nothing is locked, you stay responsible for your settings.

## Can I set these confirmations by talking to LIA?

Yes, but only so that LIA asks **more**. “Always ask me before using an MCP tool”, “… before this server” or “… before this tool” work: your strategy changes at once, a server or its tools go through a card you confirm. “Stop asking me” is refused, and LIA points you to **Settings › MCP Servers**, where the page lists what would change.

**🛡️ Why:** an instruction hidden in content LIA reads — an e-mail, a web page, a document — must never be able to switch a confirmation off.

## How does LIA check what an MCP tool can do?

LIA uses the schemas and result contracts actually discovered, with their identity, age and fingerprint. A readable name or alias does not replace the offered server and tool identity. Personal and administrator servers remain separate. Structured results can be used where their contract permits; arbitrary schemas or external data do not become internal truth. Missing or uncertain contracts stay declared as such, with applicable confirmation protections.

## Why does a reply sometimes wait for one of my MCP servers, and what does the notice mean?

LIA keeps what each of your MCP servers offers (its tools) and reuses it from one message to the next, so a message usually waits for none of them — even right after a restart, and on any of the instance's workers.

**⏳ When a server must be asked again** (the first time, or after you changed its settings), LIA prepares your servers **in parallel**:
• If one takes a while, a small notice names it: *“… is taking a while to get ready”*. Turning the server off in Settings shortens the wait, at the cost of its tools
• If it is still not ready after a short wait, your message is answered **without that server's tools**, and the notice says so. The server keeps getting ready: it is there for your next message
• A server that changes what it offers is re-read in the background while the last known version keeps serving

**🛡️ Before using a tool**, when what it keeps of the server is no longer fresh, LIA checks that the server still offers it in the same form. If the server withdrew the tool, or changed its parameters in a way the call no longer fits, the call is **not sent** and LIA tells you.
