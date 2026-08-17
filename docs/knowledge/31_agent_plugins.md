# Agent Plugins

## What is an Agent Plugin?
A plugin is a **portable package** following the open Agent Plugins v1.0.0 standard (agent-plugins.org, steered by AWS, Microsoft, OpenAI, Cursor and Vercel). It bundles, in one directory: a `plugin.json` manifest, **skills** (agentskills.io format) and **MCP servers** (`mcp.json`). The same package installs unchanged in ChatGPT, Codex, Cursor, GitHub Copilot, Kiro, VS Code — and LIA.

## How do I install a plugin?
In **Settings > Plugins**, import a **.zip file** or paste an **https link** to a plugin package. Both paths go through the same hardened pipeline as individual skill imports (bounded extraction, zip-bomb and path-traversal guards, SSRF-validated URL fetch). Quotas are pre-checked before anything is written — an install is never left half-done. Limits: 10 plugins max per user; the plugin's skills and MCP servers count toward the existing per-user quotas (20 skills, 20 MCP servers).

## What does the import report show?
Every install ends with a **per-component report**: each skill and each MCP server is listed as **installed**, **updated**, **skipped** (with a translated reason) or **removed**. Nothing is ever silently dropped. Typical skip reasons: a server type LIA deliberately does not run (`stdio` — never launched on a multi-user server), the legacy `sse` transport, a non-HTTPS endpoint (security policy), or a name already used by one of your existing skills or servers.

## How do plugin components behave after install?
Exactly like their manually-created counterparts: activate or deactivate each skill freely, configure server authentication (API key, bearer, OAuth) in the MCP section, per-server HITL settings apply. Plugin-owned MCP servers show a **"Via plugin"** badge. Plugins never carry secrets — the standard forbids credentials inside packages; you configure authentication after install and it survives plugin updates.

## How do I update a plugin?
Import the new version of the package (same plugin name): kept components are **updated in place** (configured credentials preserved), components the new version dropped are **removed**, and the report says which is which.

## How do I remove a plugin?
In **Settings > Plugins**, uninstall it: every skill and MCP server it brought is removed with it, files included. Deleting a plugin-owned skill or server **individually is refused** (with a pointer to the plugin) — so a plugin can never end up silently amputated. Deleting your account also removes all plugin files from disk.

## What are the security boundaries?
- **No stdio servers**: LIA never launches plugin subprocesses (multi-user server) — such entries are skipped and said.
- **HTTPS-only endpoints**: remote MCP servers must use https; loopback http entries (valid per the standard) are refused by policy, with an explicit reason.
- **No secrets in packages**: headers and environment values in a plugin are treated as visible package data, per the standard.
- **Provenance invariant**: name collisions only resolve within the same provenance — a plugin can never capture one of your manually-created skills, and another plugin can never capture a skill installed by the first.
