/**
 * The forgot-password page. Its answer never says whether an address has an
 * account — every outcome shows the same « check your mailbox » screen — with
 * ONE exception: a refused or unavailable bot check (ADR-364) is about the
 * visitor, not the address, so the form stays and says why.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ apiClient: { post }, default: { post } }));

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
vi.mock('@/components/auth/TurnstileWidget', () => ({
  TurnstileWidget: ({ action }: { action: string }) => <div data-testid="turnstile">{action}</div>,
}));

import ForgotPasswordPage from '../page';

const EMAIL = 'auth.forgot_password.email_label';
const SUBMIT = 'auth.forgot_password.submit';

async function submit(user: ReturnType<typeof renderWithProviders>['user']) {
  await user.type(screen.getByLabelText(EMAIL), 'person@example.com');
  await user.click(screen.getByRole('button', { name: SUBMIT }));
}

beforeEach(() => {
  post.mockReset();
  door.value = {
    ...door.value,
    siteKey: null,
    token: null,
    ready: true,
    failed: false,
    spent: vi.fn(),
  };
});

describe('ForgotPasswordPage', () => {
  it('shows the same confirmation whatever the address, and sends no header without a check', async () => {
    post.mockResolvedValue({});
    const { user } = renderWithProviders(<ForgotPasswordPage />);

    await submit(user);

    expect(await screen.findByText('auth.forgot_password.success_title')).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith(
      '/auth/request-password-reset',
      { email: 'person@example.com' },
      undefined
    );
    expect(screen.queryByTestId('turnstile')).toBeNull();
  });

  it('still shows the confirmation when the request fails for another reason', async () => {
    post.mockRejectedValue(new Error('network down'));
    const { user } = renderWithProviders(<ForgotPasswordPage />);

    await submit(user);

    expect(await screen.findByText('auth.forgot_password.success_title')).toBeInTheDocument();
  });

  it('waits for the bot check before sending anything', async () => {
    door.value = { ...door.value, siteKey: '1x00000000000000000000AA', ready: false };
    const { user } = renderWithProviders(<ForgotPasswordPage />);

    expect(screen.getByTestId('turnstile').textContent).toBe('password_reset');
    expect(door.asked).toBe('password_reset');
    await submit(user);

    expect(await screen.findByText('auth.turnstile.required')).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('says the check could not load rather than « wait » when the widget failed', async () => {
    door.value = { ...door.value, siteKey: '1x00000000000000000000AA', ready: false, failed: true };
    const { user } = renderWithProviders(<ForgotPasswordPage />);

    await submit(user);

    expect(await screen.findByText('auth.turnstile.load_failed')).toBeInTheDocument();
    expect(screen.queryByText('auth.turnstile.required')).toBeNull();
    expect(post).not.toHaveBeenCalled();
  });

  it('sends the token of the reset door', async () => {
    door.value = {
      ...door.value,
      siteKey: '1x00000000000000000000AA',
      token: 'token-1',
      ready: true,
    };
    post.mockResolvedValue({});
    const { user } = renderWithProviders(<ForgotPasswordPage />);

    await submit(user);

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/auth/request-password-reset',
        { email: 'person@example.com' },
        { headers: { 'X-LIA-Turnstile-Response': 'token-1' } }
      )
    );
    expect(door.value.spent).toHaveBeenCalled();
  });

  it('keeps the form and says why when the bot check refuses', async () => {
    door.value = {
      ...door.value,
      siteKey: '1x00000000000000000000AA',
      token: 'token-1',
      ready: true,
    };
    post.mockRejectedValue({ data: { detail: { error: 'turnstile_failed' } } });
    const { user } = renderWithProviders(<ForgotPasswordPage />);

    await submit(user);

    expect(await screen.findByText('auth.errors.turnstile_failed')).toBeInTheDocument();
    expect(screen.queryByText('auth.forgot_password.success_title')).toBeNull();
    expect(screen.getByRole('button', { name: SUBMIT })).toBeEnabled();
    expect(door.value.spent).toHaveBeenCalled();
  });
});
