/**
 * PasswordSettings — the way back the copy states is the one the reset
 * decision leaves (ADR-363): the email link, the provider the account signs in
 * with, or nothing for an administrator. It used to promise the email reset to
 * every account without a password, Google accounts and administrators
 * included — both now receive a notice or nothing.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import userEvent from '@testing-library/user-event';
import type { PasskeyCredential } from '@/hooks/useWebAuthn';
import apiClient from '@/lib/api-client';

const { usePasskeys } = vi.hoisted(() => ({ usePasskeys: vi.fn() }));
vi.mock('@/hooks/useWebAuthn', () => ({ usePasskeys }));
// The dialog has its own test file; here it only needs to exist.
vi.mock('@/components/auth/StepUpDialog', () => ({ StepUpDialog: () => null }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { PasswordSettings } from '../PasswordSettings';

type Recovery = 'email_link' | 'provider' | 'none';

const KEY = 'settings.security.password';

function passkey(id: string): PasskeyCredential {
  return {
    id,
    label: id,
    device_type: 'multi_device',
    backed_up: true,
    transports: ['internal'],
    created_at: '2026-07-01T10:00:00Z',
    last_used_at: null,
  };
}

function serveStatus(passwordSet: boolean, recovery: Recovery, provider: string | null) {
  vi.spyOn(apiClient, 'get').mockImplementation(async endpoint => {
    if (endpoint === '/auth/step-up/status') {
      return {
        methods: [],
        password_set: passwordSet,
        step_up_valid_until: null,
        password_recovery: recovery,
        sign_in_provider: provider,
      };
    }
    throw new Error(`Unexpected request: ${endpoint}`);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  // Two passkeys: the disabling dialog is reachable (arbitration A8).
  usePasskeys.mockReturnValue({ passkeys: [passkey('first'), passkey('second')] });
});

afterEach(() => vi.restoreAllMocks());

async function renderPassword() {
  await act(async () => {
    renderWithProviders(<PasswordSettings />);
  });
}

describe('PasswordSettings — beside a password already off', () => {
  it.each([
    ['email_link', null, `${KEY}.description_disabled`],
    ['provider', 'Google', `${KEY}.description_provider`],
    ['none', 'Google', `${KEY}.description_provider`],
    ['none', null, `${KEY}.description_no_recovery`],
  ] as const)('a %s account signing in with %s reads %s', async (recovery, provider, key) => {
    serveStatus(false, recovery, provider);

    await renderPassword();

    expect(await screen.findByText(key)).toBeInTheDocument();
  });
});

describe('PasswordSettings — in the dialog that turns the password off', () => {
  it.each([
    ['email_link', null, `${KEY}.disable_description`],
    ['provider', 'Google', `${KEY}.disable_description_provider`],
    ['none', 'Google', `${KEY}.disable_description_provider`],
    ['none', null, `${KEY}.disable_description_no_recovery`],
  ] as const)('a %s account signing in with %s reads %s', async (recovery, provider, key) => {
    serveStatus(true, recovery, provider);

    await renderPassword();
    await userEvent.click(await screen.findByRole('button', { name: `${KEY}.disable` }));

    expect(await screen.findByText(key)).toBeInTheDocument();
  });
});
