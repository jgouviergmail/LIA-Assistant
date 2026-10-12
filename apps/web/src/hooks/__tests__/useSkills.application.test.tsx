import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import type { SkillListResponse } from '../useSkills';

const { get, useAuth } = vi.hoisted(() => ({ get: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get } };
});
import { useSkills } from '../useSkills';

const saved: SkillListResponse = {
  skills: [
    {
      name: 'owned',
      description: 'Owned skill',
      descriptions: null,
      scope: 'user',
      category: null,
      priority: 50,
      always_loaded: false,
      has_scripts: false,
      has_plan_template: false,
      enabled_for_user: true,
    },
  ],
  total: 1,
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(saved);
});

describe('personal skill changes and queries belong to their current account', () => {
  it('refreshes only the committed owner and retains filters', async () => {
    const { result } = renderHook(() => useSkills());
    await waitFor(() => expect(result.current.total).toBe(1));
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['skills'])));
    expect(get).not.toHaveBeenCalled();
    act(() => publishApplicationResources('one', new Set(['skills'])));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    expect(get.mock.calls[0][0]).toBe('/skills');
  });

  it('hides the previous account while a new owned request is pending', async () => {
    const { result, rerender } = renderHook(() => useSkills());
    await waitFor(() => expect(result.current.total).toBe(1));
    let resolve: (value: SkillListResponse) => void = () => {};
    get.mockImplementation(
      () =>
        new Promise<SkillListResponse>(accept => {
          resolve = accept;
        })
    );
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.total).toBe(0);
    expect(result.current.skills).toEqual([]);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await act(async () => {
      resolve({ ...saved, total: 2 });
    });
    await waitFor(() => expect(result.current.total).toBe(2));
  });

  it('never queries an unavailable account', async () => {
    useAuth.mockReturnValue({ user: null });
    renderHook(() => useSkills());
    await act(async () => {
      await Promise.resolve();
    });
    expect(get).not.toHaveBeenCalled();
  });

  it('exposes a failed initial read instead of an endless loading state', async () => {
    get.mockRejectedValue(new Error('Controlled query failure'));
    const { result } = renderHook(() => useSkills());
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.loading).toBe(false);
  });
});
