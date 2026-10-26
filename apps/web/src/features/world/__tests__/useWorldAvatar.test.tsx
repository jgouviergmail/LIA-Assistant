import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useWorldAvatar } from '../useWorldAvatar';
import { DEFAULT_AVATAR, type AvatarView } from '../avatar-protocol';
const port = vi.hoisted(() => ({ data: undefined as unknown, acceptData: vi.fn(), refetch: vi.fn(), mutate: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: () => ({ data: port.data, acceptData: port.acceptData, refetch: port.refetch, loading: false, error: null }) }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate: port.mutate, loading: false }) }));
const owner = '11111111-1111-4111-8111-111111111111';
const other = '22222222-2222-4222-8222-222222222222';
const fixture = (owner_id = owner): AvatarView => ({
  owner_id, public_name: 'Native LIA name', needs_setup: true, needs_reset: false,
  preferences: { version: 1, revision: 0, appearance: DEFAULT_AVATAR },
});
beforeEach(() => { port.data = fixture(); port.acceptData.mockReset().mockReturnValue(true); port.refetch.mockReset(); port.mutate.mockReset(); });
it('refuses another owner, private fields and malformed scalar responses', () => {
  for (const data of [fixture(other), { ...fixture(), profile: 'PRIVATE' }, null, 0]) {
    port.data = data;
    const hook = renderHook(() => useWorldAvatar(owner, true));
    expect(hook.result.current.avatar).toBeNull();
    expect(hook.result.current.failed).toBe(true);
    hook.unmount();
  }
});
it('aborts a save when authority disappears and refuses its late result', async () => {
  let finish!: (value: unknown) => void;
  let signal: AbortSignal | undefined;
  port.mutate.mockImplementation((_url, _data, options: { signal: AbortSignal }) => {
    signal = options.signal;
    return new Promise(resolve => { finish = resolve; });
  });
  const hook = renderHook(({ enabled }) => useWorldAvatar(owner, enabled), { initialProps: { enabled: true } });
  let result!: Promise<AvatarView | null>;
  act(() => { result = hook.result.current.save({ expected_revision: 0, appearance: DEFAULT_AVATAR, consent: true, reset: false }); });
  hook.rerender({ enabled: false });
  expect(signal?.aborted).toBe(true);
  await act(async () => finish(fixture()));
  expect(await result).toBeNull();
  expect(port.acceptData).not.toHaveBeenCalled();
  hook.unmount();
});
it('returns the accepted server identity and ignores duplicate concurrent submits', async () => {
  let finish!: (value: unknown) => void;
  port.mutate.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const hook = renderHook(() => useWorldAvatar(owner, true));
  const payload = { expected_revision: 0, appearance: DEFAULT_AVATAR, consent: true as const, reset: false };
  let result!: Promise<AvatarView | null>;
  act(() => { result = hook.result.current.save(payload); });
  expect(await hook.result.current.save(payload)).toBeNull();
  const saved = { ...fixture(), needs_setup: false, preferences: { ...fixture().preferences, revision: 1 } };
  await act(async () => finish(saved));
  expect(await result).toEqual(saved);
  expect(port.acceptData).toHaveBeenCalledTimes(1);
  hook.unmount();
});
