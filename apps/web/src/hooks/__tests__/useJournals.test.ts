/**
 * useJournals — the journal entries, their settings and the compiled portrait.
 *
 * Two things make this hook different from the other CRUD ones and are pinned
 * accordingly: the optimistic updaters maintain a **character budget**
 * (`total_chars`) alongside the entry count, and the two LLM-bound operations
 * (consolidation, portrait feedback) must refresh **three** queries at once —
 * entries, settings (the cost changed) and the portrait (it was recompiled).
 * Refreshing only the entries would leave a stale cost on screen.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderHook, act } from '@/__tests__/test-utils';
import {
  mutateSpy,
  mutationResult,
  queryResult,
  setDataSpy,
  takeUpdater,
} from '@/__tests__/api-mocks';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));

import { useJournals } from '../useJournals';
import type { JournalEntry, JournalListResponse } from '@/hooks/useJournals';

function entry(over: Partial<JournalEntry> = {}): JournalEntry {
  return {
    id: 'j1',
    theme: 'self_reflection',
    title: 'Sur la patience',
    content: 'Une note.',
    mood: 'reflective',
    status: 'active',
    source: 'conversation',
    personality_code: null,
    char_count: 100,
    search_hints: null,
    injection_count: 0,
    last_injected_at: null,
    confidence: 'medium',
    evidence_count: 1,
    contradiction_count: 0,
    level: 'L1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

/** The seven mutations, in the order the hook declares them. */
const mutate = {
  create: mutateSpy(),
  update: mutateSpy(),
  remove: mutateSpy(),
  removeAll: mutateSpy(),
  settings: mutateSpy(),
  consolidate: mutateSpy(),
  feedback: mutateSpy(),
};
const ORDER = [
  mutate.create,
  mutate.update,
  mutate.remove,
  mutate.removeAll,
  mutate.settings,
  mutate.consolidate,
  mutate.feedback,
];

const setData = setDataSpy<JournalListResponse>();
const refetch = vi.fn();
const refetchSettings = vi.fn();
const refetchPortrait = vi.fn();

function cache(over: Partial<JournalListResponse> = {}): JournalListResponse {
  return {
    entries: [entry()],
    total: 1,
    by_theme: [{ theme: 'self_reflection', count: 1 }],
    total_chars: 100,
    max_total_chars: 10_000,
    usage_pct: 1,
    ...over,
  };
}

function setupWith(data: JournalListResponse | undefined) {
  useApiQuery.mockImplementation((endpoint: string) => {
    if (endpoint === '/journals') {
      return queryResult<JournalListResponse>({ data, setData, refetch });
    }
    if (endpoint === '/journals/settings') {
      return queryResult({ data: { journals_enabled: true }, refetch: refetchSettings });
    }
    if (endpoint === '/journals/portrait') {
      return queryResult({ data: { portrait: 'texte' }, refetch: refetchPortrait });
    }
    return queryResult({ data: { themes: [] } });
  });
  return renderHook(() => useJournals());
}

const setup = (data: JournalListResponse = cache()) => setupWith(data);

function applyUpdater(previous: JournalListResponse | undefined) {
  return takeUpdater<JournalListResponse>(setData)(previous);
}

beforeEach(() => {
  vi.clearAllMocks();
  let cursor = 0;
  useApiMutation.mockImplementation(() =>
    mutationResult({ mutate: ORDER[cursor++ % ORDER.length] })
  );
  Object.values(mutate).forEach(m => m.mockResolvedValue(undefined));
});

describe('useJournals — reading', () => {
  it('reads entries, settings, themes and the portrait', () => {
    setup();

    const endpoints = useApiQuery.mock.calls.map(call => call[0]);
    expect(endpoints).toEqual(
      expect.arrayContaining([
        '/journals',
        '/journals/settings',
        '/journals/themes',
        '/journals/portrait',
      ])
    );
  });

  it('exposes the list response as-is, and an empty theme list when absent', () => {
    const { result } = setup();
    // `entries` is the whole list response (counters included), not the array —
    // the consumer reads `entries.entries`. Only `themes` carries a default.
    expect(result.current.entries).toMatchObject({ total: 1, total_chars: 100 });

    const empty = setupWith(undefined);
    expect(empty.result.current.entries).toBeUndefined();
    expect(empty.result.current.themes).toEqual([]);
  });
});

