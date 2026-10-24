/**
 * useTurnstileDoor — what a password form needs from the bot check (ADR-364):
 * whether the instance runs one, the token it holds, whether it may submit, and
 * a way to start over once a submit spent the token.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

const { useAuthFeatures } = vi.hoisted(() => ({ useAuthFeatures: vi.fn() }));
vi.mock('@/hooks/useWebAuthn', () => ({ useAuthFeatures }));

import { useTurnstileDoor } from '../useTurnstileDoor';

function features(siteKey: string | null | undefined) {
  return {
    features:
      siteKey === undefined
        ? undefined
        : {
            mfa_enabled: false,
            federated_signin_enabled: true,
            terms_required: false,
            terms_version: '',
            turnstile_site_key: siteKey,
          },
    loading: false,
  };
}

beforeEach(() => useAuthFeatures.mockReset());

describe('useTurnstileDoor', () => {
  it('asks for nothing when the instance runs no bot check', () => {
    useAuthFeatures.mockReturnValue(features(null));

    const { result } = renderHook(() => useTurnstileDoor('login'));

    expect(result.current.siteKey).toBeNull();
    expect(result.current.ready).toBe(true);
    expect(result.current.token).toBeNull();
  });

  it('asks for nothing while the capabilities are still loading', () => {
    useAuthFeatures.mockReturnValue(features(undefined));

    expect(renderHook(() => useTurnstileDoor('login')).result.current.ready).toBe(true);
  });

  it('waits for a token when the instance runs one', () => {
    useAuthFeatures.mockReturnValue(features('1x00000000000000000000AA'));

    const { result } = renderHook(() => useTurnstileDoor('login'));
    expect(result.current.siteKey).toBe('1x00000000000000000000AA');
    expect(result.current.ready).toBe(false);

    act(() => result.current.onToken('token-1'));
    expect(result.current.ready).toBe(true);
    expect(result.current.token).toBe('token-1');
  });

  it('lets the sign-in go without a token once the widget could not load', () => {
    // Cloudflare down reaches the browser too; the API then decides from its own
    // view of Cloudflare (ADR-364): only the sign-in proceeds during an outage.
    useAuthFeatures.mockReturnValue(features('1x00000000000000000000AA'));
    const { result } = renderHook(() => useTurnstileDoor('login'));

    act(() => result.current.onFailure());

    expect(result.current.ready).toBe(true);
    expect(result.current.token).toBeNull();
  });

  it.each(['register', 'password_reset'] as const)(
    'keeps the %s door waiting when the widget could not load',
    action => {
      useAuthFeatures.mockReturnValue(features('1x00000000000000000000AA'));
      const { result } = renderHook(() => useTurnstileDoor(action));

      act(() => result.current.onFailure());

      expect(result.current.ready).toBe(false);
    }
  );

  it('says whether the widget could not load', () => {
    useAuthFeatures.mockReturnValue(features('1x00000000000000000000AA'));
    const { result } = renderHook(() => useTurnstileDoor('register'));
    expect(result.current.failed).toBe(false);

    act(() => result.current.onFailure());
    expect(result.current.failed).toBe(true);

    act(() => result.current.onToken('token-1'));
    expect(result.current.failed).toBe(false);
  });

  it('forgets the failure once the widget produces a token', () => {
    useAuthFeatures.mockReturnValue(features('1x00000000000000000000AA'));
    const { result } = renderHook(() => useTurnstileDoor('login'));
    act(() => result.current.onFailure());

    act(() => result.current.onToken('token-1'));
    act(() => result.current.onToken(null));

    expect(result.current.ready).toBe(false);
  });

  it('starts over once a submit spent the token', () => {
    useAuthFeatures.mockReturnValue(features('1x00000000000000000000AA'));
    const { result } = renderHook(() => useTurnstileDoor('login'));
    act(() => result.current.onToken('token-1'));

    act(() => result.current.spent());

    expect(result.current.resetSignal).toBe(1);
  });
});
