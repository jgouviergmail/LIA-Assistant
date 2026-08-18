/**
 * MCPServersSettings — the create/edit form (the list behaviour lives in
 * `MCPServersSettings.test.tsx`).
 *
 * This is where the domain rules are: the payload sent on creation depends on
 * the authentication scheme, and the **update is differential** with an
 * exception that only makes sense once you know the storage — credentials are
 * encrypted server-side, so they can never be compared and are therefore sent
 * whenever the user typed something, while every other field is only sent when
 * it actually changed. Saving an untouched form must send nothing at all.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useUserMCPServers } = vi.hoisted(() => ({ useUserMCPServers: vi.fn() }));
vi.mock('@/hooks/useUserMCPServers', () => ({ useUserMCPServers }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { MCPServersSettings } from '../MCPServersSettings';
import type {
  UserMCPServer,
  useUserMCPServers as useUserMCPServersFn,
} from '@/hooks/useUserMCPServers';

type McpHook = ReturnType<typeof useUserMCPServersFn>;

function server(over: Partial<UserMCPServer> = {}): UserMCPServer {
  return {
    id: 's1',
    name: 'Weather MCP',
    url: 'https://mcp.example.com/sse',
    plugin_id: null,
    auth_type: 'none',
    status: 'active',
    is_enabled: true,
    domain_description: null,
    timeout_seconds: 30,
    hitl_required: null,
    iterative_mode: false,
    header_name: null,
    has_credentials: false,
    has_oauth_credentials: false,
    oauth_scopes: null,
    tool_count: 2,
    tools: [],
    last_connected_at: null,
    last_error: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

const createServer = vi.fn();
const updateServer = vi.fn();

function hook(over: Partial<McpHook> = {}) {
  return {
    servers: [],
    total: 0,
    loading: false,
    createServer,
    updateServer,
    deleteServer: vi.fn(),
    toggleServer: vi.fn(),
    testConnection: vi.fn(),
    initiateOAuth: vi.fn(),
    disconnectOAuth: vi.fn(),
    generateDescription: vi.fn(),
    creating: false,
    updating: false,
    deleting: false,
    testing: false,
    disconnecting: false,
    generatingDescription: false,
    ...over,
  };
}

function render(over: Partial<McpHook> = {}) {
  useUserMCPServers.mockReturnValue(hook(over));
  return renderWithProviders(
    <MCPServersSettings lng="en" />
  );
}

type User = ReturnType<typeof render>['user'];

const NAME = 'settings.mcp.field_name';
const URL_FIELD = 'settings.mcp.field_url';
const SAVE = 'common.save';
const saveButton = () => screen.getByRole('button', { name: SAVE });

async function openCreate(user: User) {
  await user.click(screen.getByRole('button', { name: 'settings.mcp.add_server' }));
  return screen.findByLabelText(NAME);
}

async function openEdit(user: User) {
  await user.click(screen.getByRole('button', { name: 'common.edit' }));
  return screen.findByLabelText(NAME);
}

/** Picks an authentication scheme in the Radix select. */
async function chooseAuth(user: User, optionKey: string) {
  await user.click(screen.getByRole('combobox'));
  await user.click(await screen.findByRole('option', { name: optionKey }));
}

beforeEach(() => {
  vi.clearAllMocks();
  createServer.mockResolvedValue(server());
  updateServer.mockResolvedValue(server());
});

describe('MCPServersSettings — creating a server', () => {
  it('refuses to save until a name and a URL are given', async () => {
    const { user } = render();
    const name = await openCreate(user);

    expect(saveButton()).toBeDisabled();
    await user.type(name, 'Weather MCP');
    expect(saveButton()).toBeDisabled();
    await user.type(screen.getByLabelText(URL_FIELD), 'https://mcp.example.com/sse');
    expect(saveButton()).toBeEnabled();
  });

  it('creates an unauthenticated server with the default timeout', async () => {
    const { user } = render();
    const name = await openCreate(user);

    await user.type(name, 'Weather MCP');
    await user.type(screen.getByLabelText(URL_FIELD), 'https://mcp.example.com/sse');
    await user.click(saveButton());

    await waitFor(() =>
      expect(createServer).toHaveBeenCalledWith({
        name: 'Weather MCP',
        url: 'https://mcp.example.com/sse',
        auth_type: 'none',
        timeout_seconds: 30,
        iterative_mode: false,
      })
    );
    expect(toast.success).toHaveBeenCalledWith('settings.mcp.server_created');
  });

  it('requires the key itself once API-key authentication is chosen', async () => {
    const { user } = render();
    const name = await openCreate(user);
    await user.type(name, 'Weather MCP');
    await user.type(screen.getByLabelText(URL_FIELD), 'https://mcp.example.com/sse');

    await chooseAuth(user, 'settings.mcp.auth_api_key');

    // The scheme alone is not enough: an empty key would authenticate nothing.
    expect(saveButton()).toBeDisabled();
  });

  it('sends the key and its header name for API-key authentication', async () => {
    const { user } = render();
    const name = await openCreate(user);
    await user.type(name, 'Weather MCP');
    await user.type(screen.getByLabelText(URL_FIELD), 'https://mcp.example.com/sse');
    await chooseAuth(user, 'settings.mcp.auth_api_key');
    await user.type(screen.getByLabelText('settings.mcp.field_api_key'), 'secret-key');

    await user.click(saveButton());

    await waitFor(() =>
      expect(createServer).toHaveBeenCalledWith(
        expect.objectContaining({
          auth_type: 'api_key',
          api_key: 'secret-key',
          header_name: 'X-API-Key',
        })
      )
    );
  });

  it('sends only the token for bearer authentication', async () => {
    const { user } = render();
    const name = await openCreate(user);
    await user.type(name, 'Weather MCP');
    await user.type(screen.getByLabelText(URL_FIELD), 'https://mcp.example.com/sse');
    await chooseAuth(user, 'settings.mcp.auth_bearer');
    await user.type(screen.getByLabelText('settings.mcp.field_bearer_token'), 'tok-123');

    await user.click(saveButton());

    await waitFor(() => {
      const payload = createServer.mock.calls[0][0];
      expect(payload).toMatchObject({ auth_type: 'bearer', bearer_token: 'tok-123' });
      expect(payload).not.toHaveProperty('api_key');
    });
  });

  it('reports a refused creation without closing the form', async () => {
    createServer.mockRejectedValue(new Error('URL already registered'));
    const { user } = render();
    const name = await openCreate(user);
    await user.type(name, 'Weather MCP');
    await user.type(screen.getByLabelText(URL_FIELD), 'https://mcp.example.com/sse');

    await user.click(saveButton());

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('URL already registered'));
    expect(screen.getByLabelText(NAME)).toBeInTheDocument();
  });
});