describe('useJournals — writing entries', () => {
  const draft = {
    theme: 'learnings' as const,
    title: 'Nouvelle note',
    content: 'Contenu',
  };

  it('prepends the entry and adds its characters to the budget', async () => {
    mutate.create.mockResolvedValue(entry({ id: 'j2', char_count: 42 }));
    const { result } = setup();

    await act(async () => {
      await result.current.createEntry(draft);
    });

    expect(mutate.create).toHaveBeenCalledWith('/journals', draft);
    const next = applyUpdater(cache());
    expect(next?.entries.map(e => e.id)).toEqual(['j2', 'j1']);
    expect(next?.total).toBe(2);
    expect(next?.total_chars).toBe(142);
  });

  it('counts a characterless entry as zero rather than NaN', async () => {
    mutate.create.mockResolvedValue(entry({ id: 'j2', char_count: 0 }));
    const { result } = setup();

    await act(async () => {
      await result.current.createEntry(draft);
    });

    expect(applyUpdater(cache())?.total_chars).toBe(100);
  });

  it('replaces only the edited entry', async () => {
    const updated = entry({ title: 'Titre corrigé' });
    mutate.update.mockResolvedValue(updated);
    const { result } = setup();

    await act(async () => {
      await result.current.updateEntry('j1', { title: 'Titre corrigé' });
    });

    expect(mutate.update).toHaveBeenCalledWith('/journals/j1', { title: 'Titre corrigé' });
    const next = applyUpdater(cache({ entries: [entry(), entry({ id: 'j2' })], total: 2 }));
    expect(next?.entries).toEqual([updated, entry({ id: 'j2' })]);
  });

  it('gives the deleted entry its characters back', async () => {
    const { result } = setup(cache({ entries: [entry({ char_count: 60 })], total_chars: 160 }));

    await act(async () => {
      await result.current.deleteEntry('j1');
    });

    expect(mutate.remove).toHaveBeenCalledWith('/journals/j1');
    const next = applyUpdater(cache({ entries: [entry({ char_count: 60 })], total_chars: 160 }));
    expect(next?.entries).toEqual([]);
    expect(next?.total).toBe(0);
    expect(next?.total_chars).toBe(100);
  });

  it('never drives the counters below zero', async () => {
    const { result } = setup(cache({ entries: [], total: 0, total_chars: 0 }));

    await act(async () => {
      await result.current.deleteEntry('ghost');
    });

    const next = applyUpdater(cache({ entries: [], total: 0, total_chars: 0 }));
    expect(next?.total).toBe(0);
    expect(next?.total_chars).toBe(0);
  });

  it('empties the whole journal, budget and histogram included', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.deleteAllEntries();
    });

    expect(mutate.removeAll).toHaveBeenCalledWith('/journals');
    expect(applyUpdater(cache())).toMatchObject({
      entries: [],
      total: 0,
      by_theme: [],
      total_chars: 0,
      usage_pct: 0,
    });
  });

  it.each([
    ['create', (h: ReturnType<typeof useJournals>) => h.createEntry(draft)],
    ['update', (h: ReturnType<typeof useJournals>) => h.updateEntry('j1', { title: 't' })],
  ])('writes nothing when %s is refused', async (_label, run) => {
    const { result } = setup();

    await act(async () => {
      await run(result.current);
    });

    expect(setData).not.toHaveBeenCalled();
  });
});

describe('useJournals — settings', () => {
  it('reloads the settings once the change is accepted', async () => {
    mutate.settings.mockResolvedValue({ journals_enabled: false });
    const { result } = setup();

    await act(async () => {
      await result.current.updateSettings({ journals_enabled: false });
    });

    expect(mutate.settings).toHaveBeenCalledWith('/journals/settings', {
      journals_enabled: false,
    });
    expect(refetchSettings).toHaveBeenCalledTimes(1);
  });

  it('does not reload when the change was refused', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.updateSettings({ journals_enabled: false });
    });

    expect(refetchSettings).not.toHaveBeenCalled();
  });
});

describe('useJournals — LLM-bound operations', () => {
  it('refreshes entries, settings and portrait after a consolidation', async () => {
    mutate.consolidate.mockResolvedValue({ actions_applied: 3, duration_ms: 9000 });
    const { result } = setup();

    await act(async () => {
      await result.current.consolidateNow();
    });

    expect(mutate.consolidate).toHaveBeenCalledWith('/journals/consolidate', {});
    // The cost lives in the settings payload and the portrait was recompiled:
    // refreshing only the entries would leave both stale on screen.
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(refetchSettings).toHaveBeenCalledTimes(1);
    expect(refetchPortrait).toHaveBeenCalledTimes(1);
  });

  it('refreshes the same three views after portrait feedback', async () => {
    mutate.feedback.mockResolvedValue({ actions_applied: 1, duration_ms: 4000 });
    const { result } = setup();

    await act(async () => {
      await result.current.submitPortraitFeedback({ comment: 'Trop sévère' });
    });

    expect(mutate.feedback).toHaveBeenCalledWith('/journals/portrait/feedback', {
      comment: 'Trop sévère',
    });
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(refetchSettings).toHaveBeenCalledTimes(1);
    expect(refetchPortrait).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['consolidation', (h: ReturnType<typeof useJournals>) => h.consolidateNow()],
    [
      'portrait feedback',
      (h: ReturnType<typeof useJournals>) => h.submitPortraitFeedback({ comment: 'x' }),
    ],
  ])('refreshes nothing when the %s fails', async (_label, run) => {
    const { result } = setup();

    await act(async () => {
      await run(result.current);
    });

    expect(refetch).not.toHaveBeenCalled();
    expect(refetchPortrait).not.toHaveBeenCalled();
  });
});

describe('useJournals — updaters on an empty cache', () => {
  it.each([
    [
      'create',
      (h: ReturnType<typeof useJournals>) =>
        h.createEntry({ theme: 'learnings', title: 't', content: 'c' }),
    ],
    ['update', (h: ReturnType<typeof useJournals>) => h.updateEntry('j1', { title: 't' })],
    ['delete', (h: ReturnType<typeof useJournals>) => h.deleteEntry('j1')],
    ['wipe', (h: ReturnType<typeof useJournals>) => h.deleteAllEntries()],
  ])('%s leaves an empty cache untouched', async (_label, run) => {
    Object.values(mutate).forEach(m => m.mockResolvedValue(entry()));
    const { result } = setup();

    await act(async () => {
      await run(result.current);
    });

    expect(applyUpdater(undefined)).toBeUndefined();
  });
});
