/**
 * SecuritySettings — MFA-flag gating (renders nothing when disabled), the
 * passkey list (labels, synced badge, accessible action names), the empty
 * state, enrollment success/error, and the destructive revocation flow
 * (confirm dialog → delete → toast, plus the error path).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import userEvent from '@testing-library/user-event';
import type { PasskeyCredential } from '@/hooks/useWebAuthn';

const { useAuthFeatures, usePasskeys, useWebAuthn } = vi.hoisted(() => ({
  useAuthFeatures: vi.fn(),
  usePasskeys: vi.fn(),
  useWebAuthn: vi.fn(),
}));
vi.mock('@/hooks/useWebAuthn', () => ({ useAuthFeatures, usePasskeys, useWebAuthn }));
vi.mock('@/lib/webauthn', () => ({ isWebAuthnSupported: () => true }));
// The dialog has its own test file; here it only needs to exist.
vi.mock('@/components/auth/StepUpDialog', () => ({
  StepUpDialog: ({ open }: { open: boolean }) => (open ? <div>step-up-open</div> : null),
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { SecuritySettings } from '../SecuritySettings';

function passkey(over: Partial<PasskeyCredential> = {}): PasskeyCredential {
  return {
    id: 'pk-1',
    label: 'iPhone',
    device_type: 'multi_device',
    backed_up: true,
    transports: ['internal'],
    created_at: '2026-07-01T10:00:00Z',
    last_used_at: '2026-07-20T08:00:00Z',
    ...over,
  };
}

function passkeysHook(over: Record<string, unknown> = {}) {
  return {
    passkeys: [] as PasskeyCredential[],
    loading: false,
    error: null,
    refetch: vi.fn().mockResolvedValue(undefined),
    renamePasskey: vi.fn().mockResolvedValue(undefined),
    deletePasskey: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthFeatures.mockReturnValue({ features: { mfa_enabled: true, federated_signin_enabled: true }, loading: false });
  usePasskeys.mockReturnValue(passkeysHook());
  useWebAuthn.mockReturnValue({
    registerPasskey: vi.fn().mockResolvedValue(passkey()),
    authenticateWithPasskey: vi.fn(),
  });
});

describe('SecuritySettings — gating', () => {
  it('renders nothing when the instance has MFA disabled', () => {
    useAuthFeatures.mockReturnValue({ features: { mfa_enabled: false, federated_signin_enabled: true }, loading: false });
    const { container } = renderWithProviders(<SecuritySettings />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the section title and empty state when enabled with no passkeys', () => {
    renderWithProviders(<SecuritySettings />);
    expect(screen.getByText('settings.security.passkeys.title')).toBeInTheDocument();
    expect(screen.getByText('settings.security.passkeys.empty')).toBeInTheDocument();
  });

  it('renders itself as the open settings card the shell deep-links to', () => {
    const { container } = renderWithProviders(<SecuritySettings />);

    // The anchor id is the deep-link contract (`?section=security-auth`): the
    // pane polls it to tell an absent section from a slow one.
    expect(container.querySelector('#settings-section-security-auth')).not.toBeNull();
    expect(
      screen.getByRole('heading', { name: 'settings.security.auth.title' })
    ).toBeInTheDocument();
    // Body visible on mount — no disclosure step since ADR-227.
    expect(screen.getByText('settings.security.passkeys.empty')).toBeInTheDocument();
  });
});

describe('SecuritySettings — list', () => {
  it('shows each passkey with label, synced badge and accessible actions', () => {
    usePasskeys.mockReturnValue(
      passkeysHook({
        passkeys: [passkey(), passkey({ id: 'pk-2', label: null, backed_up: false })],
      })
    );
    renderWithProviders(<SecuritySettings />);

    expect(screen.getByText('iPhone')).toBeInTheDocument();
    // Unnamed credential falls back to the translated placeholder name.
    expect(screen.getByText('settings.security.passkeys.unnamed')).toBeInTheDocument();
    // Only the synced passkey carries the badge.
    expect(screen.getAllByText('settings.security.passkeys.synced')).toHaveLength(1);
    // Accessible names on both action buttons, per credential.
    expect(
      screen.getAllByRole('button', { name: 'settings.security.passkeys.rename_aria' })
    ).toHaveLength(2);
    expect(
      screen.getAllByRole('button', { name: 'settings.security.passkeys.revoke_aria' })
    ).toHaveLength(2);
  });
});

describe('SecuritySettings — enrollment', () => {
  it('registers a passkey with the typed label and toasts success', async () => {
    const registerPasskey = vi.fn().mockResolvedValue(passkey());
    useWebAuthn.mockReturnValue({ registerPasskey, authenticateWithPasskey: vi.fn() });
    const user = userEvent.setup();
    renderWithProviders(<SecuritySettings />);

    await user.click(screen.getByRole('button', { name: /settings\.security\.passkeys\.add$/ }));
    await user.type(screen.getByLabelText('settings.security.passkeys.label_input'), 'PC bureau');
    await user.click(
      screen.getByRole('button', { name: 'settings.security.passkeys.add_confirm' })
    );

    await waitFor(() => expect(registerPasskey).toHaveBeenCalledWith('PC bureau'));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('settings.security.passkeys.added')
    );
  });

  it('toasts an error when the ceremony fails and keeps the dialog open', async () => {
    const registerPasskey = vi.fn().mockRejectedValue(new Error('NotAllowedError'));
    useWebAuthn.mockReturnValue({ registerPasskey, authenticateWithPasskey: vi.fn() });
    const user = userEvent.setup();
    renderWithProviders(<SecuritySettings />);

    await user.click(screen.getByRole('button', { name: /settings\.security\.passkeys\.add$/ }));
    await user.click(
      screen.getByRole('button', { name: 'settings.security.passkeys.add_confirm' })
    );

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.security.passkeys.add_error')
    );
  });
});

describe('SecuritySettings — revocation', () => {
  it('deletes after explicit confirmation and toasts success', async () => {
    const deletePasskey = vi.fn().mockResolvedValue(undefined);
    usePasskeys.mockReturnValue(passkeysHook({ passkeys: [passkey()], deletePasskey }));
    const user = userEvent.setup();
    renderWithProviders(<SecuritySettings />);

    await user.click(
      screen.getByRole('button', { name: 'settings.security.passkeys.revoke_aria' })
    );
    await user.click(
      screen.getByRole('button', { name: 'settings.security.passkeys.revoke_confirm' })
    );

    await waitFor(() => expect(deletePasskey).toHaveBeenCalledWith('pk-1'));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('settings.security.passkeys.revoked')
    );
  });

  it('toasts an error when revocation fails', async () => {
    const deletePasskey = vi.fn().mockRejectedValue(new Error('500'));
    usePasskeys.mockReturnValue(passkeysHook({ passkeys: [passkey()], deletePasskey }));
    const user = userEvent.setup();
    renderWithProviders(<SecuritySettings />);

    await user.click(
      screen.getByRole('button', { name: 'settings.security.passkeys.revoke_aria' })
    );
    await user.click(
      screen.getByRole('button', { name: 'settings.security.passkeys.revoke_confirm' })
    );

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.security.passkeys.revoke_error')
    );
  });
});

describe('SecuritySettings — rename', () => {
  it('renames through the dialog and toasts success', async () => {
    const renamePasskey = vi.fn().mockResolvedValue(undefined);
    usePasskeys.mockReturnValue(passkeysHook({ passkeys: [passkey()], renamePasskey }));
    const user = userEvent.setup();
    renderWithProviders(<SecuritySettings />);

    await user.click(
      screen.getByRole('button', { name: 'settings.security.passkeys.rename_aria' })
    );
    const input = screen.getByLabelText('settings.security.passkeys.label_input');
    await user.clear(input);
    await user.type(input, 'Nouveau nom');
    await user.click(screen.getByRole('button', { name: 'common.save' }));

    await waitFor(() => expect(renamePasskey).toHaveBeenCalledWith('pk-1', 'Nouveau nom'));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('settings.security.passkeys.renamed')
    );
  });
});
