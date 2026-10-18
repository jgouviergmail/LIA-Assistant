# Agent Plugins

## What is an Agent Plugin?
A plugin is a **portable package** in the open [Agent Plugins v1.0.0 format](https://agent-plugins.org/specification). It bundles a `plugin.json` manifest, **skills** and **MCP servers** (`mcp.json`). LIA supports skills and remote Streamable HTTP MCP servers over HTTPS. Other transports and client-specific extension behavior are outside this support; the import report identifies unsupported components. A package used by another assistant may contain components LIA cannot run.

## How do I install a plugin?
In **Settings › Features › Extensions & Data › Plugins**, import a **.zip file** or paste an **https link** to a plugin package. Both paths use bounded extraction, zip-bomb and path-traversal guards, and an SSRF-validated URL fetch. Components are processed individually: the report can show loaded and skipped components, with reasons. Read it to check what was installed. Plugin, skill and MCP server quotas are configured by the instance; imported components count toward them.

## What does the import report show?
Every install ends with a **per-component report**: each skill and each MCP server is listed as **installed**, **updated**, **skipped** (with a translated reason) or **removed**. Nothing is ever silently dropped. Typical skip reasons: a server type LIA deliberately does not run (`stdio` — never launched on a multi-user server), the legacy `sse` transport, a non-HTTPS endpoint (security policy), or a name already used by one of your existing skills or servers.

## How do a plugin's skills and servers behave once installed?

Like the ones you add yourself, with their origin shown:
• its **MCP servers** appear in **MCP Servers** with a **Via plugin** badge. Switch each one on or off and set its authentication there (API key, bearer token, OAuth): a package never carries credentials, so that step is yours — and it survives the plugin's updates. Your confirmation settings for each server apply as usual
• its **skills** appear in Skills with a **Plugin** badge. Turn them on or off freely; they were written elsewhere, so they run apart from your connectors

One thing is refused: deleting a single component. A plugin leaves whole — uninstall it from **Plugins** and everything it brought goes with it.

## How do I update a plugin?
Import the new version of the package (same plugin name): kept components are **updated in place** (configured credentials preserved), components the new version dropped are **removed**, and the report says which is which.

## How do I remove a plugin?
In **Settings › Features › Extensions & Data › Plugins**, uninstall it: every skill and MCP server it brought is removed with it, files included. Deleting a plugin-owned skill or server **individually is refused** (with a pointer to the plugin) — so a plugin can never end up silently amputated. Deleting your account also removes all plugin files from disk.

## What can a plugin never do?

Whatever a package contains, LIA holds the same lines. A plugin cannot:
• **launch a program on your server**: local (stdio) servers are skipped and reported, because the server is shared
• **reach a server without HTTPS**: remote servers must use https — even a local http address the standard allows is refused
• **bring secrets**: anything inside a package is treated as visible data; you enter credentials yourself after installing
• **open your data to its skills**: they run apart, never with your mailbox, calendar or connectors, and their scripts and commands run in the sandbox
• **take over a name**: it cannot replace one of your own skills or servers, nor one brought by another plugin — a clash is skipped and reported
• **exceed your instance's limits**: quotas are checked before anything is written, so an installation is never left half-done
