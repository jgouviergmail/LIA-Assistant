import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, post, patch, remove, useAuth } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  remove: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, post, patch, delete: remove } };
});
import { useChannelBindings } from '../useChannelBindings';

const binding = {
  id: 'binding-one',
  channel_type: 'telegram',
  channel_user_id: 'private-one',
  channel_username: '@reader',
  is_active: true,
  created_at: '2026-10-07T00:00:00Z',
  updated_at: '2026-10-07T00:00:00Z',
};
const saved = { bindings: [binding], total: 1, telegram_bot_username: 'LIABot' };
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(saved);
});

describe('channel account lifetime and native invalidation', () => {
  it('rereads only the addressed account when a native change commits', async () => {
    const { result } = renderHook(() => useChannelBindings());
    await waitFor(() => expect(result.current.bindings).toEqual([binding]));
    get.mockResolvedValueOnce({ ...saved, bindings: [{ ...binding, is_active: false }] });
    act(() => publishApplicationResources('two', new Set(['channels'])));
    expect(get).toHaveBeenCalledTimes(1);
    act(() => publishApplicationResources('one', new Set(['channels'])));
    await waitFor(() => expect(result.current.bindings[0].is_active).toBe(false));
  });

  it('hides old bindings and refuses an obsolete OTP callback before HTTP', async () => {
    const { result, rerender } = renderHook(() => useChannelBindings());
    await waitFor(() => expect(result.current.bindings).toEqual([binding]));
    const obsolete = result.current.generateOtp;
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockImplementationOnce(() => new Promise(() => {}));
    rerender();
    expect(result.current.bindings).toEqual([]);
    await act(async () => {
      expect(await obsolete()).toBeUndefined();
    });
    expect(post).not.toHaveBeenCalled();
  });

  it('suppresses the OTP result after the account changes during its request', async () => {
    let complete:
      | ((value: {
          code: string;
          expires_in_seconds: number;
          bot_username: string;
          channel_type: string;
        }) => void)
      | undefined;
    post.mockImplementationOnce(
      () =>
        new Promise(done => {
          complete = done;
        })
    );
    const { result, rerender } = renderHook(() => useChannelBindings());
    await waitFor(() => expect(result.current.bindings).toEqual([binding]));
    let pending: ReturnType<typeof result.current.generateOtp> | undefined;
    act(() => {
      pending = result.current.generateOtp();
    });
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockResolvedValueOnce({ ...saved, bindings: [], total: 0 });
    rerender();
    await act(async () => {
      complete?.({
        code: '123456',
        expires_in_seconds: 30,
        bot_username: 'LIABot',
        channel_type: 'telegram',
      });
      expect(await pending).toBeUndefined();
    });
    expect(result.current.bindings).toEqual([]);
  });

  it('rereads after a manual toggle instead of relying on response ordering', async () => {
    patch.mockResolvedValueOnce({ id: binding.id, is_active: false });
    const { result } = renderHook(() => useChannelBindings());
    await waitFor(() => expect(result.current.bindings).toEqual([binding]));
    get.mockResolvedValueOnce({ ...saved, bindings: [{ ...binding, is_active: false }] });
    await act(async () => {
      await result.current.toggleBinding(binding.id);
    });
    expect(get).toHaveBeenCalledTimes(2);
    expect(result.current.bindings[0].is_active).toBe(false);
  });
});
