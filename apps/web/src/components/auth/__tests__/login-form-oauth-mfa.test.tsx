/**
 * LoginForm — the second step reached by REDIRECT, not by a JSON answer.
 *
 * A provider sign-in on a TOTP-active account cannot hand the pending token to
 * the client: the callback is a redirect, and a single-use credential does not
 * belong in a URL. The token travels in an httpOnly cookie and the browser
 * lands on `/login?mfa=1`, so the form must open its code step **without
 * holding a token** — and then verify with `null`, letting the API read the
 * cookie.
 *
 * The password path must be untouched, which the last test asserts directly.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import userEvent from '@testing-library/user-event';

const { login, verifyMfa } = vi.hoisted(() => ({
  login: vi.fn(),
  verifyMfa: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ login, verifyMfa }),
}));
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push }),
}));

import { LoginForm } from '../login-form';

/** Put a query string on the location the component reads at mount. */
function withSearch(search: string) {
  window.history.replaceState({}, '', `/login${search}`);
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  window.history.replaceState({}, '', '/login');
});

describe('LoginForm — second step reached by redirect', () => {
  it('opens the code step when the callback sent us back with ?mfa=1', async () => {
    withSearch('?mfa=1');

    renderWithProviders(<LoginForm />);

    expect(await screen.findByLabelText('auth.mfa.code_label')).toBeInTheDocument();
    // No credentials were submitted: the first factor happened at the provider.
    expect(login).not.toHaveBeenCalled();
  });

  it('verifies with no token, so the API reads the httpOnly cookie', async () => {
    withSearch('?mfa=1');
    verifyMfa.mockResolvedValue({ id: 'u1' });
    const user = userEvent.setup();
    renderWithProviders(<LoginForm />);

    await user.type(await screen.findByLabelText('auth.mfa.code_label'), '123456');
    await user.click(screen.getByRole('button', { name: 'auth.mfa.verify_button' }));

    await waitFor(() => expect(verifyMfa).toHaveBeenCalledWith(null, '123456'));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/dashboard'));
  });

  it('returns to the credential form when the code is refused', async () => {
    withSearch('?mfa=1');
    verifyMfa.mockRejectedValue(new Error('invalid'));
    const user = userEvent.setup();
    renderWithProviders(<LoginForm />);

    await user.type(await screen.findByLabelText('auth.mfa.code_label'), '000000');
    await user.click(screen.getByRole('button', { name: 'auth.mfa.verify_button' }));

    expect(await screen.findByLabelText('auth.email_label')).toBeInTheDocument();
    expect(screen.getByText('auth.mfa.invalid_code')).toBeInTheDocument();
  });

  it('consumes the flag so a refresh does not reopen the step', async () => {
    withSearch('?mfa=1');

    renderWithProviders(<LoginForm />);

    await screen.findByLabelText('auth.mfa.code_label');
    expect(window.location.search).toBe('');
  });

  it('shows the credential form when no flag is present', async () => {
    withSearch('');

    renderWithProviders(<LoginForm />);

    expect(await screen.findByLabelText('auth.email_label')).toBeInTheDocument();
    expect(screen.queryByLabelText('auth.mfa.code_label')).not.toBeInTheDocument();
  });

  it('keeps handing the password path its own token', async () => {
    withSearch('');
    login.mockResolvedValue({ user: null, mfaRequired: true, mfaToken: 'tok-1' });
    verifyMfa.mockResolvedValue({ id: 'u1' });
    const user = userEvent.setup();
    renderWithProviders(<LoginForm />);

    await user.type(screen.getByLabelText('auth.email_label'), 'user@test.dev');
    await user.type(screen.getByLabelText('auth.password_label'), 'Sup3rSecret!!');
    await user.click(screen.getByRole('button', { name: 'auth.login_button' }));

    await user.type(await screen.findByLabelText('auth.mfa.code_label'), '123456');
    await user.click(screen.getByRole('button', { name: 'auth.mfa.verify_button' }));

    await waitFor(() => expect(verifyMfa).toHaveBeenCalledWith('tok-1', '123456'));
  });
});
