import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, patch, useAuth } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, patch } };
});
import { useJournals } from '../useJournals';

const preferences = {
  journals_enabled: true,
  journal_consolidation_enabled: true,
  journal_consolidation_with_history: false,
  journal_max_total_chars: 10000,
  journal_context_max_chars: 2000,
  journal_max_entry_chars: 300,
  journal_context_max_results: 5,
};
const portrait = { full: 'Owned portrait', brief: 'Owned', compiled_at: null, sources: null };
const entries = {
  entries: [],
  total: 0,
  by_theme: [],
  total_chars: 0,
  max_total_chars: 10000,
  usage_pct: 0,
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockImplementation((endpoint: string) =>
    Promise.resolve(
      endpoint === '/journals/settings'
        ? preferences
        : endpoint === '/journals/portrait'
          ? portrait
          : endpoint === '/journals/themes'
            ? { themes: [] }
            : entries
    )
  );
});

describe('journal observations follow the current account', () => {
  it('rereads confirmed settings, entries and portrait only for their owner', async () => {
    const { result } = renderHook(() => useJournals());
    await waitFor(() => expect(result.current.portrait?.full).toBe('Owned portrait'));
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['journals'])));
    expect(get).not.toHaveBeenCalled();
    get.mockImplementation((endpoint: string) =>
      Promise.resolve(
        endpoint === '/journals/settings'
          ? { ...preferences, journals_enabled: false }
          : endpoint === '/journals/portrait'
            ? { full: null, brief: null, compiled_at: null, sources: null }
            : entries
      )
    );
    act(() => publishApplicationResources('one', new Set(['journals'])));
    await waitFor(() => expect(result.current.settings?.journals_enabled).toBe(false));
    expect(result.current.portrait?.full).toBeNull();
    expect(get.mock.calls.map(call => call[0])).toContain('/journals');
  });

  it('hides the old account while new reads are pending and ignores its late settings callback', async () => {
    const { result, rerender } = renderHook(() => useJournals());
    await waitFor(() => expect(result.current.settings?.journals_enabled).toBe(true));
    let resolve!: (value: typeof preferences) => void;
    patch.mockReturnValue(
      new Promise<typeof preferences>(done => {
        resolve = done;
      })
    );
    let pending!: Promise<unknown>;
    act(() => {
      pending = result.current.updateSettings({ journals_enabled: false });
    });
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockReturnValue(new Promise(() => {}));
    rerender();
    expect(result.current.settings).toBeUndefined();
    expect(result.current.portrait).toBeUndefined();
    await act(async () => {
      resolve({ ...preferences, journals_enabled: false });
      await pending;
    });
    expect(result.current.settings).toBeUndefined();
    expect(result.current.portrait).toBeUndefined();
  });

  it('does not retain a potentially invalidated portrait when the native reread fails', async () => {
    const { result } = renderHook(() => useJournals());
    await waitFor(() => expect(result.current.portrait?.full).toBe('Owned portrait'));
    get.mockRejectedValue(new Error('Source temporarily unavailable'));
    act(() => publishApplicationResources('one', new Set(['journals'])));
    await waitFor(() => expect(result.current.portraitError).toBeInstanceOf(Error));
    expect(result.current.portrait?.full).toBeNull();
  });
});
