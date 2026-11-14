/**
 * A known server fills the create form with PUBLIC facts — and nothing of what
 * the person typed before survives as a secret sent to another host. A server
 * the person already has is recognised by its address, however it was typed.
 */
import { describe, expect, it } from 'vitest';

import {
  applyKnownServer,
  installedKnownKeys,
  knownMCPServerListSchema,
  knownServerIconSrc,
  knownServerOf,
  knownServerScheme,
  mcpServerIdentity,
  type KnownMCPServer,
} from '@/lib/mcp-known-servers';
import { emptyMCPServerForm } from '@/lib/mcp-server-form';

const NOTES: KnownMCPServer = {
  key: 'notes',
  name: 'Notes',
  url: 'https://mcp.notes.example/mcp',
  auth_type: 'oauth2',
  domain_description: "The person's notes.",
  icon: 'notes.svg',
};
const DOCS: KnownMCPServer = {
  key: 'docs',
  name: 'Docs',
  url: 'https://mcp.docs.example/mcp',
  auth_type: 'none',
  domain_description: 'Library documentation.',
  icon: 'docs.png',
};
const FACTS: KnownMCPServer = {
  key: 'facts',
  name: 'Facts',
  url: 'https://api.facts.example/mcp/',
  auth_type: 'api_key',
  domain_description: 'Verified facts.',
  icon: 'facts.png',
  header_name: 'X-API-Key',
};
const CODE: KnownMCPServer = {
  key: 'code',
  name: 'Code',
  url: 'https://api.code.example/mcp/',
  auth_type: 'oauth2',
  domain_description: "The person's repositories.",
  icon: 'code.svg',
  oauth_scopes: 'repo',
  own_oauth_client: true,
};
const CATALOGUE = [CODE, DOCS, FACTS, NOTES];

describe('applyKnownServer', () => {
  it('fills the name, the address, the sign-in method and the description', () => {
    expect(applyKnownServer(emptyMCPServerForm(), NOTES)).toMatchObject({
      name: 'Notes',
      url: 'https://mcp.notes.example/mcp',
      auth_type: 'oauth2',
      domain_description: "The person's notes.",
    });
  });

  it('fills the header a key is read from, and leaves the key itself to the person', () => {
    const form = applyKnownServer(emptyMCPServerForm(), FACTS);

    expect(form).toMatchObject({ auth_type: 'api_key', header_name: 'X-API-Key', api_key: '' });
  });

  it('fills the scopes an OAuth vendor needs, and no client of anyone else', () => {
    expect(applyKnownServer(emptyMCPServerForm(), CODE)).toMatchObject({
      auth_type: 'oauth2',
      oauth_scopes: 'repo',
      oauth_client_id: '',
      oauth_client_secret: '',
    });
  });

  it('drops every secret typed before: none of them was meant for this host', () => {
    const typed = {
      ...emptyMCPServerForm(),
      auth_type: 'api_key' as const,
      api_key: 'secret-key',
      header_name: 'X-Other',
      bearer_token: 'secret-token',
      oauth_client_id: 'client',
      oauth_client_secret: 'client-secret',
      oauth_scopes: 'read write',
    };

    expect(applyKnownServer(typed, DOCS)).toMatchObject({
      auth_type: 'none',
      api_key: '',
      header_name: emptyMCPServerForm().header_name,
      bearer_token: '',
      oauth_client_id: '',
      oauth_client_secret: '',
      oauth_scopes: '',
    });
  });

  it('keeps the choices that are not the server’s: the timeout and who drives it', () => {
    const chosen = { ...emptyMCPServerForm(), timeout_seconds: 90, iterative_mode: true };

    expect(applyKnownServer(chosen, NOTES)).toMatchObject({
      timeout_seconds: 90,
      iterative_mode: true,
    });
  });
});

describe('knownServerOf', () => {
  it('names the known server whose address the form holds', () => {
    expect(knownServerOf(applyKnownServer(emptyMCPServerForm(), NOTES), CATALOGUE)).toBe(NOTES);
  });

  it('answers nothing once the address was edited, or was never a known one', () => {
    const edited = { ...applyKnownServer(emptyMCPServerForm(), NOTES), url: 'https://my.own/mcp' };

    expect(knownServerOf(edited, CATALOGUE)).toBeNull();
    expect(knownServerOf(emptyMCPServerForm(), CATALOGUE)).toBeNull();
  });
});

