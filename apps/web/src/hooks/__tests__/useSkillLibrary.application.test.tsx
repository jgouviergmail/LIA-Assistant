import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import { useLibraryInstalled, useLibrarySearch } from '../useSkillLibrary';

const { get, useAuth } = vi.hoisted(() => ({ get: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get } };
});

beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue({ items: [{ name: 'owned' }], portal: 'skills_sh' });
});

describe('library reads follow committed skills and the current account', () => {
  it.each(['installed', 'search'] as const)('refreshes only the owner of %s', async kind => {
    const { result } = renderHook(() => kind === 'installed' ? useLibraryInstalled(true) : useLibrarySearch('pdf'));
    await waitFor(() => expect(result.current.data).toBeDefined());
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['skills'])));
    expect(get).not.toHaveBeenCalled();
    act(() => publishApplicationResources('one', new Set(['skills'])));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
  });

  it('hides prior installations while the next account loads', async () => {
    const { result, rerender } = renderHook(() => useLibraryInstalled(true));
    await waitFor(() => expect(result.current.data).toBeDefined());
    get.mockImplementation(() => new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it('retains search parameters across committed refresh and revisions', async () => {
    const { result, rerender } = renderHook(({ revision }) => useLibrarySearch('literal query', revision), { initialProps: { revision: 0 } });
    await waitFor(() => expect(result.current.data).toBeDefined());
    act(() => publishApplicationResources('one', new Set(['skills'])));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    rerender({ revision: 1 });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    expect(get.mock.calls.every(call => call[1].params.q === 'literal query')).toBe(true);
  });

  it('does not read for a missing account or disabled installed panel', async () => {
    useAuth.mockReturnValue({ user: null });
    renderHook(() => useLibraryInstalled(true));
    renderHook(() => useLibrarySearch('pdf'));
    await act(async () => { await Promise.resolve(); });
    expect(get).not.toHaveBeenCalled();
  });
});
