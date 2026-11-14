import { emptyMCPServerForm, type MCPServerFormState } from '@/lib/mcp-server-form';
import { z } from '@/lib/zod';

/**
 * The known MCP servers (`GET /mcp/servers/known`): what a person may add
 * without typing an address. Public facts only — a vendor's own endpoint, the
 * way it authenticates, what it is about, its icon. The API owns the list
 * (`infrastructure/mcp/known_servers.py`); this module is how the gallery of
 * the settings and the create form read it, in the settings dialog and in the
 * chat's private form alike.
 */

/** Where the application serves the vendors' icons (`public/mcp-icons/`). */
export const KNOWN_MCP_ICON_PATH = '/mcp-icons/';

export const knownMCPServerSchema = z
  .object({
    key: z.string().min(1),
    name: z.string().min(1).max(100),
    url: z.string().startsWith('https://').max(2048),
    // A key or a token is the person's to type: the catalogue only names the scheme.
    auth_type: z.enum(['none', 'oauth2', 'api_key', 'bearer']),
    domain_description: z.string().max(500),
    // A file of this application, never an address: no icon is fetched from a vendor.
    icon: z
      .string()
      .regex(/^[a-z][a-z0-9_]{0,31}\.(svg|png)$/)
      .optional(),
    header_name: z.string().min(1).max(100).nullable().optional(),
    oauth_scopes: z.string().max(500).nullable().optional(),
    own_oauth_client: z.boolean().optional(),
  })
  // The API holds a header to a key, scopes and an own application to OAuth (its
  // catalogue test guards it): a body saying otherwise is not that catalogue, and
  // is not read rather than prefilled half-wrong.
  .refine(server => server.auth_type === 'api_key' || !server.header_name)
  .refine(
    server => server.auth_type === 'oauth2' || (!server.oauth_scopes && !server.own_oauth_client)
  );
export const knownMCPServerListSchema = z.object({
  servers: z.array(knownMCPServerSchema),
  oauth_redirect_uri: z.string().startsWith('http').max(2048).nullable().optional(),
});

export type KnownMCPServer = z.infer<typeof knownMCPServerSchema>;

/** What the person must do once a known server's form is saved, by sign-in scheme. */
export type KnownServerScheme = 'none' | 'oauth2' | 'oauth2_own' | 'api_key' | 'bearer';

export function knownServerScheme(server: KnownMCPServer): KnownServerScheme {
  return server.auth_type === 'oauth2' && server.own_oauth_client ? 'oauth2_own' : server.auth_type;
}

/** The vendor's icon, served by this application; `null` when the catalogue names none. */
export function knownServerIconSrc(server: KnownMCPServer): string | null {
  return server.icon ? `${KNOWN_MCP_ICON_PATH}${server.icon}` : null;
}

/**
 * The create form once a known server was picked.
 *
 * Every credential field is emptied: whatever was typed before was typed for
 * another host, and a client id left behind would be sent to this one. What is
 * not the server's — the timeout, who drives it — stays the person's. A key's
 * header and the scopes an OAuth vendor needs come from the catalogue; the key
 * itself is the person's to type.
 */
export function applyKnownServer(
  form: MCPServerFormState,
  server: KnownMCPServer
): MCPServerFormState {
  const empty = emptyMCPServerForm();
  return {
    ...empty,
    timeout_seconds: form.timeout_seconds,
    iterative_mode: form.iterative_mode,
    name: server.name,
    url: server.url,
    auth_type: server.auth_type,
    header_name: server.header_name ?? empty.header_name,
    oauth_scopes: server.oauth_scopes ?? '',
    domain_description: server.domain_description,
  };
}

/** The known server whose address the form holds, if it still holds one. */
export function knownServerOf(
  form: MCPServerFormState,
  servers: readonly KnownMCPServer[]
): KnownMCPServer | null {
  return servers.find(server => server.url === form.url) ?? null;
}

/**
 * Which server an address names: scheme and host in lower case, no default
 * port, no credentials, no query or fragment, no trailing slash. A server
 * added with its key in the query (`?token=…`) or with a trailing slash is the
 * same server as its catalogue entry; `null` for what is not an address.
 */
export function mcpServerIdentity(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url.trim());
  } catch {
    return null;
  }
  const path = parsed.pathname.replace(/\/+$/, '');
  // `host` drops the scheme's default port and keeps any other one.
  return `${parsed.protocol}//${parsed.host.toLowerCase()}${path}`;
}

/** The keys of the known servers the person already has, matched by address. */
export function installedKnownKeys(
  servers: readonly KnownMCPServer[],
  installed: readonly { url: string }[]
): ReadonlySet<string> {
  const addresses = new Set(installed.map(server => mcpServerIdentity(server.url)).filter(Boolean));
  return new Set(
    servers.filter(server => addresses.has(mcpServerIdentity(server.url))).map(server => server.key)
  );
}
