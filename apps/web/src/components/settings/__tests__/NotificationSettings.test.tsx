/**
 * NotificationSettings — permission gating (not-configured / denied / loading),
 * the registered-devices list and current-device switch state, the destructive
 * per-device removal (confirm → unregister → toast, plus the error path), and
 * enabling via the permission prompt.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';
import type { UseFCMTokenReturn, RegisteredToken } from '@/hooks/useFCMToken';

const { useFCMToken } = vi.hoisted(() => ({ useFCMToken: vi.fn() }));
vi.mock('@/hooks/useFCMToken', () => ({ useFCMToken }));
// The component resolves the "current device" via getDeviceType(); pin it to web.
vi.mock('@/lib/firebase', () => ({ getDeviceType: () => 'web' }));
// Stub the permission dialog to a visible marker driven purely by `open`.
vi.mock('@/components/notifications/NotificationPrompt', () => ({
  NotificationPrompt: ({ open }: { open: boolean }) => (open ? <div>prompt-open</div> : null),
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { NotificationSettings } from '../NotificationSettings';

function token(over: Partial<RegisteredToken> = {}): RegisteredToken {
  return {
    id: 'tok1',
    device_type: 'web',
    device_name: 'This Device',
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    last_used_at: null,
    ...over,
  };
}

function fcm(over: Partial<UseFCMTokenReturn> = {}): UseFCMTokenReturn {
  return {
    token: null,
    permissionStatus: 'granted',
    isSupported: true,
    isConfigured: true,
    isIOSPWA: false,
    isLoading: false,
    error: null,
    registeredTokens: [],
    requestPermission: vi.fn().mockResolvedValue(null),
    unregisterToken: vi.fn().mockResolvedValue(undefined),
    refreshTokens: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

function renderNotifications() {
  return renderWithProviders(
    <Accordion type="multiple" defaultValue={['notifications']}>
      <NotificationSettings lng="en" />
    </Accordion>
  );
}

beforeEach(() => vi.clearAllMocks());

describe('NotificationSettings — gating', () => {
  it('warns and disables the switch when Firebase is not configured', () => {
    useFCMToken.mockReturnValue(fcm({ isConfigured: false, permissionStatus: 'not-configured' }));
    renderNotifications();
    expect(screen.getByText('settings.notifications.not_configured_admin')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeDisabled();
  });

  it('shows the denied help and disables the switch when permission is denied', () => {
    useFCMToken.mockReturnValue(fcm({ permissionStatus: 'denied' }));
    renderNotifications();
    expect(screen.getByText('settings.notifications.permission_denied_help')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeDisabled();
  });

  it('shows a spinner while the token list loads', () => {
    useFCMToken.mockReturnValue(fcm({ isLoading: true }));
    renderNotifications();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});

describe('NotificationSettings — devices', () => {
  it('lists the registered device and checks the switch for the current device', () => {
    useFCMToken.mockReturnValue(fcm({ registeredTokens: [token()] }));
    renderNotifications();
    expect(screen.getByText('settings.notifications.registered_devices')).toBeInTheDocument();
    expect(screen.getByText('This Device')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeChecked();
  });

  it('shows the empty state when granted with no registered device', () => {
    useFCMToken.mockReturnValue(fcm({ registeredTokens: [] }));
    renderNotifications();
    expect(screen.getByText('settings.notifications.no_devices')).toBeInTheDocument();
  });

  it('removes a device after confirmation and toasts success', async () => {
    const unregisterToken = vi.fn().mockResolvedValue(undefined);
    useFCMToken.mockReturnValue(fcm({ registeredTokens: [token()], unregisterToken }));
    const { user } = renderNotifications();
    await user.click(
      screen.getByRole('button', { name: 'settings.notifications.remove_device_title' })
    );
    await user.click(await screen.findByRole('button', { name: 'common.delete' }));
    await waitFor(() => expect(unregisterToken).toHaveBeenCalledWith('tok1'));
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('toasts an error when device removal fails', async () => {
    const unregisterToken = vi.fn().mockRejectedValue(new Error('boom'));
    useFCMToken.mockReturnValue(fcm({ registeredTokens: [token()], unregisterToken }));
    const { user } = renderNotifications();
    await user.click(
      screen.getByRole('button', { name: 'settings.notifications.remove_device_title' })
    );
    await user.click(await screen.findByRole('button', { name: 'common.delete' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});

describe('NotificationSettings — enabling', () => {
  it('opens the permission prompt when enabling from an ungranted state', async () => {
    useFCMToken.mockReturnValue(fcm({ permissionStatus: 'default', registeredTokens: [] }));
    const { user } = renderNotifications();
    expect(screen.queryByText('prompt-open')).not.toBeInTheDocument();
    await user.click(screen.getByRole('switch'));
    expect(screen.getByText('prompt-open')).toBeInTheDocument();
  });
});
