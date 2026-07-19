/**
 * UserConnectorsSection — the connector hub's orchestration (the individual
 * cards have their own suites). Covers the loading state, the collapsed-by-
 * default family sections, and the disconnect journey: expand → confirm →
 * delete → **optimistic prune of the cached list**, plus the dismissal and the
 * failure paths.
 *
 * Only the OAuth/bulk/preferences hooks are stubbed — the real cards render, so
 * the affordances asserted here are the ones a user actually sees. The stubs
 * return frozen identities (see the hook-mock stability pitfall in
 * GUIDE_TESTING).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeConnector } from '@/__tests__/factories';
import {
  queryResult,
  mutationResult,
  mutateSpy,
  setDataSpy,
  takeUpdater,
} from '@/__tests__/api-mocks';
import type { Connector, ConnectorsResponse } from '../connectors/types';

const { oauthStub, bulkStub, prefsStub } = vi.hoisted(() => ({
  oauthStub: { connect: vi.fn() },
  bulkStub: { bulkConnecting: false, connectAllGoogle: vi.fn(), connectAllMicrosoft: vi.fn() },
  prefsStub: { savedPrefs: {}, savingPreference: null, selectPreference: vi.fn() },
}));
// Keep every real card/constant from the barrel; stub only the side-effecting hooks.
vi.mock('../connectors', async importOriginal => {
  const actual = await importOriginal<typeof import('../connectors')>();
  return {
    ...actual,
    useGoogleOAuth: () => oauthStub,
    useMicrosoftOAuth: () => oauthStub,
    useBulkConnect: () => bulkStub,
    useConnectorPreferences: () => prefsStub,
  };
});
const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));
const { get, post, del } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), del: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get, post, delete: del } }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import UserConnectorsSection from '../UserConnectorsSection';

const GOOGLE_SECTION = /connected_google/;
const DISCONNECT = 'settings.connectors.google.disconnect';

let setData: ReturnType<typeof setDataSpy<ConnectorsResponse>>;
let deleteConnector: ReturnType<typeof mutateSpy>;

function stub(connectors: Connector[], loading = false) {
  setData = setDataSpy<ConnectorsResponse>();
  useApiQuery.mockReturnValue(
    queryResult<ConnectorsResponse>({ data: { connectors }, loading, setData })
  );
}

function render() {
  return renderWithProviders(<UserConnectorsSection lng="en" collapsible={false} />);
}

/** Expands the "connected Google" family so its cards mount. */
async function openGoogleFamily(user: ReturnType<typeof render>['user']) {
  await user.click(await screen.findByRole('button', { name: GOOGLE_SECTION }));
}

beforeEach(() => {
  vi.clearAllMocks();
  deleteConnector = mutateSpy().mockResolvedValue(undefined);
  useApiMutation.mockReturnValue(mutationResult({ mutate: deleteConnector }));
  // The preference dropdown inside a connected card fetches its items.
  get.mockResolvedValue({ items: [] });
  stub([makeConnector({ id: 'c1', connector_type: 'google_calendar' })]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('UserConnectorsSection — shell', () => {
  it('shows the loading state before the connector list arrives', () => {
    stub([], true);
    render();
    expect(screen.getByText('common.loading')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: GOOGLE_SECTION })).not.toBeInTheDocument();
  });

  it('keeps the connected family collapsed until the user opens it', async () => {
    const { user } = render();
    expect(await screen.findByRole('button', { name: GOOGLE_SECTION })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: DISCONNECT })).not.toBeInTheDocument();
    await openGoogleFamily(user);
    expect(await screen.findByRole('button', { name: DISCONNECT })).toBeInTheDocument();
  });
});

describe('UserConnectorsSection — disconnect', () => {
  it('does nothing when the confirmation is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { user } = render();
    await openGoogleFamily(user);
    await user.click(await screen.findByRole('button', { name: DISCONNECT }));
    expect(deleteConnector).not.toHaveBeenCalled();
    expect(setData).not.toHaveBeenCalled();
  });

  it('deletes the connector and prunes it from the cached list', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { user } = render();
    await openGoogleFamily(user);
    await user.click(await screen.findByRole('button', { name: DISCONNECT }));
    await waitFor(() => expect(deleteConnector).toHaveBeenCalledWith('/connectors/c1'));
    // Optimistic prune: the updater drops exactly the disconnected row.
    const next = takeUpdater(setData)({
      connectors: [
        makeConnector({ id: 'c1', connector_type: 'google_calendar' }),
        makeConnector({ id: 'c2', connector_type: 'gmail' }),
      ],
    });
    expect(next?.connectors.map(c => c.id)).toEqual(['c2']);
  });

  it('reports a failed disconnect and leaves the cache untouched', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    deleteConnector.mockRejectedValue(new Error('boom'));
    const { user } = render();
    await openGoogleFamily(user);
    await user.click(await screen.findByRole('button', { name: DISCONNECT }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.connectors.disconnect_error')
    );
    expect(setData).not.toHaveBeenCalled();
  });
});
