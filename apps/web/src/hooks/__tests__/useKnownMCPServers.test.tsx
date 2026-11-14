/**
 * useKnownMCPServers — the known catalogue behind the gallery and the create form.
 *
 * The catalogue is served by the personal servers' router, which refuses every
 * route under the operator's switch (ADR-280): the hook asks only where the
 * layout's read of `/config` says the servers are offered, and whatever it
 * cannot read is an empty catalogue — no gallery, and the form is the one it always was.
 *
 * The read is the real one (`useApiQuery`); only the API client, the boundary,
 * is controlled — so « asks nothing » means that no request leaves.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { appConfigFixture } from '@/__tests__/fixtures/app-config';
import { AppConfigSeedContext, type AppConfig } from '@/hooks/useAppConfig';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn() } }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { useKnownMCPServers } from '../useKnownMCPServers';

const NOTION = {
  key: 'notion',
  name: 'Notion',
  url: 'https://mcp.notion.com/mcp',
  auth_type: 'oauth2',
  domain_description: "The person's Notion workspace.",
  icon: 'notion.png',
};
const CALLBACK = 'https://lia.example/api/v1/mcp/servers/oauth/callback';

const offered = (enabled: boolean): AppConfig =>
  appConfigFixture({ capabilities: { mcp: { enabled, family: 'reach' } } });

function under(config: AppConfig | null) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <AppConfigSeedContext.Provider value={config}>{children}</AppConfigSeedContext.Provider>
  );
  return renderHook(() => useKnownMCPServers(), { wrapper });
}

/** Lets a read that was going to leave, leave: the first one is deferred to a microtask. */
const settled = () => act(async () => {});

beforeEach(() => {
  api.get.mockReset();
  api.get.mockResolvedValue({ servers: [NOTION] });
});

describe('useKnownMCPServers', () => {
  it('reads the catalogue where the personal servers are offered', async () => {
    const { result } = under(offered(true));

    await waitFor(() => expect(result.current.servers).toEqual([NOTION]));
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get.mock.calls[0][0]).toBe('/mcp/servers/known');
    expect(result.current.loading).toBe(false);
  });

  it.each([
    ['the operator closed the personal servers', offered(false)],
    ['the configuration has not answered yet', null],
  ])('asks nothing when %s', async (_label, config) => {
    const { result } = under(config);
    await settled();

    // The router refuses the route under the switch: no request may leave.
    expect(api.get).not.toHaveBeenCalled();
    // Never « loading » for a read that is not asked: the gallery would hold its place for ever.
    expect(result.current).toEqual({ servers: [], loading: false, oauthRedirectUri: null });
  });

  it.each([
    ['a body of another shape', { servers: [{ id: 'server', name: 'Saved' }] }],
    [
      'an entry whose icon would be fetched from a vendor',
      { servers: [{ ...NOTION, icon: 'https://cdn.example/notion.png' }] },
    ],
    [
      'an entry that would prefill a header for a server reading no key',
      { servers: [{ ...NOTION, header_name: 'X-API-Key' }] },
    ],
  ])('answers an empty catalogue for %s', async (_label, body) => {
    api.get.mockResolvedValue(body);
    const { result } = under(offered(true));

    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.servers).toEqual([]);
  });

  it('answers an empty catalogue when the read is refused', async () => {
    api.get.mockRejectedValue(new Error('403'));
    const { result } = under(offered(true));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(result.current.servers).toEqual([]);
  });

  it('holds « loading » while an asked read is on its way, and lets go when it lands', async () => {
    let land: (body: unknown) => void = () => {};
    api.get.mockReturnValue(
      new Promise(resolve => {
        land = resolve;
      })
    );
    const { result } = under(offered(true));
    await settled();

    expect(result.current).toEqual({ servers: [], loading: true, oauthRedirectUri: null });

    await act(async () => land({ servers: [NOTION] }));

    expect(result.current).toEqual({ servers: [NOTION], loading: false, oauthRedirectUri: null });
  });

  it('hands over the OAuth callback the instance publishes with its catalogue', async () => {
    api.get.mockResolvedValue({ servers: [NOTION], oauth_redirect_uri: CALLBACK });
    const { result } = under(offered(true));

    await waitFor(() => expect(result.current.oauthRedirectUri).toBe(CALLBACK));
    expect(result.current.servers).toEqual([NOTION]);
  });
});
