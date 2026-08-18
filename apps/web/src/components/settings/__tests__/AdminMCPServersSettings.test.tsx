/**
 * AdminMCPServersSettings — the "not configured" null render, and toggling a
 * server's per-user availability (success toast; failure toast).
 *
 * The component renders as an open card (ADR-227), so the
 * server list lives in an accordion that the test expands first.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useAdminMCPServers } = vi.hoisted(() => ({ useAdminMCPServers: vi.fn() }));
vi.mock('@/hooks/useAdminMCPServers', () => ({ useAdminMCPServers }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { AdminMCPServersSettings } from '../AdminMCPServersSettings';
import type { useAdminMCPServers as useAdminMCPServersFn } from '@/hooks/useAdminMCPServers';

type AdminMcpHook = ReturnType<typeof useAdminMCPServersFn>;
type AdminMcpServer = AdminMcpHook['servers'][number];

function server(over: Partial<AdminMcpServer> = {}) {
  return {
    server_key: 'weather',
    name: 'Weather',
    description: 'Weather tools',
    tools_count: 2,
    enabled_for_user: false,
    tools: [],
    ...over,
  };
}

function hook(over: Partial<AdminMcpHook> = {}) {
  return {
    servers: [server()],
    loading: false,
    error: null,
    toggleServer: vi.fn().mockResolvedValue({ enabled_for_user: true }),
    toggling: false,
    refetch: vi.fn(),
    ...over,
  };
}

function renderSection() {
  return renderWithProviders(
    <AdminMCPServersSettings lng="en" />
  );
}

beforeEach(() => vi.clearAllMocks());

describe('AdminMCPServersSettings', () => {
  it('renders nothing when MCP is not configured (no servers, no error)', () => {
    useAdminMCPServers.mockReturnValue(hook({ servers: [] }));
    const { container } = renderWithProviders(<AdminMCPServersSettings lng="en" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('toggling a server persists the change and toasts success', async () => {
    const toggleServer = vi.fn().mockResolvedValue({ enabled_for_user: true });
    useAdminMCPServers.mockReturnValue(hook({ toggleServer }));
    const { user } = renderSection();
    await user.click(screen.getByRole('switch', { name: 'settings.admin_mcp.toggle_server' }));
    expect(toggleServer).toHaveBeenCalledWith('weather');
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
  });

  it('toasts an error when the toggle fails', async () => {
    const toggleServer = vi.fn().mockRejectedValue(new Error('boom'));
    useAdminMCPServers.mockReturnValue(hook({ toggleServer }));
    const { user } = renderSection();
    await user.click(screen.getByRole('switch', { name: 'settings.admin_mcp.toggle_server' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});
