/**
 * TotpSettings — enrollment flow (enroll → QR dialog → confirm → backup
 * codes revealed once), the disable and regenerate destructive flows with
 * confirmation, and error paths (invalid confirmation code).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import userEvent from '@testing-library/user-event';

const { useTotp } = vi.hoisted(() => ({ useTotp: vi.fn() }));
vi.mock('@/hooks/useTotp', () => ({ useTotp }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
// The dialog has its own test file; here it only needs to exist.
vi.mock('@/components/auth/StepUpDialog', () => ({
  StepUpDialog: ({ open }: { open: boolean }) => (open ? <div>step-up-open</div> : null),
}));

import { TotpSettings } from '../TotpSettings';

function totpHook(over: Record<string, unknown> = {}) {
  return {
    status: { active: false, confirmed_at: null, backup_codes_remaining: 0 },
    loading: false,
    refetch: vi.fn(),
    enroll: vi.fn().mockResolvedValue({
      secret: 'BASE32SECRET',
      otpauth_uri: 'otpauth://totp/LIA:user?secret=BASE32SECRET',
      qr_data_uri: 'data:image/png;base64,QR',
    }),
    confirm: vi.fn().mockResolvedValue(['aaaa111111', 'bbbb222222']),
    disable: vi.fn().mockResolvedValue(undefined),
    regenerateBackupCodes: vi.fn().mockResolvedValue(['cccc333333']),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useTotp.mockReturnValue(totpHook());
});

describe('TotpSettings — inactive state', () => {
  it('offers enabling through the feature switch and hides management actions', () => {
    // A switch like every other feature toggle (owner arbitration 2026-08-05),
    // CONTROLLED by the server state: unchecked here, and no regenerate yet.
    renderWithProviders(<TotpSettings />);
    const toggle = screen.getByRole('switch', { name: 'settings.security.totp.title' });
    expect(toggle).not.toBeChecked();
    expect(
      screen.queryByRole('button', { name: 'settings.security.totp.regenerate' })
    ).not.toBeInTheDocument();
  });

  it('enrolls, shows the QR + secret, confirms, then reveals backup codes once', async () => {
    const hook = totpHook();
    useTotp.mockReturnValue(hook);
    const user = userEvent.setup();
    renderWithProviders(<TotpSettings />);

    await user.click(screen.getByRole('switch', { name: 'settings.security.totp.title' }));

    // QR + manual secret are displayed.
    expect(await screen.findByAltText('settings.security.totp.qr_alt')).toBeInTheDocument();
    expect(screen.getByText('BASE32SECRET')).toBeInTheDocument();

    await user.type(screen.getByLabelText('settings.security.totp.enroll_code_label'), '123456');
    await user.click(screen.getByRole('button', { name: 'settings.security.totp.enroll_confirm' }));

    await waitFor(() => expect(hook.confirm).toHaveBeenCalledWith('123456'));
    // Backup codes revealed once.
    expect(await screen.findByText('aaaa111111')).toBeInTheDocument();
    expect(screen.getByText('bbbb222222')).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalledWith('settings.security.totp.activated');
  });

  it('keeps the enrollment dialog open and toasts on an invalid code', async () => {
    const hook = totpHook({ confirm: vi.fn().mockRejectedValue(new Error('400')) });
    useTotp.mockReturnValue(hook);
    const user = userEvent.setup();
    renderWithProviders(<TotpSettings />);

    await user.click(screen.getByRole('switch', { name: 'settings.security.totp.title' }));
    await user.type(
      await screen.findByLabelText('settings.security.totp.enroll_code_label'),
      '000000'
    );
    await user.click(screen.getByRole('button', { name: 'settings.security.totp.enroll_confirm' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.security.totp.enroll_error')
    );
    // Dialog still open for a retry.
    expect(screen.getByAltText('settings.security.totp.qr_alt')).toBeInTheDocument();
  });
});

describe('TotpSettings — active state', () => {
  beforeEach(() => {
    useTotp.mockReturnValue(
      totpHook({
        status: { active: true, confirmed_at: '2026-07-01T00:00:00Z', backup_codes_remaining: 7 },
      })
    );
  });

  it('shows the active badge and remaining backup codes', () => {
    renderWithProviders(<TotpSettings />);
    expect(screen.getByText('settings.security.totp.status_active')).toBeInTheDocument();
    expect(screen.getByText('settings.security.totp.codes_remaining')).toBeInTheDocument();
  });

  it('disables only after explicit confirmation', async () => {
    const hook = totpHook({
      status: { active: true, confirmed_at: '2026-07-01T00:00:00Z', backup_codes_remaining: 7 },
    });
    useTotp.mockReturnValue(hook);
    const user = userEvent.setup();
    renderWithProviders(<TotpSettings />);

    // Turning the switch OFF asks the house confirm first — the thumb only
    // moves once the server confirms the deactivation.
    await user.click(screen.getByRole('switch', { name: 'settings.security.totp.title' }));
    await user.click(
      screen.getByRole('button', { name: 'settings.security.totp.disable_confirm' })
    );

    await waitFor(() => expect(hook.disable).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith('settings.security.totp.disabled_toast');
  });

  it('regenerates codes after confirmation and reveals the new set', async () => {
    const hook = totpHook({
      status: { active: true, confirmed_at: '2026-07-01T00:00:00Z', backup_codes_remaining: 2 },
    });
    useTotp.mockReturnValue(hook);
    const user = userEvent.setup();
    renderWithProviders(<TotpSettings />);

    await user.click(screen.getByRole('button', { name: 'settings.security.totp.regenerate' }));
    // The alert-dialog action carries the same label as the trigger.
    const actions = await screen.findAllByRole('button', {
      name: 'settings.security.totp.regenerate',
    });
    await user.click(actions[actions.length - 1]);

    await waitFor(() => expect(hook.regenerateBackupCodes).toHaveBeenCalled());
    expect(await screen.findByText('cccc333333')).toBeInTheDocument();
  });
});
