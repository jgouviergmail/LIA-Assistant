/**
 * DeviceSessionsSettings — the session list (attested names, families
 * fallback, current badge, unknown-device fallback), single revocation with
 * confirm, and the step-up-guarded revoke-others flow.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import userEvent from '@testing-library/user-event';
import type { DeviceSession } from '@/hooks/useSessions';

const { useSessions } = vi.hoisted(() => ({ useSessions: vi.fn() }));
const { setEnabled, refreshUser } = vi.hoisted(() => ({
  setEnabled: vi.fn(),
  refreshUser: vi.fn(),
}));
vi.mock('@/hooks/useSessions', () => ({
  useSessions,
  useLoginNotificationsPreference: () => ({ setEnabled }),
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { login_notifications_enabled: true },
    refreshUser,
  }),
}));
const { useStepUpGuard } = vi.hoisted(() => ({ useStepUpGuard: vi.fn() }));
vi.mock('@/hooks/useStepUpGuard', () => ({ useStepUpGuard }));
vi.mock('@/components/auth/StepUpDialog', () => ({
  StepUpDialog: ({ open }: { open: boolean }) => (open ? <div>step-up-open</div> : null),
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { DeviceSessionsSettings } from '../DeviceSessionsSettings';

function session(over: Partial<DeviceSession> = {}): DeviceSession {
  return {
    id: 'abcd1234abcd1234',
    current: false,
    ua_family: 'chrome',
    os_family: 'windows',
    ip_trunc: '10.0.0.x',
    auth_methods: ['password'],
    created_at: '2026-07-20T10:00:00Z',
    last_seen_at: '2026-07-23T08:00:00Z',
    device_name: null,
    ...over,
  };
}

function sessionsHook(over: Record<string, unknown> = {}) {
  return {
    sessions: [] as DeviceSession[],
    loading: false,
    error: null,
    refetch: vi.fn(),
    revokeSession: vi.fn().mockResolvedValue(undefined),
    revokeOthers: vi.fn().mockResolvedValue(2),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  setEnabled.mockResolvedValue(undefined);
  refreshUser.mockResolvedValue(undefined);
  useSessions.mockReturnValue(sessionsHook());
  useStepUpGuard.mockReturnValue({
    guard: (fn: () => Promise<unknown>) => fn(),
    stepUpOpen: false,
    onVerified: vi.fn(),
    onCancel: vi.fn(),
  });
});

describe('DeviceSessionsSettings — list', () => {
  it('renders attested name, families fallback, and unknown fallback', () => {
    useSessions.mockReturnValue(
      sessionsHook({
        sessions: [
          session({ id: 's1', device_name: 'iPhone de Jean', current: true }),
          session({ id: 's2' }),
          session({ id: 's3', ua_family: null, os_family: null, ip_trunc: null }),
        ],
      })
    );
    renderWithProviders(<DeviceSessionsSettings collapsible={false} />);

    // A4 attested session shows the real device name + current badge.
    expect(screen.getByText('iPhone de Jean')).toBeInTheDocument();
    expect(screen.getByText('settings.security.devices.current')).toBeInTheDocument();
    // Metadata fallback: coarse families.
    expect(screen.getByText('chrome · windows')).toBeInTheDocument();
    // Legacy session without metadata.
    expect(screen.getByText('settings.security.devices.unknown_device')).toBeInTheDocument();
  });

  it('offers no revoke button on the current session', () => {
    useSessions.mockReturnValue(
      sessionsHook({ sessions: [session({ id: 's1', current: true })] })
    );
    renderWithProviders(<DeviceSessionsSettings collapsible={false} />);
    expect(
      screen.queryByRole('button', { name: 'settings.security.devices.revoke_aria' })
    ).not.toBeInTheDocument();
  });
});

describe('DeviceSessionsSettings — revocation', () => {
  it('revokes one session after confirmation', async () => {
    const hook = sessionsHook({
      sessions: [session({ id: 's1', current: true }), session({ id: 's2' })],
    });
    useSessions.mockReturnValue(hook);
    const user = userEvent.setup();
    renderWithProviders(<DeviceSessionsSettings collapsible={false} />);

    await user.click(
      screen.getByRole('button', { name: 'settings.security.devices.revoke_aria' })
    );
    await user.click(
      screen.getByRole('button', { name: 'settings.security.devices.revoke_confirm' })
    );

    await waitFor(() => expect(hook.revokeSession).toHaveBeenCalledWith('s2'));
    expect(toast.success).toHaveBeenCalledWith('settings.security.devices.revoked');
  });

  it('revokes all others through the step-up guard', async () => {
    const guard = vi.fn((fn: () => Promise<unknown>) => fn());
    useStepUpGuard.mockReturnValue({
      guard,
      stepUpOpen: false,
      onVerified: vi.fn(),
      onCancel: vi.fn(),
    });
    const hook = sessionsHook({
      sessions: [session({ id: 's1', current: true }), session({ id: 's2' })],
    });
    useSessions.mockReturnValue(hook);
    const user = userEvent.setup();
    renderWithProviders(<DeviceSessionsSettings collapsible={false} />);

    await user.click(
      screen.getByRole('button', { name: 'settings.security.devices.revoke_others' })
    );
    await user.click(
      screen.getByRole('button', { name: 'settings.security.devices.revoke_others_confirm' })
    );

    await waitFor(() => expect(hook.revokeOthers).toHaveBeenCalled());
    expect(guard).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith('settings.security.devices.others_revoked');
  });

  it('disables revoke-others with a single session', () => {
    useSessions.mockReturnValue(
      sessionsHook({ sessions: [session({ id: 's1', current: true })] })
    );
    renderWithProviders(<DeviceSessionsSettings collapsible={false} />);
    expect(
      screen.getByRole('button', { name: 'settings.security.devices.revoke_others' })
    ).toBeDisabled();
  });
});

describe('DeviceSessionsSettings — login-notification preference (A4)', () => {
  it('persists the new value then refreshes the user', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DeviceSessionsSettings collapsible={false} />);

    const toggle = screen.getByRole('switch', {
      name: 'settings.security.devices.notify_title',
    });
    expect(toggle).toBeChecked();

    await user.click(toggle);

    await waitFor(() => expect(setEnabled).toHaveBeenCalledWith(false));
    await waitFor(() => expect(refreshUser).toHaveBeenCalled());
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('surfaces a persistence failure without refreshing', async () => {
    setEnabled.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    renderWithProviders(<DeviceSessionsSettings collapsible={false} />);

    await user.click(
      screen.getByRole('switch', { name: 'settings.security.devices.notify_title' })
    );

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.security.devices.error_generic')
    );
    expect(refreshUser).not.toHaveBeenCalled();
  });
});
