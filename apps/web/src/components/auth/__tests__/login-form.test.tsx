/**
 * LoginForm — accessible names and control states (audit F012).
 *
 * The remember-me checkbox is queried BY ROLE AND NAME (not by test-id or
 * class), which proves the programmatic label association end to end:
 * label[htmlFor] + aria-labelledby → accessible name. Covers nominal toggle,
 * the disabled state while a login is in flight, the error state after a
 * rejected login, and keyboard focusability.
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
      expect(mockLogin).toHaveBeenCalledWith('user@example.test', 'correct horse battery', true)
    );
    expect(mockPush).toHaveBeenCalledWith('/dashboard');
  });
});
