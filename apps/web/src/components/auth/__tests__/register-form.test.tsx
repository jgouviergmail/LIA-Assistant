/**
 * RegisterForm — the sign-up gate: the two client-side refusals (mismatched
 * confirmation, weak password) must both stop the request before it leaves, the
 * live password checklist must reflect what the user typed, and a successful
 * registration must forward the detected timezone/language and land on the
 * confirmation route. The failure path must surface an error without navigating.
 *
 * `validatePassword` / `getPasswordRequirementChecks` are deliberately NOT
 * mocked — they carry the business rule and have their own suite
 * (lib/__tests__/password-validation.test.ts); stubbing them here would hollow
 * out the very behaviour under test.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { register } = vi.hoisted(() => ({ register: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ register }) }));
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('@/hooks/useLocalizedRouter', () => ({ useLocalizedRouter: () => ({ push }) }));
vi.mock('@/utils/timezone', () => ({
  getBrowserTimezone: () => 'Europe/Paris',
  formatTimezoneDisplay: (tz: string) => tz,
}));
vi.mock('@/utils/locale-mapping', () => ({ getBrowserLanguageForBackend: () => 'fr' }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { RegisterForm } from '../register-form';

const NAME = 'auth.full_name_label';
const EMAIL = 'auth.email_label';
const PASSWORD = 'auth.password_label';
const CONFIRM = 'auth.confirm_password_label';
const SUBMIT = 'auth.register_button';

// The real policy demands ≥10 chars AND ≥2 uppercase AND ≥2 digits AND
// ≥2 special characters — counts, not mere presence.
const STRONG = 'Str0ng!@Passw0rd';

async function fill(
  user: ReturnType<typeof renderWithProviders>['user'],
  { password = STRONG, confirm = STRONG }: { password?: string; confirm?: string } = {}
) {
  await user.type(screen.getByLabelText(NAME), 'Alice');
  await user.type(screen.getByLabelText(EMAIL), 'alice@example.com');
  await user.type(screen.getByLabelText(PASSWORD), password);
  await user.type(screen.getByLabelText(CONFIRM), confirm);
}

beforeEach(() => {
  vi.clearAllMocks();
  register.mockResolvedValue(undefined);
});

describe('RegisterForm — client-side refusals', () => {
  it('refuses a confirmation that does not match, without calling the API', async () => {
    const { user } = renderWithProviders(<RegisterForm />);
    await fill(user, { confirm: `${STRONG}-typo` });
    await user.click(screen.getByRole('button', { name: SUBMIT }));
    expect(await screen.findByText('auth.errors.passwords_mismatch')).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });

  it('refuses a password that fails the strength rules, without calling the API', async () => {
    const { user } = renderWithProviders(<RegisterForm />);
    await fill(user, { password: 'weak', confirm: 'weak' });
    await user.click(screen.getByRole('button', { name: SUBMIT }));
    await waitFor(() => expect(register).not.toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
  });

  it('refuses a password holding a single special character — the policy wants two', async () => {
    const { user } = renderWithProviders(<RegisterForm />);
    // Long enough, 2 uppercase, 2 digits… but only one special.
    await fill(user, { password: 'Str0ng!Passw0rd', confirm: 'Str0ng!Passw0rd' });
    await user.click(screen.getByRole('button', { name: SUBMIT }));
    await waitFor(() => expect(register).not.toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
  });
});

describe('RegisterForm — password checklist', () => {
  it('reveals the requirement checklist only once a password is typed', async () => {
    const { user } = renderWithProviders(<RegisterForm />);
    expect(screen.queryByText('auth.password.checks.min_length')).not.toBeInTheDocument();
    await user.type(screen.getByLabelText(PASSWORD), 'a');
    expect(await screen.findByText('auth.password.checks.min_length')).toBeInTheDocument();
  });
});

describe('RegisterForm — submission', () => {
  it('forwards the detected timezone and language, then lands on the confirmation route', async () => {
    const { user } = renderWithProviders(<RegisterForm />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: SUBMIT }));
    await waitFor(() =>
      expect(register).toHaveBeenCalledWith(
        'alice@example.com',
        STRONG,
        'Alice',
        false,
        'Europe/Paris',
        'fr'
      )
    );
    expect(push).toHaveBeenCalledWith('/registration-success');
  });

  it('passes the remember-me choice through', async () => {
    const { user } = renderWithProviders(<RegisterForm />);
    await fill(user);
    await user.click(screen.getByRole('checkbox', { name: 'auth.remember_me' }));
    await user.click(screen.getByRole('button', { name: SUBMIT }));
    await waitFor(() =>
      expect(register).toHaveBeenCalledWith(
        'alice@example.com',
        STRONG,
        'Alice',
        true,
        'Europe/Paris',
        'fr'
      )
    );
  });

  it('surfaces a failed registration and does not navigate', async () => {
    register.mockRejectedValue(new Error('email already taken'));
    const { user } = renderWithProviders(<RegisterForm />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: SUBMIT }));
    expect(await screen.findByText('auth.errors.registration_failed')).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it('shows the detected timezone to the user', async () => {
    renderWithProviders(<RegisterForm />);
    expect(await screen.findByText(/Europe\/Paris/)).toBeInTheDocument();
  });
});
