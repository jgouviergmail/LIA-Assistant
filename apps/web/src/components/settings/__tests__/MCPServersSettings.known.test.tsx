/**
 * MCPServersSettings — the known servers: « + Known MCPs » opens a gallery of
 * tiles, a tile opens the create form already filled with that server, and a
 * server the person already has (recognised by its address) is never offered
 * again. The gallery and the form are two dialogs: once the form closes, the
 * focus returns to the button that opened the gallery, its tile being gone.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';

vi.mock('@/hooks/useAppConfig', async importOriginal => {
  const original = await importOriginal<typeof import('@/hooks/useAppConfig')>();
  const { appConfigFixture } = await import('@/__tests__/fixtures/app-config');
  const config = appConfigFixture();
  const useAppConfig: typeof original.useAppConfig = (enabled = true) => ({
    config: enabled ? config : null,
    loading: false,
    error: null,
  });
  return { ...original, useAppConfig };
});

const { useUserMCPServers } = vi.hoisted(() => ({ useUserMCPServers: vi.fn() }));
vi.mock('@/hooks/useUserMCPServers', () => ({ useUserMCPServers }));
const known = vi.hoisted(() => ({ read: vi.fn() }));
vi.mock('@/hooks/useKnownMCPServers', () => ({ useKnownMCPServers: known.read }));
type BehaviorQuery = ReturnType<typeof import('@/hooks/useMCPServerBehavior').useMCPServerBehavior>;
const { useMCPServerBehavior, useMCPBehaviorPreview, useMCPToolChoice } = vi.hoisted(() => ({
  useMCPServerBehavior: vi.fn(
    (): BehaviorQuery => ({ behavior: undefined, loading: false, error: null, refetch: vi.fn() })
  ),
  useMCPBehaviorPreview: vi.fn(() => ({
    previewServer: vi.fn(async () => ({ behavior: undefined, questions_lost: [] })),
    previewStrategy: vi.fn(async () => ({ questions_lost: [] })),
  })),
  useMCPToolChoice: vi.fn(() => ({ setToolChoice: vi.fn() })),
}));
vi.mock('@/hooks/useMCPServerBehavior', () => ({
  useMCPServerBehavior,
  useMCPBehaviorPreview,
  useMCPToolChoice,
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { mcpDefaultsFixture } from '@/__tests__/fixtures/mcp-behavior';
import { userMCPServerFixture } from '@/__tests__/fixtures/mcp-servers';
import type { useUserMCPServers as useUserMCPServersFn } from '@/hooks/useUserMCPServers';
import type { KnownMCPServer } from '@/lib/mcp-known-servers';
import { MCPServersSettings } from '../MCPServersSettings';

type McpHook = ReturnType<typeof useUserMCPServersFn>;

const NOTION: KnownMCPServer = {
  key: 'notion',
  name: 'Notion',
  url: 'https://mcp.notion.com/mcp',
  auth_type: 'oauth2',
  domain_description: "The person's Notion workspace.",
  icon: 'notion.png',
};
const BRIGHT: KnownMCPServer = {
  key: 'brightdata',
  name: 'Bright Data',
  url: 'https://mcp.brightdata.com/mcp',
  auth_type: 'bearer',
  domain_description: 'Live web data.',
  icon: 'brightdata.png',
};

const createServer = vi.fn();

function hook(over: Partial<McpHook> = {}) {
  return {
    ownerId: 'owner',
    servers: [],
    total: 0,
    defaults: mcpDefaultsFixture(),
    loading: false,
    refetch: vi.fn(),
    createServer,
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

function render(over: Partial<McpHook> = {}) {
  useUserMCPServers.mockReturnValue(hook(over));
  return renderWithProviders(<MCPServersSettings lng="en" />);
}

const KNOWN_BUTTON = 'settings.mcp.known.button';
const knownButton = () => screen.getByRole('button', { name: KNOWN_BUTTON });
const gallery = () => screen.getByRole('dialog', { name: 'settings.mcp.known.title' });

beforeEach(() => {
  vi.clearAllMocks();
  createServer.mockResolvedValue(userMCPServerFixture({ name: 'Notion' }));
  known.read.mockReturnValue({
    servers: [BRIGHT, NOTION],
    loading: false,
    oauthRedirectUri: null,
  });
});

describe('the known servers of the MCP settings', () => {
  it('offers the gallery beside « Add server », and not without a catalogue', () => {
    const { unmount } = render();
    expect(knownButton()).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'settings.mcp.add_server' })).toBeInTheDocument();
    unmount();

    known.read.mockReturnValue({ servers: [], loading: false, oauthRedirectUri: null });
    render();
    expect(screen.queryByRole('button', { name: KNOWN_BUTTON })).toBeNull();
  });

  it('opens the create form filled with the server a tile names', async () => {
    const { user } = render();

    await user.click(knownButton());
    await user.click(within(gallery()).getByRole('button', { name: 'Notion' }));

    const form = await screen.findByRole('dialog', { name: 'settings.mcp.add_title' });
    expect(screen.queryByRole('dialog', { name: 'settings.mcp.known.title' })).toBeNull();
    expect(within(form).getByLabelText('settings.mcp.field_name')).toHaveValue('Notion');
    expect(within(form).getByLabelText('settings.mcp.field_url')).toHaveValue(NOTION.url);

    await user.click(within(form).getByRole('button', { name: 'common.save' }));

    await waitFor(() => expect(createServer).toHaveBeenCalledTimes(1));
    expect(createServer.mock.calls[0][0]).toMatchObject({
      name: 'Notion',
      url: NOTION.url,
      auth_type: 'oauth2',
      domain_description: NOTION.domain_description,
    });
  });

  it('greys a server the person already has, whatever the address carries', async () => {
    const { user } = render({
      servers: [
        userMCPServerFixture({
          id: 'mine',
          name: 'BrightData',
          url: 'https://mcp.brightdata.com/mcp?token=typed-by-the-person',
        }),
      ],
      total: 1,
    });

    await user.click(knownButton());
    const bright = within(gallery()).getByRole('button', { name: 'Bright Data' });
    expect(bright).toHaveAttribute('aria-disabled', 'true');
    expect(within(gallery()).getByRole('button', { name: 'Notion' })).not.toHaveAttribute(
      'aria-disabled'
    );

    await user.click(bright);
    expect(screen.queryByRole('dialog', { name: 'settings.mcp.add_title' })).toBeNull();
    expect(gallery()).toBeInTheDocument();
  });

  it('returns the focus to the gallery’s button once the form it opened is closed', async () => {
    const { user } = render();

    await user.click(knownButton());
    await user.click(within(gallery()).getByRole('button', { name: 'Notion' }));
    await screen.findByRole('dialog', { name: 'settings.mcp.add_title' });

    await user.keyboard('{Escape}');

    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'settings.mcp.add_title' })).toBeNull()
    );
    await waitFor(() => expect(knownButton()).toHaveFocus());
  });

  it('opens a blank form from « Add server » after a known one was abandoned', async () => {
    const { user } = render();

    await user.click(knownButton());
    await user.click(within(gallery()).getByRole('button', { name: 'Notion' }));
    await screen.findByRole('dialog', { name: 'settings.mcp.add_title' });
    await user.keyboard('{Escape}');
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'settings.mcp.add_title' })).toBeNull()
    );

    await user.click(screen.getByRole('button', { name: 'settings.mcp.add_server' }));

    const form = await screen.findByRole('dialog', { name: 'settings.mcp.add_title' });
    expect(within(form).getByLabelText('settings.mcp.field_name')).toHaveValue('');
    expect(within(form).getByLabelText('settings.mcp.field_url')).toHaveValue('');
  });
});
