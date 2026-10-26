import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useWorldHome } from '../useWorldHome';
import type { HomeView } from '../home-protocol';

const port = vi.hoisted(() => ({
  data: undefined as unknown,
  acceptData: vi.fn(),
  refetch: vi.fn(),
  mutate: vi.fn(),
}));
vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: () => ({
    data: port.data,
    acceptData: port.acceptData,
    refetch: port.refetch,
    loading: false,
    error: null,
  }),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: port.mutate, loading: false }),
}));
const owner = '11111111-1111-4111-8111-111111111111';
const other = '22222222-2222-4222-8222-222222222222';
function fixture(owner_id = owner): HomeView {
  return {
    owner_id,
    needs_reset: false,
    preferences: { version: 1, revision: 0, palette: 'auto' },
    decoration: {
      automatic_palette: 'clay',
      palette: 'clay',
    },
  };
}
beforeEach(() => {
  port.data = fixture();
  port.acceptData.mockReset().mockReturnValue(true);
  port.mutate.mockReset();
  port.refetch.mockReset();
});

describe('owner home response fencing', () => {
  it('never exposes a different owner, unknown fields or unsupported catalogue values', () => {
    for (const data of [
      null,
      0,
      fixture(other),
      { ...fixture(), memories: ['private'] },
      { ...fixture(), decoration: { ...fixture().decoration, palette: 'injected-css' } },
    ]) {
      port.data = data;
      const hook = renderHook(() => useWorldHome(owner, true));
      expect(hook.result.current.home).toBeNull();
      expect(hook.result.current.failed).toBe(true);
      hook.unmount();
    }
  });
  it('clears the visible skin when world authority is lost', () => {
    const hook = renderHook(({ enabled }) => useWorldHome(owner, enabled), {
      initialProps: { enabled: true },
    });
    expect(hook.result.current.home?.owner_id).toBe(owner);
    hook.rerender({ enabled: false });
    expect(hook.result.current.home).toBeNull();
    expect(hook.result.current.failed).toBe(false);
    hook.unmount();
  });
  it('aborts an old save and refuses its late result after an account switch', async () => {
    let finish!: (value: unknown) => void;
    let signal: AbortSignal | undefined;
    port.mutate.mockImplementation((_url, _data, options: { signal: AbortSignal }) => {
      signal = options.signal;
      return new Promise<unknown>(resolve => {
        finish = resolve;
      });
    });
    const hook = renderHook(({ id }) => useWorldHome(id, true), { initialProps: { id: owner } });
    let accepted!: Promise<boolean>;
    act(() => {
      accepted = hook.result.current.save({
        expected_revision: 0,
        palette: 'sage',
      });
    });
    hook.rerender({ id: other });
    expect(signal?.aborted).toBe(true);
    expect(hook.result.current.home).toBeNull();
    // A real account query answers asynchronously after the new lifetime owns
    // the effect. Do not inject its response before that effect has run.
    port.data = fixture(other);
    hook.rerender({ id: other });
    await act(async () => finish(fixture()));
    expect(await accepted).toBe(false);
    expect(port.acceptData).not.toHaveBeenCalled();
    expect(hook.result.current.home?.owner_id).toBe(other);
    hook.unmount();
  });
  it('memoizes an unchanged response instead of resetting the renderer on every UI tick', () => {
    const hook = renderHook(() => useWorldHome(owner, true));
    const initial = hook.result.current.home;
    hook.rerender();
    expect(hook.result.current.home).toBe(initial);
    hook.unmount();
  });
});
