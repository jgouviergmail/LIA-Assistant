/**
 * MCPServersSettings — the user's MCP server list: loading, empty, the rendered
 * row, the enable/disable toggle, the on-demand connection test (both the
 * success wording and the server-provided failure reason), and the confirm-gated
 * deletion with its failure path. Errors thrown by the hook must surface the
 * server's own message rather than a generic one.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';

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

function hook(over: Partial<McpHook> = {}) {
  return {
    servers: [],
    total: 0,
    loading: false,
    createServer: vi.fn(),
    updateServer: vi.fn(),
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

function render() {
  return renderWithProviders(
    <Accordion type="multiple" defaultValue={['mcp-servers']}>
      <MCPServersSettings lng="en" />
    </Accordion>
  );
}

const TOGGLE = 'settings.mcp.toggle_server';
const TEST = 'settings.mcp.test_connection';
const DELETE = 'common.delete';

beforeEach(() => vi.clearAllMocks());

describe('MCPServersSettings — list states', () => {
  it('shows a loading spinner while servers load', () => {
    useUserMCPServers.mockReturnValue(hook({ loading: true }));
    render();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('invites the user to add a server when the list is empty', () => {
    useUserMCPServers.mockReturnValue(hook({ loading: false, servers: [] }));
    render();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByText('settings.mcp.empty')).toBeInTheDocument();
  });

  it('renders a configured server with its endpoint', () => {
    useUserMCPServers.mockReturnValue(hook({ servers: [server()], total: 1 }));
    render();
    expect(screen.getByText('Weather MCP')).toBeInTheDocument();
    expect(screen.getByText('https://mcp.example.com/sse')).toBeInTheDocument();
    expect(screen.queryByText('settings.mcp.empty')).not.toBeInTheDocument();
  });
});

describe('MCPServersSettings — enable toggle', () => {
  it('toggles a server by id', async () => {
    const toggleServer = vi.fn().mockResolvedValue(undefined);
    useUserMCPServers.mockReturnValue(hook({ servers: [server()], toggleServer }));
    const { user } = render();
    await user.click(screen.getByRole('switch', { name: TOGGLE }));
    await waitFor(() => expect(toggleServer).toHaveBeenCalledWith('s1'));
  });

  it('surfaces the server message when the toggle is refused', async () => {
    const toggleServer = vi.fn().mockRejectedValue(new Error('server is locked'));
    useUserMCPServers.mockReturnValue(hook({ servers: [server()], toggleServer }));
    const { user } = render();
    await user.click(screen.getByRole('switch', { name: TOGGLE }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('server is locked'));
  });
});

describe('MCPServersSettings — connection test', () => {
  it('confirms a successful test', async () => {
    const testConnection = vi.fn().mockResolvedValue({ success: true, tool_count: 4, tools: [] });
    useUserMCPServers.mockReturnValue(hook({ servers: [server()], testConnection }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: TEST }));
    await waitFor(() => expect(testConnection).toHaveBeenCalledWith('s1'));
    expect(toast.success).toHaveBeenCalledWith('settings.mcp.test_success');
  });

  it('reports the reason the server gave for a failed test', async () => {
    const testConnection = vi
      .fn()
      .mockResolvedValue({ success: false, tool_count: 0, tools: [], error: 'handshake refused' });
    useUserMCPServers.mockReturnValue(hook({ servers: [server()], testConnection }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: TEST }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('handshake refused'));
  });

  it('falls back to the generic wording when the test throws', async () => {
    const testConnection = vi.fn().mockRejectedValue({ notAnError: true });
    useUserMCPServers.mockReturnValue(hook({ servers: [server()], testConnection }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: TEST }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('settings.mcp.test_failed'));
  });
});

describe('MCPServersSettings — deletion', () => {
  /** Opens the row's delete confirmation; the action shares the trigger label. */
  async function confirmDelete(user: ReturnType<typeof render>['user']) {
    await user.click(screen.getByRole('button', { name: DELETE }));
    const buttons = await screen.findAllByRole('button', { name: DELETE });
    await user.click(buttons[buttons.length - 1]);
  }

  it('deletes a server only after the confirmation is validated', async () => {
    const deleteServer = vi.fn().mockResolvedValue(undefined);
    useUserMCPServers.mockReturnValue(hook({ servers: [server()], deleteServer }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: DELETE }));
    expect(deleteServer).not.toHaveBeenCalled();
    const buttons = await screen.findAllByRole('button', { name: DELETE });
    await user.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(deleteServer).toHaveBeenCalledWith('s1'));
    expect(toast.success).toHaveBeenCalledWith('settings.mcp.server_deleted');
  });

  it('surfaces the server message when a deletion is refused', async () => {
    const deleteServer = vi.fn().mockRejectedValue(new Error('still in use'));
    useUserMCPServers.mockReturnValue(hook({ servers: [server()], deleteServer }));
    const { user } = render();
    await confirmDelete(user);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('still in use'));
  });
});
