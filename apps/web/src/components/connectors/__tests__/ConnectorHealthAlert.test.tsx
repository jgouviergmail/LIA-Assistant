/**
 * The health alert offers « reconnect my services » like « My connectors » does.
 *
 * Two expired Google services on one account: one click, one authorization,
 * and the health hook told to refetch on return. Two accounts: the dialog asks
 * which one. One broken service per provider: nothing grouped to offer.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { ConnectorHealthItem } from '@/hooks/useConnectorHealth';

const health = vi.hoisted(() => ({
  critical: [] as ConnectorHealthItem[],
  markReconnectPending: vi.fn(),
  onCritical: undefined as ((items: ConnectorHealthItem[]) => void) | undefined,
}));
vi.mock('@/hooks/useConnectorHealth', () => ({
  useConnectorHealth: (options: { onCritical?: (items: ConnectorHealthItem[]) => void }) => {
    health.onCritical = options.onCritical;
    return {
      criticalConnectors: health.critical,
      markReconnectPending: health.markReconnectPending,
    };
  },
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'u1' }, isLoading: false }),
}));
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { post, get: vi.fn() } }));
const { navigateToAuthorizationUrl } = vi.hoisted(() => ({
  navigateToAuthorizationUrl: vi.fn(),
}));
vi.mock('@/lib/safe-navigation', () => ({ navigateToAuthorizationUrl }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { ConnectorHealthAlert } from '../ConnectorHealthAlert';

function item(over: Partial<ConnectorHealthItem> = {}): ConnectorHealthItem {
  return {
    id: 'calendar',
    connector_type: 'google_calendar',
    display_name: 'Google Calendar',
    health_status: 'error',
    severity: 'critical',
    expires_in_minutes: null,
    authorize_url: '/connectors/google_calendar/authorize',
    bulk_reconnect_provider: 'google',
    oauth_grant_id: 'grant-a',
    oauth_account_email: 'someone@example.org',
    ...over,
  };
}

const GOOGLE_ACTION = 'settings.connectors.bulk_reconnect.google_action';

beforeEach(() => {
  vi.clearAllMocks();
  health.critical = [];
  post.mockResolvedValue({ authorization_url: 'https://accounts.google.com/o/oauth2/auth' });
});

describe('ConnectorHealthAlert — grouped reconnection', () => {
  it('starts one authorization for two services of one account, marking the refetch', async () => {
    health.critical = [
      item(),
      item({ id: 'mail', connector_type: 'google_gmail', display_name: 'Gmail' }),
    ];
    const { user } = renderWithProviders(<ConnectorHealthAlert lng="en" />);

    await user.click(screen.getByRole('button', { name: GOOGLE_ACTION }));

    await waitFor(() => expect(navigateToAuthorizationUrl).toHaveBeenCalledOnce());
    expect(post).toHaveBeenCalledWith('/connectors/oauth-bulk/google/authorize', {
      connector_types: ['google_calendar', 'google_gmail'],
    });
    expect(navigateToAuthorizationUrl).toHaveBeenCalledWith(
      'https://accounts.google.com/o/oauth2/auth',
      'bulk-reconnect'
    );
    // Marked BEFORE the browser leaves, so the health refetches on return.
    expect(health.markReconnectPending).toHaveBeenCalledOnce();
    expect(health.markReconnectPending.mock.invocationCallOrder[0]).toBeLessThan(
      navigateToAuthorizationUrl.mock.invocationCallOrder[0]
    );
  });

  it('asks which account when the services belong to two', async () => {
    health.critical = [
      item(),
      item({
        id: 'mail',
        connector_type: 'google_gmail',
        oauth_grant_id: 'grant-b',
        oauth_account_email: 'other@example.org',
      }),
    ];
    const { user } = renderWithProviders(<ConnectorHealthAlert lng="en" />);

    await user.click(screen.getByRole('button', { name: GOOGLE_ACTION }));

    expect(
      await screen.findByRole('dialog', { name: 'settings.connectors.bulk_reconnect.google_title' })
    ).toBeInTheDocument();
    expect(screen.getByText('other@example.org')).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('offers nothing grouped when each provider has a single broken service', () => {
    health.critical = [
      item(),
      item({
        id: 'outlook',
        connector_type: 'microsoft_outlook',
        bulk_reconnect_provider: 'microsoft',
        oauth_grant_id: 'grant-m',
      }),
    ];
    renderWithProviders(<ConnectorHealthAlert lng="en" />);

    expect(screen.queryByRole('button', { name: /bulk_reconnect/ })).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'settings.connectors.health.banner_manage' })
    ).toBeInTheDocument();
  });

  it('offers it in the modal too, and closes the modal before the account choice', async () => {
    const broken = [
      item(),
      item({ id: 'mail', connector_type: 'google_gmail', oauth_grant_id: null }),
    ];
    health.critical = broken;
    const { user } = renderWithProviders(<ConnectorHealthAlert lng="en" />);
    // The health hook calls `onCritical` when it detects the set: open the modal.
    await waitFor(() => expect(health.onCritical).toBeDefined());
    const onCritical = health.onCritical;
    if (!onCritical) throw new Error('the alert registered no onCritical');
    await act(() => onCritical(broken));
    const modal = await screen.findByRole('dialog', {
      name: /settings\.connectors\.health\.modal_title/,
    });

    await user.click(within(modal).getByRole('button', { name: GOOGLE_ACTION }));

    // An unverified account among them: the choice opens, the modal is gone.
    expect(
      await screen.findByRole('dialog', { name: 'settings.connectors.bulk_reconnect.google_title' })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('dialog', { name: /settings\.connectors\.health\.modal_title/ })
    ).not.toBeInTheDocument();
  });
});
