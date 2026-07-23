/**
 * LoginForm — two-step (TOTP) branch: a login answering mfa_required swaps
 * the credential form for the code step, a valid code completes navigation,
 * and a failed code returns to the credential form with a clear error (the
 * pending token is single-use).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

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

async function submitCredentials(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('auth.email_label'), 'user@test.dev');
  await user.type(screen.getByLabelText('auth.password_label'), 'Sup3rSecret!!');
  await user.click(screen.getByRole('button', { name: 'auth.login_button' }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('LoginForm — two-step login', () => {
  it('switches to the code step when the account requires MFA', async () => {
    login.mockResolvedValue({ user: null, mfaRequired: true, mfaToken: 'tok-1' });
    const user = userEvent.setup();
    renderWithProviders(<LoginForm />);

    await submitCredentials(user);

    expect(await screen.findByLabelText('auth.mfa.code_label')).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it('verifies the code and navigates to the dashboard', async () => {
    login.mockResolvedValue({ user: null, mfaRequired: true, mfaToken: 'tok-1' });
    verifyMfa.mockResolvedValue({ id: 'u1' });
    const user = userEvent.setup();
    renderWithProviders(<LoginForm />);

    await submitCredentials(user);
    await user.type(await screen.findByLabelText('auth.mfa.code_label'), '123456');
    await user.click(screen.getByRole('button', { name: 'auth.mfa.verify_button' }));

    await waitFor(() => expect(verifyMfa).toHaveBeenCalledWith('tok-1', '123456'));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/dashboard'));
  });

  it('returns to the credential form with an error when the code fails', async () => {
    login.mockResolvedValue({ user: null, mfaRequired: true, mfaToken: 'tok-1' });
    verifyMfa.mockRejectedValue(new Error('401'));
    const user = userEvent.setup();
    renderWithProviders(<LoginForm />);

    await submitCredentials(user);
    await user.type(await screen.findByLabelText('auth.mfa.code_label'), '000000');
    await user.click(screen.getByRole('button', { name: 'auth.mfa.verify_button' }));

    // Single-use token: back to credentials with the localized error.
    expect(await screen.findByText('auth.mfa.invalid_code')).toBeInTheDocument();
    expect(screen.getByLabelText('auth.email_label')).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it('completes a classic single-step login unchanged', async () => {
    login.mockResolvedValue({ user: { id: 'u1' }, mfaRequired: false, mfaToken: null });
    const user = userEvent.setup();
    renderWithProviders(<LoginForm />);

    await submitCredentials(user);

    await waitFor(() => expect(push).toHaveBeenCalledWith('/dashboard'));
  });
});
