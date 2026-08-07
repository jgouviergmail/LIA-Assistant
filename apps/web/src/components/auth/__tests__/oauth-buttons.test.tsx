/**
 * OAuthButtons — the Google sign-in entry point: its label follows the mode
 * (sign in vs sign up), a click hands over to the OAuth initiation and locks the
 * button so a second redirect cannot be queued, and a failed initiation both
 * reports a two-line toast and gives the button back to the user (otherwise the
 * form would be permanently dead).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { initiateGoogleOAuth } = vi.hoisted(() => ({ initiateGoogleOAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ initiateGoogleOAuth }) }));

const authFeatures = vi.hoisted(() => ({ value: { mfa_enabled: true, federated_signin_enabled: true } }));
vi.mock('@/hooks/useWebAuthn', () => ({
  useAuthFeatures: () => ({ features: authFeatures.value, loading: false }),
}));
// `withContext` keeps a frozen identity — a fresh one per render would retrigger
// every effect depending on it (see GUIDE_TESTING → hook-mock stability).
const { withContext } = vi.hoisted(() => ({
  withContext: (extra: Record<string, unknown>) => extra,
}));
vi.mock('@/lib/logging-context', () => ({ useLoggingContext: () => ({ withContext }) }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { OAuthButtons } from '../oauth-buttons';

const SIGN_IN = 'auth.oauth.continue_with_google';
const SIGN_UP = 'auth.oauth.signup_with_google';

beforeEach(() => {
  vi.clearAllMocks();
  initiateGoogleOAuth.mockResolvedValue(undefined);
});

describe('OAuthButtons — labelling', () => {
  it('invites to sign in by default', () => {
    renderWithProviders(<OAuthButtons />);
    expect(screen.getByRole('button', { name: SIGN_IN })).toBeInTheDocument();
  });

  it('invites to sign up in register mode', () => {
    renderWithProviders(<OAuthButtons mode="register" />);
    expect(screen.getByRole('button', { name: SIGN_UP })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: SIGN_IN })).not.toBeInTheDocument();
  });
});

describe('OAuthButtons — initiation', () => {
  it('hands over to the OAuth flow and locks the button while redirecting', async () => {
    // Never settles: the real flow ends in a browser redirect.
    initiateGoogleOAuth.mockReturnValue(new Promise(() => {}));
    const { user } = renderWithProviders(<OAuthButtons />);
    await user.click(screen.getByRole('button', { name: SIGN_IN }));
    expect(initiateGoogleOAuth).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByRole('button', { name: SIGN_IN })).toBeDisabled());
  });

  it('reports a failed initiation and gives the button back', async () => {
    initiateGoogleOAuth.mockRejectedValue(new Error('popup blocked'));
    const { user } = renderWithProviders(<OAuthButtons />);
    await user.click(screen.getByRole('button', { name: SIGN_IN }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('auth.oauth.error_title', {
        description: 'auth.oauth.error_message',
      })
    );
    // Not left permanently disabled — the user can retry.
    expect(screen.getByRole('button', { name: SIGN_IN })).toBeEnabled();
  });
});

describe('OAuthButtons — an instance that does not offer it', () => {
  afterEach(() => {
    authFeatures.value = { mfa_enabled: true, federated_signin_enabled: true };
  });

  it('draws no button when the instance refuses provider sign-in', () => {
    // The public demonstrator closes this route: a button answering 404 is
    // worse than no button, and the visitor has an email form right below.
    authFeatures.value = { mfa_enabled: true, federated_signin_enabled: false };
    const { container } = renderWithProviders(<OAuthButtons />);
    expect(container).toBeEmptyDOMElement();
  });

  it('draws nothing while the answer is unknown', () => {
    // A button that appears a beat later moves the form under the cursor.
    authFeatures.value = undefined as never;
    const { container } = renderWithProviders(<OAuthButtons />);
    expect(container).toBeEmptyDOMElement();
  });
});
