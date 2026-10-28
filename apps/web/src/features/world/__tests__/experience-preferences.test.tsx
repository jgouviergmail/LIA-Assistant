import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useWorldExperiencePreferences } from '../useWorldExperiencePreferences';
import { experienceViewSchema, type ExperienceView } from '../experience-protocol';

const port = vi.hoisted(() => ({
  data: undefined as unknown,
  acceptData: vi.fn(),
  refetch: vi.fn(),
  mutate: vi.fn(),
  query: vi.fn(),
}));
vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (endpoint: string) => {
    port.query(endpoint);
    return {
      data: port.data,
      acceptData: port.acceptData,
      refetch: port.refetch,
      loading: false,
      error: null,
    };
  },
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: port.mutate, loading: false }),
}));
const owner = '11111111-1111-4111-8111-111111111111';
const other = '22222222-2222-4222-8222-222222222222';
function fixture(owner_id = owner): ExperienceView {
  return {
    owner_id,
    needs_reset: false,
    preferences: {
      version: 1,
      revision: 0,
      show_route: true,
      season_mode: 'calendar',
      hemisphere: 'north',
    },
  };
}
beforeEach(() => {
  port.data = fixture();
  port.acceptData.mockReset().mockReturnValue(true);
  port.mutate.mockReset();
  port.refetch.mockReset();
  port.query.mockClear();
});
describe('private experience lifetime', () => {
  it('uses the native owner resource and retains a saved route opt-out', () => {
    port.data = { ...fixture(), preferences: { ...fixture().preferences, show_route: false } };
    const hook = renderHook(() => useWorldExperiencePreferences(owner, true));
    expect(port.query).toHaveBeenCalledWith('/world/experience');
    expect(hook.result.current.experience?.preferences.show_route).toBe(false);
  });
  it('hides wrong-owner, unsupported or malformed documents', () => {
    for (const data of [
      fixture(other),
      { ...fixture(), private: true },
      { ...fixture(), preferences: { ...fixture().preferences, version: 2 } },
    ]) {
      port.data = data;
      const hook = renderHook(() => useWorldExperiencePreferences(owner, true));
      expect(hook.result.current.experience).toBeNull();
      expect(hook.result.current.failed).toBe(true);
      hook.unmount();
    }
    expect(
      experienceViewSchema.safeParse({
        ...fixture(),
        preferences: { ...fixture().preferences, revision: true },
      }).success
    ).toBe(false);
  });
  it('preserves the last accepted preferences after a failed write', async () => {
    port.mutate.mockRejectedValue(new Error('STALE_STATE'));
    const hook = renderHook(() => useWorldExperiencePreferences(owner, true));
    await expect(
      hook.result.current.save({ expected_revision: 0, show_route: false })
    ).rejects.toThrow('STALE_STATE');
    expect(hook.result.current.experience?.preferences.show_route).toBe(true);
    expect(port.acceptData).not.toHaveBeenCalled();
  });
  it.each([
    ['account replacement', { id: other, enabled: true }],
    ['loss of authority', { id: owner, enabled: false }],
  ] as const)('aborts a late write on %s alone', async (_cause, next) => {
    let finish!: (value: unknown) => void;
    let signal: AbortSignal | undefined;
    port.mutate.mockImplementation((_url, _data, options: { signal: AbortSignal }) => {
      signal = options.signal;
      return new Promise<unknown>(resolve => {
        finish = resolve;
      });
    });
    const hook = renderHook(
      ({ id, enabled }: { id: string; enabled: boolean }) =>
        useWorldExperiencePreferences(id, enabled),
      { initialProps: { id: owner, enabled: true } }
    );
    let saved!: Promise<boolean>;
    act(() => {
      saved = hook.result.current.save({ expected_revision: 0, show_route: false });
    });
    expect(signal?.aborted).toBe(false);
    hook.rerender(next);
    expect(signal?.aborted).toBe(true);
    await act(async () => finish(fixture(next.id)));
    expect(await saved).toBe(false);
    expect(port.acceptData).not.toHaveBeenCalled();
    expect(hook.result.current.experience).toBeNull();
  });
  it('reads once per return to the tab, never on the focus that follows the visibility event', () => {
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
    const focused = vi.spyOn(document, 'hasFocus').mockReturnValue(true);
    try {
      const hook = renderHook(({ enabled }) => useWorldExperiencePreferences(owner, enabled), {
        initialProps: { enabled: true },
      });
      act(() => window.dispatchEvent(new Event('focus')));
      expect(port.refetch).not.toHaveBeenCalled();
      act(() => {
        window.dispatchEvent(new Event('blur'));
        hidden.mockReturnValue(true);
        document.dispatchEvent(new Event('visibilitychange'));
      });
      expect(port.refetch).not.toHaveBeenCalled();
      act(() => {
        hidden.mockReturnValue(false);
        document.dispatchEvent(new Event('visibilitychange'));
        window.dispatchEvent(new Event('focus'));
      });
      expect(port.refetch).toHaveBeenCalledTimes(1);
      act(() => {
        window.dispatchEvent(new Event('blur'));
        window.dispatchEvent(new Event('focus'));
      });
      expect(port.refetch).toHaveBeenCalledTimes(2);
      hook.rerender({ enabled: false });
      act(() => {
        window.dispatchEvent(new Event('blur'));
        window.dispatchEvent(new Event('focus'));
      });
      expect(port.refetch).toHaveBeenCalledTimes(2);
      hook.unmount();
    } finally {
      hidden.mockRestore();
      focused.mockRestore();
    }
  });
});