describe('knownServerScheme and knownServerIconSrc', () => {
  it('tells an OAuth server whose application the person brings from one that registers LIA', () => {
    expect(knownServerScheme(CODE)).toBe('oauth2_own');
    expect(knownServerScheme(NOTES)).toBe('oauth2');
    expect(knownServerScheme(FACTS)).toBe('api_key');
    expect(knownServerScheme(DOCS)).toBe('none');
  });

  it('serves an icon from this application, or none when the catalogue names none', () => {
    expect(knownServerIconSrc(NOTES)).toBe('/mcp-icons/notes.svg');
    expect(knownServerIconSrc({ ...NOTES, icon: undefined })).toBeNull();
  });
});

describe('mcpServerIdentity', () => {
  it.each([
    ['https://MCP.Example.com/mcp', 'https://mcp.example.com/mcp'],
    ['https://mcp.example.com/mcp/', 'https://mcp.example.com/mcp'],
    ['https://mcp.example.com:443/mcp', 'https://mcp.example.com/mcp'],
    ['https://mcp.example.com/mcp?token=secret&groups=a', 'https://mcp.example.com/mcp'],
    ['https://user:pass@mcp.example.com/mcp#part', 'https://mcp.example.com/mcp'],
    ['  https://mcp.example.com/mcp  ', 'https://mcp.example.com/mcp'],
  ])('reads %s as the server %s', (url, identity) => {
    expect(mcpServerIdentity(url)).toBe(identity);
  });

  it('keeps what does tell two servers apart: a path, a port of its own', () => {
    expect(mcpServerIdentity('https://geo.example/carto/mcp')).not.toBe(
      mcpServerIdentity('https://geo.example/context/mcp')
    );
    expect(mcpServerIdentity('https://mcp.example.com:8443/mcp')).toBe(
      'https://mcp.example.com:8443/mcp'
    );
  });

  it('answers nothing for what is not an address', () => {
    expect(mcpServerIdentity('not an address')).toBeNull();
    expect(mcpServerIdentity('')).toBeNull();
  });
});

describe('installedKnownKeys', () => {
  it('names the known servers the person has, however their address was typed', () => {
    const installed = installedKnownKeys(CATALOGUE, [
      { url: 'https://api.facts.example/mcp?key=typed-by-the-person' },
      { url: 'https://MCP.NOTES.example/mcp/' },
      { url: 'https://my.own/mcp' },
    ]);

    expect([...installed].sort()).toEqual(['facts', 'notes']);
  });

  it('names none when the person has none, or nothing readable', () => {
    expect(installedKnownKeys(CATALOGUE, []).size).toBe(0);
    expect(installedKnownKeys(CATALOGUE, [{ url: 'garbage' }]).size).toBe(0);
  });
});

describe('knownMCPServerListSchema', () => {
  it('reads what the API publishes, with the instance’s OAuth callback', () => {
    const parsed = knownMCPServerListSchema.parse({
      servers: CATALOGUE,
      oauth_redirect_uri: 'https://lia.example/api/v1/mcp/servers/oauth/callback',
    });

    expect(parsed.servers).toEqual(CATALOGUE);
    expect(parsed.oauth_redirect_uri).toBe('https://lia.example/api/v1/mcp/servers/oauth/callback');
  });

  it.each([
    ['a header on a server that reads no key', { ...DOCS, header_name: 'X-API-Key' }],
    ['scopes on a server that signs in no one', { ...FACTS, oauth_scopes: 'repo' }],
    ['an own application for a key', { ...FACTS, own_oauth_client: true }],
    ['an icon fetched from elsewhere', { ...DOCS, icon: 'https://cdn.example/docs.png' }],
    ['a scheme the form does not know', { ...DOCS, auth_type: 'mtls' }],
  ])('refuses %s', (_label, entry) => {
    expect(knownMCPServerListSchema.safeParse({ servers: [entry] }).success).toBe(false);
  });
});
