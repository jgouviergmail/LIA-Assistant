/**
 * StepUpDialog — offers the account's available methods (fetched from the
 * status endpoint), verifies with password/TOTP, reports success to the
 * guard, and surfaces failures inline without closing.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import userEvent from '@testing-library/user-event';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { ...original.default, get, post } };
});
vi.mock('@/lib/webauthn', () => ({
  isWebAuthnSupported: () => true,
  parseRequestOptions: vi.fn(),
  serializeAuthenticationCredential: vi.fn(),
}));
const { initiateGoogleOAuth } = vi.hoisted(() => ({ initiateGoogleOAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ initiateGoogleOAuth }),
}));

import { StepUpDialog } from '../StepUpDialog';

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue({
    methods: ['password', 'totp', 'passkey'],
    password_set: true,
    step_up_valid_until: null,
  });
});

describe('StepUpDialog', () => {
  it('renders the methods reported by the status endpoint', async () => {
    renderWithProviders(<StepUpDialog open onVerified={vi.fn()} onCancel={vi.fn()} />);

    expect(await screen.findByLabelText('auth.stepUp.password_label')).toBeInTheDocument();
    expect(screen.getByLabelText('auth.stepUp.totp_label')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'auth.stepUp.passkey_button' })
    ).toBeInTheDocument();
  });

  it('verifies with the password and reports success', async () => {
    post.mockResolvedValue({});
    const onVerified = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<StepUpDialog open onVerified={onVerified} onCancel={vi.fn()} />);

    await user.type(await screen.findByLabelText('auth.stepUp.password_label'), 'pw');
    await user.click(screen.getByRole('button', { name: 'auth.stepUp.password_submit' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/auth/step-up/password', { password: 'pw' })
    );
    await waitFor(() => expect(onVerified).toHaveBeenCalled());
  });

  it('keeps the dialog open with an inline error on failure', async () => {
    post.mockRejectedValue(new Error('401'));
    const onVerified = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<StepUpDialog open onVerified={onVerified} onCancel={vi.fn()} />);

    await user.type(await screen.findByLabelText('auth.stepUp.password_label'), 'bad');
    await user.click(screen.getByRole('button', { name: 'auth.stepUp.password_submit' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('auth.stepUp.error');
    expect(onVerified).not.toHaveBeenCalled();
  });

  it('hides method inputs the account does not support', async () => {
    get.mockResolvedValue({
      methods: ['password'],
      password_set: true,
      step_up_valid_until: null,
    });
    renderWithProviders(<StepUpDialog open onVerified={vi.fn()} onCancel={vi.fn()} />);

    expect(await screen.findByLabelText('auth.stepUp.password_label')).toBeInTheDocument();
    expect(screen.queryByLabelText('auth.stepUp.totp_label')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'auth.stepUp.passkey_button' })
    ).not.toBeInTheDocument();
  });

  it('offers a Google re-sign-in to an OAuth-only account (anti-deadlock)', async () => {
    get.mockResolvedValue({
      methods: ['oauth_google'],
      password_set: false,
      step_up_valid_until: null,
    });
    const user = userEvent.setup();
    renderWithProviders(<StepUpDialog open onVerified={vi.fn()} onCancel={vi.fn()} />);

    const googleButton = await screen.findByRole('button', {
      name: 'auth.stepUp.oauth_google_button',
    });
    expect(screen.getByText('auth.stepUp.oauth_hint')).toBeInTheDocument();
    expect(screen.queryByLabelText('auth.stepUp.password_label')).not.toBeInTheDocument();

    await user.click(googleButton);
    await waitFor(() => expect(initiateGoogleOAuth).toHaveBeenCalled());
  });

  it('explains itself instead of a bare Cancel when no method exists', async () => {
    get.mockResolvedValue({
      methods: [],
      password_set: false,
      step_up_valid_until: null,
    });
    renderWithProviders(<StepUpDialog open onVerified={vi.fn()} onCancel={vi.fn()} />);

    expect(await screen.findByText('auth.stepUp.no_methods')).toBeInTheDocument();
  });
});
