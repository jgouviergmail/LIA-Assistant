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
Extend LIA's capabilities without limits by connecting any MCP-compatible service.

## How do I add an MCP server?
Add a server in a few steps:

**⚙️ Access:**
Settings → "*MCP Servers*" section → **Add** button

**📝 Configuration:**
1. **Name**: descriptive name (e.g., "HuggingFace Hub")
2. **URL**: HTTP(S) endpoint of the MCP server
3. **Description** (optional): describe what the server does so LIA knows when to use it
4. **Authentication**: choose the type (none, API key, bearer token, OAuth 2.1)
5. **Timeout**: maximum call duration (5-120 seconds)

6. **Iterative mode** (optional): enable for servers with complex APIs that require multi-step interaction (e.g., Excalidraw). When enabled, a dedicated ReAct AI agent reads the server documentation first, then calls tools step by step with correct parameters. The planner sees a single "task" tool instead of individual tools. Uses more tokens but produces significantly better results for complex multi-step workflows.

**🔗 After creation:**
Click **Test Connection** to verify the server is reachable and discover available tools.

## What authentication types are supported?
Four authentication types are available:

**🔓 None:**
For public servers or internal network services

**🔑 API Key:**
• Sent in a customizable HTTP header
• Default header: X-API-Key
• Ideal for simple APIs (HuggingFace, etc.)

**🎫 Bearer Token:**
• Token sent in the Authorization: Bearer header
• For APIs using static access tokens

**🔐 OAuth 2.1:**
• Full authorization flow with PKCE
• Optional Client ID and Client Secret (pre-registration)
• Automatic refresh of expired tokens
• For APIs requiring user authorization (GitHub, Slack...)

**💡 Security:**
All authentication credentials are **encrypted** server-side.

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
MCP tools are used **automatically** by LIA when relevant:

**🧠 Smart selection:**
• LIA analyzes your question and identifies relevant tools
• The **server description** helps LIA choose the right MCP server
• MCP tools are selected alongside native tools (Google, weather, etc.)

**📊 Result display:**
• MCP results appear as **visual cards** in the conversation
• Each card shows the source server and tool name
• Content can be text or formatted JSON

**💡 Tips:**
• Write a good **server description** to guide LIA
• Test the connection to ensure tools are properly discovered
• You can **enable/disable** a server via the toggle without deleting it
• A server connected with your own account (OAuth, personal token) tells LIA so: "my repos", "my accounts" resolve to that account, with no username to provide

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

## What is iterative mode and when should I enable it?
Iterative mode changes how LIA interacts with an MCP server:

**🔄 Standard mode (default):**
• LIA's planner sees all individual tools from the server
• It generates all parameters at once before calling tools
• Works well for simple APIs with independent tools

**🤖 Iterative mode (ReAct agent):**
• LIA's planner sees a single "task" tool per server
• A dedicated ReAct AI agent takes over and interacts with the server step by step
• The agent reads the server's documentation first (`read_me`), then plans and executes tools iteratively with error recovery

**💬 Behaviour by chat mode:**
• In the **standard** chat mode, the planner delegates to the dedicated ReAct sub-agent described above.
• In the **autonomous (⚡ ReAct)** chat mode, LIA already reasons step by step, so it uses the server's individual tools **directly** (no nested agent) and picks the right one by description — your iterative servers work the same as in standard mode. Servers with interactive widgets (like Excalidraw) keep their dedicated agent even here. Admins can force the task tool everywhere with `REACT_MCP_EXPAND_ITERATIVE_ENABLED=false`.

**✅ Enable iterative mode when:**
• The server has a complex API requiring tools to be called in sequence
• Tools depend on each other (output of one is input for the next)
• The server provides a `read_me` documentation tool
• Example: Excalidraw (must read element format before creating diagrams)

**❌ Keep standard mode when:**
• Tools are simple and independent (e.g., a search tool)
• The API has few parameters and no complex workflows

**⚠️ Requirements:**
• The administrator must enable `MCP_REACT_ENABLED=true` globally
• Iterative mode uses more tokens per request (multiple LLM calls for the ReAct loop)
• Iterative tools get an extended execution timeout (120s minimum vs. 60s for regular tools) to accommodate multi-step ReAct iterations

**🤖 Smart AI selection:**
• MCP servers with interactive widgets (like Excalidraw) automatically use a more powerful AI model
• Regular MCP servers use a faster, more cost-efficient model
• The administrator can configure both models in the LLM Config panel

**🩺 Widget durability and diagnostics:**
• MCP App widgets are persisted with the conversation — they reopen after a reload or on another device
• A widget that never starts shows an actionable notice (explanation, Retry) with the technical failure detail relayed from inside the frame, so a report from any device names the culprit
• Requests whose analyzed domain is an MCP surface (e.g. a drawing request when Excalidraw is connected) route directly to that server — the skill detector can no longer divert them

**⚙️ How to enable:**
Settings → MCP Servers → Edit your server → Toggle "Iterative mode (ReAct agent)"

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
LIA speaks **both generations of the MCP protocol**:

**🔌 Supported revisions:**
• The **new stateless revision (2026)** — used by new-generation servers
• The **classic handshake** — used by every earlier server
• The right one is chosen **automatically per server**: existing servers keep working with no action on your side, and new-generation servers connect too

**🧭 Clear diagnostics:**
If a server requires a revision LIA does not speak, the connection test shows a clear explanation instead of a technical error.

**🔐 Hardened OAuth:**
• The authorization server's identity is verified before your authorization code is used
• Stored client credentials are never sent to a different authorization server than the one that issued them — LIA re-registers automatically instead
• Declining the consent screen brings you back to your settings with an informational message — declining is a choice, not an error

**🧩 Reading what a server declares:**
Since v1.38.4 the alignment reaches the second half of the protocol. LIA reads tool declarations across the full latitude the 2026-07-28 revision allows: optional types, nested structures, internal references and closed sets. A server describing its parameters with the standard's more advanced forms is now read in full, where some of those forms used to make its tools disappear without a word.

## Why do some MCP tools have a readable name, and why do some ask for confirmation?

**🏷️ The displayed name:**
The protocol lets a server publish a **readable name** alongside a tool's technical identifier. When it does, that is what appears in the discovered-tools list — *Financial accounts* rather than `accounts__list_financial_accounts`. The technical identifier stays beside it: that is the one found again in logs and in rules.

**🛡️ The confirmation:**
A server can also declare that a tool is **destructive**. LIA believes that declaration — but in one direction only:
• A tool announced as destructive asks for confirmation **even if** confirmation is switched off for that server
• A server claiming to be harmless never earns a free pass
• This is what the specification recommends: a third-party server's annotations may strengthen a protection, never lift one
