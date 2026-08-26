/**
 * The page a native shell lands on after a provider sign-in.
 *
 * It spends a single-use code against a verifier only this WebView holds. Three
 * properties matter and are pinned here: the code is spent exactly once even
 * when React runs the effect twice, an unfinished second factor leads to the
 * code step rather than the dashboard, and every failure — a missing code, a
 * missing verifier, a refused exchange — ends in the same recoverable screen
 * instead of a spinner that never stops.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { completeNativeSignIn } = vi.hoisted(() => ({ completeNativeSignIn: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ completeNativeSignIn }),
}));

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push }),
}));

const { searchParams } = vi.hoisted(() => ({ searchParams: new URLSearchParams() }));
vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParams,
}));

const { takeNativeVerifier } = vi.hoisted(() => ({ takeNativeVerifier: vi.fn() }));
vi.mock('@/lib/native/shell', () => ({ takeNativeVerifier }));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import NativeAuthPage from '../page';

function arrive(query: string) {
  searchParams.forEach((_, key) => searchParams.delete(key));
  new URLSearchParams(query).forEach((value, key) => searchParams.set(key, value));
}

beforeEach(() => {
  vi.clearAllMocks();
  arrive('');
});

describe('native sign-in landing', () => {
  it('spends the code and reaches the dashboard', async () => {
    arrive('code=handoff-123');
    takeNativeVerifier.mockReturnValue('verifier-abc');
    completeNativeSignIn.mockResolvedValue({ mfaRequired: false });

    renderWithProviders(<NativeAuthPage />);

    await waitFor(() =>
      expect(completeNativeSignIn).toHaveBeenCalledWith('handoff-123', 'verifier-abc')
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith('/dashboard'));
  });

  it('goes to the code step when a second factor is still owed', async () => {
    arrive('code=handoff-123');
    takeNativeVerifier.mockReturnValue('verifier-abc');
    completeNativeSignIn.mockResolvedValue({ mfaRequired: true });

    renderWithProviders(<NativeAuthPage />);

    await waitFor(() => expect(push).toHaveBeenCalledWith('/login?mfa=1'));
  });

  it('spends the code once even if the effect runs twice', async () => {
    arrive('code=handoff-123');
    takeNativeVerifier.mockReturnValue('verifier-abc');
    completeNativeSignIn.mockResolvedValue({ mfaRequired: false });

    const { rerender } = renderWithProviders(<NativeAuthPage />);
    rerender(<NativeAuthPage />);

    await waitFor(() => expect(completeNativeSignIn).toHaveBeenCalledTimes(1));
  });

  it('offers a way back when no code arrived', async () => {
    arrive('');

    renderWithProviders(<NativeAuthPage />);

    expect(await screen.findByText('auth.oauth.error_message')).toBeInTheDocument();
    expect(completeNativeSignIn).not.toHaveBeenCalled();
  });

  it('offers a way back when no sign-in was in flight', async () => {
    arrive('code=handoff-123');
    takeNativeVerifier.mockReturnValue(null);

    renderWithProviders(<NativeAuthPage />);

    expect(await screen.findByText('auth.oauth.error_message')).toBeInTheDocument();
    // The code was never presented: without the verifier it could not be spent
    // anyway, and burning it would only cost the user a retry.
    expect(completeNativeSignIn).not.toHaveBeenCalled();
  });

  it('offers a way back when the exchange is refused', async () => {
    arrive('code=handoff-123');
    takeNativeVerifier.mockReturnValue('verifier-abc');
    completeNativeSignIn.mockRejectedValue(new Error('401'));

    renderWithProviders(<NativeAuthPage />);

    expect(await screen.findByText('auth.oauth.error_message')).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it('shows progress while the exchange is in flight', async () => {
    arrive('code=handoff-123');
    takeNativeVerifier.mockReturnValue('verifier-abc');
    completeNativeSignIn.mockReturnValue(new Promise(() => {}));

    renderWithProviders(<NativeAuthPage />);

    expect(await screen.findByText('auth.oauth.connecting')).toBeInTheDocument();
  });
});
