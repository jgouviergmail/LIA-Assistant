/** Real query/mutation hooks: a write marks the portrait stale; an HTTP failure never clears it. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { useJournals } from '../useJournals';
import type { JournalEntry, JournalPortrait, JournalSettings } from '../useJournals';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owned-journal-user' } }) }));
vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client');
  return { ...actual, default: api, apiClient: api };
});
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

const storedPortrait: JournalPortrait = {
  full: 'A current synthesis grounded in the stored source.',
  brief: 'A supported brief synthesis.',
  compiled_at: '2026-10-07T08:00:00Z',
  sources: null,
};
const source: JournalEntry = {
  id: 'owned-entry',
  theme: 'learnings',
  title: 'A grounded method',
  content: 'Compare the relevant options.',
  mood: 'reflective',
  status: 'active',
  source: 'manual',
  personality_code: null,
  char_count: 29,
  search_hints: null,
  injection_count: 0,
  last_injected_at: null,
  confidence: 'medium',
  evidence_count: 0,
  contradiction_count: 0,
  revision: 1,
  level: 'L1',
  created_at: '2026-10-07T08:00:00Z',
  updated_at: '2026-10-07T08:00:00Z',
};
function settings(): JournalSettings {
  return {
    journals_enabled: true,
    journal_consolidation_enabled: true,
    journal_consolidation_with_history: false,
    journal_max_total_chars: 50000,
    journal_context_max_chars: 2000,
    journal_max_entry_chars: 500,
    journal_context_max_results: 5,
    size_info: { total_chars: 29, max_total_chars: 50000, usage_pct: 0.058 },
    last_cost: { tokens_in: null, tokens_out: null, cost_eur: null, timestamp: null, source: null },
  };
}
let currentSettings: JournalSettings;
let failPortraitRefresh: boolean;
beforeEach(() => {
  vi.clearAllMocks();
  currentSettings = settings();
  failPortraitRefresh = false;
  api.get.mockImplementation(async (endpoint: string) => {
    if (endpoint === '/journals/portrait') {
      if (failPortraitRefresh) throw new Error('Simulated portrait read failure');
      return storedPortrait;
    }
    if (endpoint === '/journals/settings') return currentSettings;
    if (endpoint === '/journals/themes') return { themes: [] };
    return {
      entries: [source],
      total: 1,
      total_chars: 29,
      by_theme: [],
      max_total_chars: 50000,
      usage_pct: 0.058,
    };
  });
  api.delete.mockResolvedValue(undefined);
});
async function mounted() {
  const hook = renderHook(() => useJournals());
  await waitFor(() => expect(hook.result.current.portrait?.full).toBe(storedPortrait.full));
  failPortraitRefresh = true;
  return hook;
}

describe('portrait freshness after acknowledged writes', () => {
  it.each(['delete', 'deleteAll', 'create', 'update'] as const)(
    'marks the portrait stale after %s even when its GET fails, and keeps its words',
    async operation => {
      const { result } = await mounted();
      api.post.mockResolvedValue({ ...source, id: 'new-entry' });
      api.patch.mockResolvedValue({ ...source, content: 'A corrected method.', revision: 2 });
      await act(async () => {
        if (operation === 'delete') await result.current.deleteEntry(source.id);
        if (operation === 'deleteAll') await result.current.deleteAllEntries();
        if (operation === 'create')
          await result.current.createEntry({
            theme: 'learnings',
            title: 'New method',
            content: 'A new source.',
          });
        if (operation === 'update')
          await result.current.updateEntry(source.id, { content: 'A corrected method.' });
      });
      expect(result.current.portrait?.stale).toBe(true);
      expect(result.current.portrait?.full).toBe(storedPortrait.full);
      expect(result.current.portraitError).toBeInstanceOf(Error);
    }
  );

  it('trusts an exact settings invalidation receipt even when cached preferences appear unchanged', async () => {
    const { result } = await mounted();
    currentSettings = { ...settings(), portrait_invalidated: true };
    api.patch.mockResolvedValue(currentSettings);
    await act(async () => {
      await result.current.updateSettings({ journal_consolidation_with_history: false });
    });
    expect(result.current.portrait?.stale).toBe(true);
    expect(result.current.portrait?.full).toBe(storedPortrait.full);
  });

  it('keeps a valid portrait when an exact settings receipt says no invalidation', async () => {
    const { result } = await mounted();
    currentSettings = {
      ...settings(),
      journal_consolidation_with_history: true,
      portrait_invalidated: false,
    };
    api.patch.mockResolvedValue(currentSettings);
    await act(async () => {
      await result.current.updateSettings({ journal_consolidation_with_history: true });
    });
    expect(result.current.portrait?.full).toBe(storedPortrait.full);
  });

  it.each([
    [{ journal_consolidation_with_history: true }, true],
    [{ journal_consolidation_with_history: false }, false],
    [{ journal_context_max_chars: 2500 }, false],
  ] as const)(
    'uses only known changed portrait inputs for a legacy settings response %j',
    async (changes, invalidated) => {
      const { result } = await mounted();
      currentSettings = { ...settings(), ...changes };
      api.patch.mockResolvedValue(currentSettings);
      await act(async () => {
        await result.current.updateSettings(changes);
      });
      expect(result.current.portrait?.full).toBe(storedPortrait.full);
      expect(Boolean(result.current.portrait?.stale)).toBe(invalidated);
    }
  );

  it.each(['success', 'no_op', 'invalid_output'])(
    'keeps the words, marked stale only on success, when the attempt is %s and its portrait refresh fails',
    async status => {
      const { result } = await mounted();
      api.post.mockResolvedValue({ status, actions_applied: 0, duration_ms: 1500 });
      await act(async () => {
        await result.current.consolidateNow();
      });
      expect(result.current.portrait?.full).toBe(storedPortrait.full);
      expect(Boolean(result.current.portrait?.stale)).toBe(status === 'success');
      expect(result.current.portraitError).toBeInstanceOf(Error);
    }
  );

  it('marks an old portrait stale after a persisted correction even when synthesis is rejected', async () => {
    const { result } = await mounted();
    api.post.mockResolvedValue({ status: 'invalid_output', actions_applied: 0, duration_ms: 1500 });
    await act(async () => {
      await result.current.submitPortraitFeedback({
        comment: 'Correct this account understanding.',
      });
    });
    expect(result.current.portrait?.stale).toBe(true);
    expect(result.current.portrait?.full).toBe(storedPortrait.full);
  });

  it('retains prior valid data on an ordinary refresh failure and exposes that failure', async () => {
    const { result } = await mounted();
    await act(async () => {
      await result.current.refetchPortrait();
    });
    expect(result.current.portrait?.full).toBe(storedPortrait.full);
    expect(result.current.portraitError).toBeInstanceOf(Error);
  });
});
