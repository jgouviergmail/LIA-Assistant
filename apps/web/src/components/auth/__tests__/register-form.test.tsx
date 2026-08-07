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

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { register } = vi.hoisted(() => ({ register: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ register }) }));

const authFeatures = vi.hoisted(() => ({
  value: { mfa_enabled: false, federated_signin_enabled: true, terms_required: false, terms_version: '' },
}));
vi.mock('@/hooks/useWebAuthn', () => ({
  useAuthFeatures: () => ({ features: authFeatures.value, loading: false }),
}));
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

import { RegisterForm, registrationErrorKey } from '../register-form';

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
        'fr',
        // Seventh argument: terms acceptance, undefined where nothing is
        // required of the visitor.
        undefined
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
        'fr',
        undefined
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

describe('RegisterForm — a demonstrator asks for the terms', () => {
  afterEach(() => {
    authFeatures.value = {
      mfa_enabled: false,
      federated_signin_enabled: true,
      terms_required: false,
      terms_version: '',
    };
  });

  it('shows no checkbox on an ordinary instance', () => {
    renderWithProviders(<RegisterForm />);
    expect(screen.queryByRole('checkbox', { name: /auth\.terms/ })).not.toBeInTheDocument();
  });

  it('asks for acceptance when the instance requires it', () => {
    authFeatures.value = {
      mfa_enabled: false,
      federated_signin_enabled: false,
      terms_required: true,
      terms_version: '2026-08-06',
    };
    renderWithProviders(<RegisterForm />);

    // The box exists, and the terms are one click away — a visitor cannot
    // accept what they cannot read.
    expect(screen.getByRole('checkbox', { name: /auth\.terms/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'auth.terms.link_label' })).toHaveAttribute(
      'target',
      '_blank'
    );
  });

  it('refuses to submit unaccepted, and says why', async () => {
    authFeatures.value = {
      mfa_enabled: false,
      federated_signin_enabled: false,
      terms_required: true,
      terms_version: '2026-08-06',
    };
    const { user } = renderWithProviders(<RegisterForm />);

    await fill(user);
    await user.click(screen.getByRole('button', { name: 'auth.register_button' }));

    // The server refuses this too; saying it here spares the visitor a round
    // trip that reads as "Registration failed" with no reason.
    expect(await screen.findByText('auth.errors.terms_not_accepted')).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });

  it('carries the acceptance to the API once ticked', async () => {
    authFeatures.value = {
      mfa_enabled: false,
      federated_signin_enabled: false,
      terms_required: true,
      terms_version: '2026-08-06',
    };
    const { user } = renderWithProviders(<RegisterForm />);

    await fill(user);
    await user.click(screen.getByRole('checkbox', { name: /auth\.terms/ }));
    await user.click(screen.getByRole('button', { name: 'auth.register_button' }));

    await waitFor(() => expect(register).toHaveBeenCalled());
    expect(register.mock.calls[0][6]).toBe(true);
  });
});


describe('registrationErrorKey — an explicable refusal stays explicable', () => {
  /**
   * The demonstrator's daily ceiling is a bound the visitor can act on: it
   * reopens at midnight UTC. Collapsing it into "registration failed" told
   * them nothing — not that it is full, not that it reopens, not when. And
   * the first version of the backend shipped an English sentence, which a
   * French visitor would have read in English.
   */
  it('names the daily ceiling when the backend refuses for that reason', () => {
    const error = { data: { detail: { error: 'demo_signup_limit_reached' } } };

    expect(registrationErrorKey(error)).toBe('auth.errors.demo_signup_limit_reached');
  });

  it.each([
    ['a different structured code', { data: { detail: { error: 'email_already_exists' } } }],
    ['a validation array', { data: { detail: [{ msg: 'invalid' }] } }],
    ['no data at all', new Error('network down')],
    ['a null detail', { data: { detail: null } }],
    ['a non-string code', { data: { detail: { error: 42 } } }],
    ['undefined', undefined],
  ])('keeps the generic message for %s', (_label, error) => {
    // Inventing a specific cause for a failure the visitor cannot act on is
    // worse than saying nothing precise.
    expect(registrationErrorKey(error)).toBe('auth.errors.registration_failed');
  });
});
