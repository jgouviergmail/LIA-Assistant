/**
 * LoginForm — accessible names and control states (audit F012).
 *
 * The remember-me checkbox is queried BY ROLE AND NAME (not by test-id or
 * class), which proves the programmatic label association end to end:
 * label[htmlFor] + aria-labelledby → accessible name. Covers nominal toggle,
 * the disabled state while a login is in flight, the error state after a
 * rejected login, and keyboard focusability. And the bot check (ADR-364): the
 * form waits for its token, sends it, names a refused check, and asks for a
 * new token after every submit.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockLogin = vi.hoisted(() => vi.fn());
const mockPush = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ login: mockLogin }),
}));
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push: mockPush }),
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));
const door = vi.hoisted(() => ({
  asked: '',
  value: {
    siteKey: null as string | null,
    token: null as string | null,
    ready: true,
    failed: false,
    onToken: vi.fn(),
    onFailure: vi.fn(),
    resetSignal: 0,
    spent: vi.fn(),
  },
}));
vi.mock('@/hooks/useTurnstileDoor', () => ({
  useTurnstileDoor: (action: string) => {
    door.asked = action;
    return door.value;
  },
}));
vi.mock('../TurnstileWidget', () => ({
  TurnstileWidget: ({ action }: { action: string }) => <div data-testid="turnstile">{action}</div>,
}));

import { LoginForm } from '../login-form';

function fillCredentials() {
  fireEvent.change(screen.getByLabelText('auth.email_label'), {
    target: { value: 'user@example.test' },
  });
  fireEvent.change(screen.getByLabelText('auth.password_label'), {
    target: { value: 'correct horse battery' },
  });
}

beforeEach(() => {
  mockLogin.mockReset();
  mockPush.mockReset();
  door.value = {
    ...door.value,
    siteKey: null,
    token: null,
    ready: true,
    failed: false,
    spent: vi.fn(),
  };
});

describe('LoginForm — remember-me accessible name and states (F012)', () => {
  it('exposes the checkbox by role and translated name, and toggles it', () => {
    render(<LoginForm />);
    const checkbox = screen.getByRole('checkbox', {
      name: 'auth.remember_me',
    }) as HTMLInputElement;

    expect(checkbox.checked).toBe(false);
    fireEvent.click(checkbox);
    expect(checkbox.checked).toBe(true);
  });

  it('is focusable from the keyboard', () => {
    render(<LoginForm />);
    const checkbox = screen.getByRole('checkbox', { name: 'auth.remember_me' });
    checkbox.focus();
    expect(document.activeElement).toBe(checkbox);
  });

  it('disables the named checkbox while the login is in flight', async () => {
    let resolveLogin: (v: unknown) => void = () => {};
    mockLogin.mockImplementation(() => new Promise(r => (resolveLogin = r)));
    render(<LoginForm />);
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: 'auth.login_button' }));

    const checkbox = screen.getByRole('checkbox', { name: 'auth.remember_me' });
    await waitFor(() => expect(checkbox).toHaveProperty('disabled', true));

    resolveLogin({});
    await waitFor(() => expect(checkbox).toHaveProperty('disabled', false));
  });

  it('shows the translated error after a rejected login, controls stay named', async () => {
    mockLogin.mockRejectedValue(new Error('bad credentials'));
    render(<LoginForm />);
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: 'auth.login_button' }));

    await waitFor(() => expect(screen.getByText('auth.errors.invalid_credentials')).toBeTruthy());
    // The error state never degrades the association.
    expect(screen.getByRole('checkbox', { name: 'auth.remember_me' })).toBeTruthy();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('submits the remembered flag with the credentials', async () => {
    mockLogin.mockResolvedValue({});
    render(<LoginForm />);
    fillCredentials();
    fireEvent.click(screen.getByRole('checkbox', { name: 'auth.remember_me' }));

    fireEvent.click(screen.getByRole('button', { name: 'auth.login_button' }));

    await waitFor(() =>
      expect(mockLogin).toHaveBeenCalledWith(
        'user@example.test',
        'correct horse battery',
        true,
        null
      )
    );
    expect(mockPush).toHaveBeenCalledWith('/dashboard');
  });
});

describe('LoginForm — the bot check (ADR-364)', () => {
  it('shows no widget when the instance runs no check', () => {
    render(<LoginForm />);

    expect(screen.queryByTestId('turnstile')).toBeNull();
  });

  it('shows the widget of the sign-in door when the instance runs one', () => {
    door.value = { ...door.value, siteKey: '1x00000000000000000000AA', ready: false };
    render(<LoginForm />);

    expect(screen.getByTestId('turnstile').textContent).toBe('login');
    expect(door.asked).toBe('login');
  });

  it('sends the credentials without a token once the widget could not load', async () => {
    // The sign-in door alone is « ready » with no token after a widget failure
    // (useTurnstileDoor): the API decides from its own view of Cloudflare.
    door.value = { ...door.value, siteKey: '1x00000000000000000000AA', token: null, ready: true };
    mockLogin.mockResolvedValue({});
    render(<LoginForm />);
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: 'auth.login_button' }));

    await waitFor(() =>
      expect(mockLogin).toHaveBeenCalledWith(
        'user@example.test',
        'correct horse battery',
        false,
        null
      )
    );
  });

  it('waits for the token before sending anything', async () => {
    door.value = { ...door.value, siteKey: '1x00000000000000000000AA', ready: false };
    render(<LoginForm />);
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: 'auth.login_button' }));

    await waitFor(() => expect(screen.getByText('auth.turnstile.required')).toBeTruthy());
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('sends the token with the credentials, then asks for a new one', async () => {
    door.value = {
      ...door.value,
      siteKey: '1x00000000000000000000AA',
      token: 'token-1',
      ready: true,
    };
    mockLogin.mockResolvedValue({});
    render(<LoginForm />);
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: 'auth.login_button' }));

    await waitFor(() =>
      expect(mockLogin).toHaveBeenCalledWith(
        'user@example.test',
        'correct horse battery',
        false,
        'token-1'
      )
    );
    await waitFor(() => expect(door.value.spent).toHaveBeenCalled());
  });

  it('says the check is blocked in this browser when a sign-in sent without it is refused', async () => {
    door.value = {
      ...door.value,
      siteKey: '1x00000000000000000000AA',
      token: null,
      ready: true,
      failed: true,
    };
    mockLogin.mockRejectedValue({ data: { detail: { error: 'turnstile_failed' } } });
    render(<LoginForm />);
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: 'auth.login_button' }));

    await waitFor(() => expect(screen.getByText('auth.turnstile.blocked')).toBeTruthy());
    expect(screen.queryByText('auth.errors.turnstile_failed')).toBeNull();
  });

  it('names a refused check rather than blaming the password', async () => {
    door.value = {
      ...door.value,
      siteKey: '1x00000000000000000000AA',
      token: 'token-1',
      ready: true,
    };
    mockLogin.mockRejectedValue({ data: { detail: { error: 'turnstile_failed' } } });
    render(<LoginForm />);
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: 'auth.login_button' }));

    await waitFor(() => expect(screen.getByText('auth.errors.turnstile_failed')).toBeTruthy());
    expect(screen.queryByText('auth.errors.invalid_credentials')).toBeNull();
    expect(door.value.spent).toHaveBeenCalled();
  });
});
