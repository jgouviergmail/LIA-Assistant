/**
 * MCPServersSettings — the loading and empty states of the user MCP server list.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';

const { useUserMCPServers } = vi.hoisted(() => ({ useUserMCPServers: vi.fn() }));
vi.mock('@/hooks/useUserMCPServers', () => ({ useUserMCPServers }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { MCPServersSettings } from '../MCPServersSettings';
import type { useUserMCPServers as useUserMCPServersFn } from '@/hooks/useUserMCPServers';

type McpHook = ReturnType<typeof useUserMCPServersFn>;

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

beforeEach(() => vi.clearAllMocks());

describe('MCPServersSettings', () => {
  it('shows a loading spinner while servers load', () => {
    useUserMCPServers.mockReturnValue(hook({ loading: true }));
    render();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders without a spinner once the (empty) list has loaded', () => {
    useUserMCPServers.mockReturnValue(hook({ loading: false, servers: [] }));
    render();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
