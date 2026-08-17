# Agent Plugins Integration (agent-plugins.org v1.0.0)

**Status**: implemented (ADR-225) · **Domain**: `apps/api/src/domains/plugins/` · **Since**: v1.31.x

LIA is a conformant client of the [Agent Plugins specification v1.0.0](https://agent-plugins.org/specification) under the incremental-adoption profile (§11.2): **skills + streamable-http MCP servers**. A plugin published for ChatGPT, Codex, Cursor, GitHub Copilot, Kiro or VS Code installs into LIA without adaptation.

See [ADR-225](../architecture/ADR-225-Standard-Agent-Plugins-v1.md) for the conformance positioning, the documented deviations and the owner arbitrations.

## Package model

A plugin is a directory (uploaded as a `.zip`, flat or under a single wrapper directory) with:

| Location      | Component                | Handled by                                     |
| ------------- | ------------------------ | ---------------------------------------------- |
| `plugin.json` | Manifest (required)      | `domains/plugins/manifest.py` (closed schema)  |
| `skills/*/SKILL.md` | Agent Skills (agentskills.io) | The existing skills pipeline via `SkillImportService.import_directory` |
| `mcp.json`    | MCP servers              | `domains/plugins/mcp_config.py` → `user_mcp`   |

Validation is exhaustively spec-driven: closed manifest with the two non-fatal exceptions of §5.2 (unknown top-level field, non-object `extensions` — reported and ignored), closed server variants mirroring the official `mcp.schema.json`, plus the semantic rules the JSON schema deliberately leaves to the spec text (URL semantics, header validity including case-insensitive duplicates, stdio `cwd` forms, reserved `env` names). Rejection reasons are a closed taxonomy (`PluginIssueCode`), translated client-side — never string-matched.

## Pipeline

`PluginImportService.import_upload` (all import paths converge here):

1. size guard → staged extraction with S3 guards (zip bomb, member count, zip-slip, POSIX-safe prefix matching);
2. manifest validation — fatal violation rejects the plugin with nothing created (§5.2);
3. component discovery (immediate children of `skills/` only — §7.1; `mcp.json` at the root only);
4. **global quota pre-check before any write** (plugins, skills, MCP servers — no half-done install);
5. per-skill import through the existing hardened pipeline (S1–S5, atomic per-skill swap with rollback), carrying the plugin provenance into the DB row atomically;
6. per-server creation/update in `user_mcp` (name `"<plugin>:<key>"`, non-secret `extra_headers`, provenance) — connection failures are non-fatal (§7.2.2 r.5);
7. update flow: components dropped by the new version are removed (keyed on package contents, never on install success — a failed re-import keeps its retained previous version);
8. plugin root persisted under `data/plugins/users/{user_id}/{name}/`;
9. **exhaustive per-component report** (installed / updated / skipped + reason / removed) — the §11.3 SHOULD-report and LIA's anti-false-success doctrine.

Failure boundaries follow §11.3: an invalid skill or server entry is skipped and reported, a config-level `mcp.json` violation disables MCP for the plugin only, unsupported transports (`stdio`, `sse`) and policy-refused endpoints (loopback HTTP) are skipped with distinct reason codes.

## Provenance invariant

A name collision is allowed **only within the same provenance**: a plugin import never captures a manual skill, a manual import never captures a plugin's skill, plugin P updating its own skill stays an upsert (enforced in `_check_user_conflict` + defense-in-depth in `create_skill_for_import`). Individual deletion of a plugin-owned component is refused (`raise_plugin_component_locked`) server-side on both the skills DELETE endpoint and `UserMCPServerService.delete_server`; the group uninstall passes `allow_plugin_owned=True`. `ON DELETE SET NULL` on the provenance FK is the raw-SQL safety net: components degrade to manual ones instead of cascading user data away.

## Persistence

- `user_plugins` (one row per installed plugin per user, unique `(user_id, name)`, full manifest JSONB, spec version) — migration `3b4c5d6e7f8a`;
- nullable `plugin_id` on `skills` and `user_mcp_servers`;
- `user_mcp_servers.extra_headers` (non-secret fixed headers from `mcp.json` §7.2.1) — applied as httpx client default headers in the ephemeral pool, so auth-generated headers keep precedence on name collision, exactly the spec's rule.

## API & frontend

`POST /plugins/import` (upload) · `POST /plugins/import-from-url` (reuses the skills SSRF-hardened fetch and its per-user rate limit) · `GET /plugins` (listing with component names) · `DELETE /plugins/{id}` (group uninstall). Feature flag `PLUGINS_ENABLED` (requires `SKILLS_ENABLED`).

Frontend: `PluginsSettings` section (import, listing with component-count badges, import-report dialog, uninstall confirmation), registered in the settings deep-link tokens and search index; `via plugin` badge on plugin-owned MCP servers; delete guards on plugin-owned components show an informative toast pointing to the plugin (guard in the handler, never a disabled attribute — keyboard focus is preserved). Six locales, strict key parity.

## Settings

| Env var | Default | Purpose |
| ------- | ------- | ------- |
| `PLUGINS_ENABLED` | `true` | Feature flag (router mount + settings section) |
| `PLUGINS_USERS_PATH` | `data/plugins/users` | Per-user plugin roots |
| `PLUGINS_MAX_PER_USER` | `10` | Installed-plugin quota |
| `PLUGINS_MAX_FILE_SIZE_KB` | `512` | Upload size cap |
| `PLUGINS_ZIP_MAX_DECOMPRESSED_KB` | `8192` | Zip-bomb guard |
| `PLUGINS_ZIP_MAX_FILES` | `256` | Zip-bomb guard |

Existing quotas apply to imported components (`SKILLS_MAX_PER_USER`, `MCP_USER_MAX_SERVERS_PER_USER`) and are pre-checked globally before any write.
