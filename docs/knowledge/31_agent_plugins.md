# Agent Plugins

## What is an Agent Plugin?
A plugin is a **portable package** in the open [Agent Plugins v1.0.0 format](https://agent-plugins.org/specification). It bundles a `plugin.json` manifest, **skills** and **MCP servers** (`mcp.json`). LIA supports skills and remote Streamable HTTP MCP servers over HTTPS. Other transports and client-specific extension behavior are outside this support; the import report identifies unsupported components. A package used by another assistant may contain components LIA cannot run.

## How do I install a plugin?
In **Settings > Plugins**, import a **.zip file** or paste an **https link** to a plugin package. Both paths use bounded extraction, zip-bomb and path-traversal guards, and an SSRF-validated URL fetch. Components are processed individually: the report can show loaded and skipped components, with reasons. Read it to check what was installed. Plugin, skill and MCP server quotas are configured by the instance; imported components count toward them.

## What does the import report show?
Every install ends with a **per-component report**: each skill and each MCP server is listed as **installed**, **updated**, **skipped** (with a translated reason) or **removed**. Nothing is ever silently dropped. Typical skip reasons: a server type LIA deliberately does not run (`stdio` — never launched on a multi-user server), the legacy `sse` transport, a non-HTTPS endpoint (security policy), or a name already used by one of your existing skills or servers.

## How do plugin components behave after install?
Like their manually-created counterparts, with one difference: a plugin's skills were written elsewhere, so they run apart (see the security boundaries below). Activate or deactivate each skill freely, configure server authentication (API key, bearer, OAuth) in the MCP section, per-server HITL settings apply. Plugin-owned MCP servers show a **"Via plugin"** badge. Plugins never carry secrets — the standard forbids credentials inside packages; you configure authentication after install and it survives plugin updates.

## How do I update a plugin?
Import the new version of the package (same plugin name): kept components are **updated in place** (configured credentials preserved), components the new version dropped are **removed**, and the report says which is which.

## How do I remove a plugin?
In **Settings > Plugins**, uninstall it: every skill and MCP server it brought is removed with it, files included. Deleting a plugin-owned skill or server **individually is refused** (with a pointer to the plugin) — so a plugin can never end up silently amputated. Deleting your account also removes all plugin files from disk.

## What are the security boundaries?
- **No stdio servers**: LIA never launches plugin subprocesses (multi-user server) — such entries are skipped and said.
- **HTTPS-only endpoints**: remote MCP servers must use https; loopback http entries (valid per the standard) are refused by policy, with an explicit reason.
- **No secrets in packages**: headers and environment values in a plugin are treated as visible package data, per the standard.
- **Plugin skills are third-party**: their instructions run only in an isolated runner with their own files and the ones you attach — never your mailbox, calendar or other connectors — their answers show no interactive frame, remote image or web content, and their commands reach the network only through the sandbox proxy, to permitted hosts.
- **Provenance invariant**: name collisions only resolve within the same provenance — a plugin can never capture one of your manually-created skills, and another plugin can never capture a skill installed by the first.
