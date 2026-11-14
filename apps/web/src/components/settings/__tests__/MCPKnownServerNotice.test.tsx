/**
 * A create form opened from a known server says which server it is and what to
 * do next — in the settings dialog and in the chat's private form alike, since
 * both draw `MCPServerFormFields`. The known server is read off the address the
 * form holds: an address edited by hand is no known server any more.
 */
import { useState } from 'react';
import { createInstance } from 'i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { applyKnownServer, type KnownMCPServer } from '@/lib/mcp-known-servers';
import {
  emptyMCPServerForm,
  type MCPServerFormSource,
  type MCPServerFormState,
} from '@/lib/mcp-server-form';

import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { MCPServerFormFields } from '../MCPServerFormFields';

const known = vi.hoisted(() => ({ read: vi.fn() }));
vi.mock('@/hooks/useKnownMCPServers', () => ({ useKnownMCPServers: known.read }));

const english = createInstance();
await english.init({ lng: 'en', resources: { en: { translation: en } } });
const french = createInstance();
await french.init({ lng: 'fr', resources: { fr: { translation: fr } } });

const NOTION: KnownMCPServer = {
  key: 'notion',
  name: 'Notion',
  url: 'https://mcp.notion.com/mcp',
  auth_type: 'oauth2',
  domain_description: "The person's Notion workspace.",
  icon: 'notion.png',
};
const CALA: KnownMCPServer = {
  key: 'cala',
  name: 'Cala',
  url: 'https://api.cala.ai/mcp/',
  auth_type: 'api_key',
  domain_description: 'Verified knowledge.',
  icon: 'cala.png',
  header_name: 'X-API-Key',
};
const HUGGING: KnownMCPServer = {
  key: 'huggingface',
  name: 'Hugging Face',
  url: 'https://huggingface.co/mcp',
  auth_type: 'bearer',
  domain_description: 'The Hub.',
  icon: 'huggingface.svg',
};
const GITHUB: KnownMCPServer = {
  key: 'github',
  name: 'GitHub',
  url: 'https://api.githubcopilot.com/mcp/',
  auth_type: 'oauth2',
  domain_description: "The person's GitHub.",
  icon: 'github.svg',
  oauth_scopes: 'repo',
  own_oauth_client: true,
};
const EXA: KnownMCPServer = {
  key: 'exa',
  name: 'Exa',
  url: 'https://mcp.exa.ai/mcp',
  auth_type: 'none',
  domain_description: 'Web search.',
  icon: 'exa.png',
};
const CALLBACK = 'https://lia.example/api/v1/mcp/servers/oauth/callback';
const SAVED: MCPServerFormSource = {
  id: 'server',
  name: 'Notion',
  url: NOTION.url,
  auth_type: 'oauth2',
  header_name: null,
  oauth_scopes: null,
  domain_description: null,
  timeout_seconds: 30,
  iterative_mode: false,
  has_credentials: false,
  has_oauth_credentials: true,
};

function Form({
  start,
  editing = null,
  t = english.t,
}: {
  start: MCPServerFormState;
  editing?: MCPServerFormSource | null;
  t?: typeof english.t;
}) {
  const [form, setForm] = useState(start);
  return <MCPServerFormFields form={form} setForm={setForm} editingServer={editing} t={t} />;
}

const filledWith = (server: KnownMCPServer) => applyKnownServer(emptyMCPServerForm(), server);
const next = en.settings.mcp.known.next;
const purposes = en.settings.mcp.known.servers;

beforeEach(() => {
  vi.clearAllMocks();
  known.read.mockReturnValue({
    servers: [CALA, EXA, GITHUB, HUGGING, NOTION],
    loading: false,
    oauthRedirectUri: CALLBACK,
  });
});

describe('the known server of a create form', () => {
  it.each([
    {
      server: NOTION,
      purpose: purposes.notion,
      step: next.oauth2.replaceAll('{{name}}', 'Notion'),
    },
    { server: CALA, purpose: purposes.cala, step: next.api_key.replaceAll('{{name}}', 'Cala') },
    {
      server: HUGGING,
      purpose: purposes.huggingface,
      step: next.bearer.replaceAll('{{name}}', 'Hugging Face'),
    },
    { server: EXA, purpose: purposes.exa, step: next.none },
  ])('names $server.name, what it is for and what to do next', ({ server, purpose, step }) => {
    renderWithProviders(<Form start={filledWith(server)} />);

    expect(screen.getByText(server.name)).toBeInTheDocument();
    expect(screen.getByText(purpose)).toBeInTheDocument();
    expect(screen.getByText(step)).toBeInTheDocument();
    expect(screen.queryByText(CALLBACK)).toBeNull();
  });

  it('gives the callback to declare when the person brings their own OAuth application', () => {
    renderWithProviders(<Form start={filledWith(GITHUB)} />);

    expect(screen.getByText(next.oauth2_own.replaceAll('{{name}}', 'GitHub'))).toBeInTheDocument();
    expect(screen.getByText(CALLBACK)).toBeInTheDocument();
    expect(screen.getByText(/^Callback URL to declare/)).toBeInTheDocument();
  });

  it('says nothing of a callback the instance did not publish', () => {
    known.read.mockReturnValue({ servers: [GITHUB], loading: false, oauthRedirectUri: null });
    renderWithProviders(<Form start={filledWith(GITHUB)} />);

    expect(screen.getByText(next.oauth2_own.replaceAll('{{name}}', 'GitHub'))).toBeInTheDocument();
    expect(screen.queryByText(/^Callback URL to declare/)).toBeNull();
  });

  it('leaves once the address is edited by hand: it is no known server any more', async () => {
    const { user } = renderWithProviders(<Form start={filledWith(NOTION)} />);
    const url = screen.getByRole('textbox', { name: en.settings.mcp.field_url });

    await user.type(url, '/v2');

    expect(screen.queryByText(next.oauth2.replaceAll('{{name}}', 'Notion'))).toBeNull();
  });

  it('is not drawn for a typed address, nor when a saved server is edited', () => {
    const { unmount } = renderWithProviders(<Form start={emptyMCPServerForm()} />);
    expect(screen.queryByText(next.none)).toBeNull();
    unmount();

    renderWithProviders(<Form start={filledWith(NOTION)} editing={SAVED} />);
    expect(screen.queryByText(next.oauth2.replaceAll('{{name}}', 'Notion'))).toBeNull();
  });

  it('says the same in French', () => {
    renderWithProviders(<Form start={filledWith(CALA)} t={french.t} />);

    expect(
      screen.getByText(fr.settings.mcp.known.next.api_key.replaceAll('{{name}}', 'Cala'))
    ).toBeInTheDocument();
    expect(screen.getByText(fr.settings.mcp.known.servers.cala)).toBeInTheDocument();
  });
});
