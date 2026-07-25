/**
 * useAppleConnect — validating an app-specific password and activating the
 * iCloud services in one call.
 *
 * What matters: the busy flag is released on every outcome (a stuck spinner
 * locks the whole form), and Apple's own refusal reason reaches the user —
 * "invalid app-specific password" is the single most actionable message of the
 * flow, and it used to be replaced by a generic sentence.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderHook, act, waitFor } from '@/__tests__/test-utils';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

import { ApiError } from '@/lib/api-client';

import { useAppleConnect } from '../useAppleConnect';

const ACTIVATED = {
  activated: [{ id: 'a1', connector_type: 'apple_calendar', status: 'active' }],
  deactivated: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  post.mockResolvedValue(ACTIVATED);
});

describe('useAppleConnect', () => {
  it('posts the credentials with the selected services and reports success', async () => {
    const onSuccess = vi.fn();
    const { result } = renderHook(() => useAppleConnect({ onSuccess }));

    let response: unknown;
    await act(async () => {
      response = await result.current.connect('me@icloud.com', 'abcd-efgh', ['apple_calendar']);
    });

    expect(post).toHaveBeenCalledWith('/connectors/apple/activate', {
      apple_id: 'me@icloud.com',
      app_password: 'abcd-efgh',
      services: ['apple_calendar'],
    });
    expect(response).toEqual(ACTIVATED);
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(result.current.connecting).toBe(false);
  });

  it("surfaces Apple's refusal reason and returns null", async () => {
    post.mockRejectedValue(
      new ApiError('irrelevant', 401, { detail: 'Invalid app-specific password' })
    );
    const onError = vi.fn();
    const onSuccess = vi.fn();
    const { result } = renderHook(() => useAppleConnect({ onError, onSuccess }));

    let response: unknown = 'unset';
    await act(async () => {
      response = await result.current.connect('me@icloud.com', 'bad', ['apple_calendar']);
    });

    expect(response).toBeNull();
    expect(onError).toHaveBeenCalledWith('Invalid app-specific password');
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('falls back to a generic message when the failure carries no detail', async () => {
    post.mockRejectedValue(new Error('Failed to fetch'));
    const onError = vi.fn();
    const { result } = renderHook(() => useAppleConnect({ onError }));

    await act(async () => {
      await result.current.connect('me@icloud.com', 'x', []);
    });

    expect(onError).toHaveBeenCalledWith('Failed to connect Apple services');
  });

  it('releases the busy flag even when the request fails', async () => {
    post.mockRejectedValue(new Error('down'));
    const { result } = renderHook(() => useAppleConnect());

    await act(async () => {
      await result.current.connect('me@icloud.com', 'x', []);
    });

    await waitFor(() => expect(result.current.connecting).toBe(false));
  });

  it('marks the hook busy while the call is in flight', async () => {
    let settle!: (value: typeof ACTIVATED) => void;
    post.mockReturnValue(
      new Promise<typeof ACTIVATED>(resolve => {
        settle = resolve;
      })
    );
    const { result } = renderHook(() => useAppleConnect());

    let pending!: Promise<unknown>;
    act(() => {
      pending = result.current.connect('me@icloud.com', 'x', ['apple_calendar']);
    });
    await waitFor(() => expect(result.current.connecting).toBe(true));

    await act(async () => {
      settle(ACTIVATED);
      await pending;
    });
    expect(result.current.connecting).toBe(false);
  });
});
