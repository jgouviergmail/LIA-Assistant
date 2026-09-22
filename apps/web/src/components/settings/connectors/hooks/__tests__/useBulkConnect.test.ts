/** One provider request connects all absent eligible services on one account. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@/__tests__/test-utils';
import { makeConnector } from '@/__tests__/factories';
import type { Connector } from '@/components/settings/connectors/types';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { post } }));
const { toast } = vi.hoisted(() => ({ toast: { info: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({ logger: { error: vi.fn() } }));
const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));
vi.mock('@/lib/safe-navigation', () => ({ navigateToAuthorizationUrl: navigate }));

import { availableTypes, useBulkConnect } from '../useBulkConnect';

const t = (key: string) => key;
function setup(connectors: Connector[] = []) {
  return renderHook(() => useBulkConnect({ connectors, loading: false, t }));
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  post.mockResolvedValue({ authorization_url: 'https://accounts.example/oauth' });
});

describe('useBulkConnect', () => {
  it('starts exactly one Google authorization without persisting an OAuth queue', async () => {
    const { result } = setup();
    await act(async () => result.current.connectAllGoogle());

    expect(post).toHaveBeenCalledExactlyOnceWith(
      '/connectors/oauth-bulk/google/connect-all/authorize', {}
    );
    expect(navigate).toHaveBeenCalledExactlyOnceWith(
      'https://accounts.example/oauth', 'bulk-connect'
    );
    expect(sessionStorage.getItem('oauth_connectors_reconnect_pending')).toBe('true');
    expect(localStorage.length).toBe(0);
  });

  it('starts exactly one Microsoft authorization', async () => {
    const { result } = setup();
    await act(async () => result.current.connectAllMicrosoft());
    expect(post).toHaveBeenCalledExactlyOnceWith(
      '/connectors/oauth-bulk/microsoft/connect-all/authorize', {}
    );
  });

  it('does not include a configured error service in Connect All', async () => {
    const connectors = [
      makeConnector({ id: '1', connector_type: 'google_gmail', status: 'error' }),
      ...['google_contacts', 'google_calendar', 'google_drive', 'google_tasks'].map((type, i) =>
        makeConnector({ id: `a${i}`, connector_type: type, status: 'active' })
      ),
    ];
    const { result } = setup(connectors);
    await act(async () => result.current.connectAllGoogle());
    expect(post).not.toHaveBeenCalled();
    expect(toast.info).toHaveBeenCalled();
  });

  it('does not start when every absent service is blocked by an active alternative', async () => {
    const connectors = [
      makeConnector({ id: 'outlook', connector_type: 'microsoft_outlook', status: 'active' }),
      ...['google_contacts', 'google_calendar', 'google_drive', 'google_tasks'].map((type, i) =>
        makeConnector({ id: `a${i}`, connector_type: type, status: 'active' })
      ),
    ];
    const { result } = setup(connectors);
    expect(result.current.canConnectGoogle).toBe(false);
    await act(async () => result.current.connectAllGoogle());
    expect(post).not.toHaveBeenCalled();
    expect(toast.info).toHaveBeenCalled();
  });

  it('does not offer Outlook when legacy Gmail is active', () => {
    const connectors = [makeConnector({ id: 'legacy', connector_type: 'gmail', status: 'active' })];
    expect(availableTypes('microsoft', connectors)).not.toContain('microsoft_outlook');
  });

  it('requires a deliberate account choice when known grants exist', async () => {
    const connectors = [
      makeConnector({ id: 'a', connector_type: 'google_calendar', status: 'active',
        oauth_grant_id: 'grant-a', metadata: { oauth_account_email: 'a@gmail.com' } }),
      makeConnector({ id: 'b', connector_type: 'google_contacts', status: 'active',
        oauth_grant_id: 'grant-b', metadata: { oauth_account_email: 'b@gmail.com' } }),
    ];
    const { result } = setup(connectors);
    await act(async () => result.current.connectAllGoogle());
    expect(post).not.toHaveBeenCalled();
    expect(result.current.accountDialogProvider).toBe('google');
    expect(result.current.knownAccounts).toEqual([
      { grantId: 'grant-a', email: 'a@gmail.com' },
      { grantId: 'grant-b', email: 'b@gmail.com' },
    ]);
    await act(async () => result.current.confirmAccount('grant-b'));
    expect(post).toHaveBeenCalledExactlyOnceWith(
      '/connectors/oauth-bulk/google/connect-all/authorize', { grant_id: 'grant-b' }
    );
  });

  it('allows choosing another provider account without binding a known grant', async () => {
    const { result } = setup([
      makeConnector({ id: 'a', connector_type: 'google_calendar', status: 'active',
        oauth_grant_id: 'grant-a' }),
    ]);
    await act(async () => result.current.connectAllGoogle());
    await act(async () => result.current.confirmAccount(null));
    expect(post).toHaveBeenCalledExactlyOnceWith(
      '/connectors/oauth-bulk/google/connect-all/authorize', {}
    );
  });

  it('recovers from a rejected authorization request', async () => {
    post.mockRejectedValueOnce(new Error('temporary failure'));
    const { result } = setup();
    await act(async () => result.current.connectAllMicrosoft());
    expect(result.current.bulkConnecting).toBe(false);
    expect(toast.error).toHaveBeenCalledWith('settings.connectors.microsoft.connect_all_error');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('ignores a second click while the first authorization is in flight', async () => {
    let resolve!: (value: { authorization_url: string }) => void;
    post.mockReturnValueOnce(new Promise(resolvePromise => { resolve = resolvePromise; }));
    const { result } = setup();
    let first!: Promise<void>;
    act(() => { first = result.current.connectAllGoogle(); });
    await act(async () => result.current.connectAllMicrosoft());
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => { resolve({ authorization_url: 'https://accounts.example/oauth' }); await first; });
  });
});