describe('MCPServersSettings — editing a server', () => {
  it('prefills the form with the stored configuration', async () => {
    const { user } = render({
      servers: [server({ domain_description: 'Weather data' })],
      total: 1,
    });

    expect(await openEdit(user)).toHaveValue('Weather MCP');
    expect(screen.getByLabelText(URL_FIELD)).toHaveValue('https://mcp.example.com/sse');
    expect(screen.getByLabelText(/settings\.mcp\.field_domain_description/)).toHaveValue(
      'Weather data'
    );
  });

  it('sends only the field that changed', async () => {
    const { user } = render({ servers: [server()], total: 1 });
    const name = await openEdit(user);

    await user.clear(name);
    await user.type(name, 'Renamed MCP');
    await user.click(saveButton());

    await waitFor(() => expect(updateServer).toHaveBeenCalledWith('s1', { name: 'Renamed MCP' }));
    expect(toast.success).toHaveBeenCalledWith('settings.mcp.server_updated');
  });

  it('sends nothing when the form is reopened and saved untouched', async () => {
    const { user } = render({ servers: [server()], total: 1 });
    await openEdit(user);

    await user.click(saveButton());

    await waitFor(() => expect(screen.queryByLabelText(NAME)).not.toBeInTheDocument());
    expect(updateServer).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('always sends a credential the user typed, even though nothing else changed', async () => {
    // Credentials are encrypted server-side: they cannot be diffed, so typing
    // one is itself the signal to send it.
    const { user } = render({
      servers: [server({ auth_type: 'api_key', header_name: 'X-API-Key', has_credentials: true })],
      total: 1,
    });
    await openEdit(user);

    await user.type(screen.getByLabelText('settings.mcp.field_api_key'), 'rotated-key');
    await user.click(saveButton());

    await waitFor(() =>
      expect(updateServer).toHaveBeenCalledWith('s1', { api_key: 'rotated-key' })
    );
  });

  it('sends the header name only when it differs from the stored one', async () => {
    const { user } = render({
      servers: [server({ auth_type: 'api_key', header_name: 'X-Custom' })],
      total: 1,
    });
    await openEdit(user);
    const header = screen.getByLabelText('settings.mcp.field_header_name');

    await user.clear(header);
    await user.type(header, 'X-Other');
    await user.click(saveButton());

    await waitFor(() =>
      expect(updateServer).toHaveBeenCalledWith('s1', { header_name: 'X-Other' })
    );
  });

  it('lets an existing server be saved without retyping its credential', async () => {
    const { user } = render({
      servers: [server({ auth_type: 'bearer', has_credentials: true })],
      total: 1,
    });
    const name = await openEdit(user);

    // On creation an empty token blocks the save; on edition it must not.
    await user.clear(name);
    await user.type(name, 'Renamed');
    expect(saveButton()).toBeEnabled();
  });

  it('clears a description by sending it as undefined', async () => {
    const { user } = render({
      servers: [server({ domain_description: 'Weather data' })],
      total: 1,
    });
    await openEdit(user);

    await user.clear(screen.getByLabelText(/settings\.mcp\.field_domain_description/));
    await user.click(saveButton());

    await waitFor(() =>
      expect(updateServer).toHaveBeenCalledWith('s1', { domain_description: undefined })
    );
  });

  it('reports a refused update', async () => {
    updateServer.mockRejectedValue(new Error('server is locked'));
    const { user } = render({ servers: [server()], total: 1 });
    const name = await openEdit(user);

    await user.clear(name);
    await user.type(name, 'Renamed');
    await user.click(saveButton());

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('server is locked'));
  });
});
