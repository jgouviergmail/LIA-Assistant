/** Private composer text follows its discussion through switching and logout. */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { clearInputDraft, seedInputDraft, useInputDraft } from '../useInputDraft';
import { CHAT_DRAFT_STORAGE_KEY_PREFIX } from '@/lib/constants';

const owner = { id: 'owner' };
const a = { id: 'a', kind: 'secondary' as const };
const b = { id: 'b', kind: 'secondary' as const };

beforeEach(() => {
  localStorage.clear();
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

it('does not resurrect pending private text when logout is followed by unmount', () => {
  const recover = vi.fn(() => true);
  const hook = renderHook(() => useInputDraft(owner, true, a, recover));
  act(() => hook.result.current.saveDraft('pending'));
  clearInputDraft(owner.id);
  hook.unmount();
  act(() => vi.runAllTimers());
  const fresh = renderHook(() => useInputDraft(owner, true, a));
  expect(fresh.result.current.initialDraft).toBeUndefined();
  expect(recover).not.toHaveBeenCalled();
});

it.each(['loaded', 'pending', 'stored'] as const)(
  'recovers a revoked %s draft in memory',
  state => {
    const key = `${CHAT_DRAFT_STORAGE_KEY_PREFIX}${owner.id}.${a.id}`;
    if (state === 'loaded') localStorage.setItem(key, 'private A');
    const recover = vi.fn(() => true);
    const hook = renderHook(() => useInputDraft(owner, true, a, recover));
    if (state !== 'loaded') act(() => hook.result.current.saveDraft('private A'));
    if (state === 'stored') {
      act(() => vi.runAllTimers());
      expect(localStorage.getItem(key)).toBe('private A');
    }
    // Another tab confirms deletion and clears the shared key.
    localStorage.removeItem(key);
    hook.unmount();
    expect(recover).toHaveBeenCalledExactlyOnceWith('private A');
    expect(localStorage.getItem(key)).toBeNull();
  }
);

it('flushes the outgoing draft to its captured target during a debounce', () => {
  const hook = renderHook(({ target }) => useInputDraft(owner, true, target), {
    initialProps: { target: a },
  });
  act(() => hook.result.current.saveDraft('private A'));
  hook.rerender({ target: b });
  expect(hook.result.current.initialDraft).toBeUndefined();
  act(() => hook.result.current.saveDraft('private B'));
  act(() => vi.runAllTimers());
  hook.rerender({ target: a });
  expect(hook.result.current.initialDraft).toBe('private A');
  hook.rerender({ target: b });
  expect(hook.result.current.initialDraft).toBe('private B');
});

it('migrates legacy text to Main alone, including a draft seeded without a target', () => {
  localStorage.setItem(`${CHAT_DRAFT_STORAGE_KEY_PREFIX}owner`, 'legacy');
  const annex = renderHook(() => useInputDraft(owner, true, a));
  expect(annex.result.current.initialDraft).toBeUndefined();
  annex.unmount();
  seedInputDraft('owner', 'seed');
  const main = renderHook(() => useInputDraft(owner));
  expect(main.result.current.initialDraft).toBe('legacy\n\nseed');
  expect(localStorage.getItem(`${CHAT_DRAFT_STORAGE_KEY_PREFIX}owner`)).toBeNull();
});

it('clears only the sent draft, then removes every account draft at logout', () => {
  const left = renderHook(() => useInputDraft(owner, true, a));
  const right = renderHook(() => useInputDraft(owner, true, b));
  act(() => {
    left.result.current.saveDraft('A');
    right.result.current.saveDraft('B');
    vi.runAllTimers();
  });
  act(() => left.result.current.saveDraft(''));
  const readB = renderHook(() => useInputDraft(owner, true, b));
  expect(readB.result.current.initialDraft).toBe('B');
  seedInputDraft('owner-other', 'keep');
  clearInputDraft(owner.id);
  const afterLogout = renderHook(() => useInputDraft(owner, true, b));
  expect(afterLogout.result.current.initialDraft).toBeUndefined();
  const other = renderHook(() => useInputDraft({ id: 'owner-other' }));
  expect(other.result.current.initialDraft).toBe('keep');
});
