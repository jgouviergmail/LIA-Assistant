/**
 * useInputDraft (UXR Lot 2, A7) — per-user persisted chat draft: debounced
 * save clamped at CHAT_INPUT_MAX_LENGTH, immediate clear on empty (a refresh
 * right after send must never resurrect the sent text), flush on unmount,
 * private-mode resilience, and the logout purge helper.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useInputDraft, clearInputDraft } from '../useInputDraft';
import { CHAT_DRAFT_STORAGE_KEY_PREFIX, CHAT_INPUT_MAX_LENGTH } from '@/lib/constants';

const KEY = `${CHAT_DRAFT_STORAGE_KEY_PREFIX}u-1`;

describe('useInputDraft', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('saves the draft after the debounce, under the per-user key', () => {
    const { result } = renderHook(() => useInputDraft({ id: 'u-1' }));

    act(() => result.current.saveDraft('Bonjour LIA'));
    expect(localStorage.getItem(KEY)).toBeNull(); // debounced — not yet

    act(() => vi.runAllTimers());
    expect(localStorage.getItem(KEY)).toBe('Bonjour LIA');
  });

  it('clamps an oversized draft at the input cap', () => {
    const { result } = renderHook(() => useInputDraft({ id: 'u-1' }));

    act(() => result.current.saveDraft('x'.repeat(CHAT_INPUT_MAX_LENGTH + 50)));
    act(() => vi.runAllTimers());

    expect(localStorage.getItem(KEY)?.length).toBe(CHAT_INPUT_MAX_LENGTH);
  });

  it('clears immediately on empty/whitespace and cancels the pending save', () => {
    localStorage.setItem(KEY, 'stale');
    const { result } = renderHook(() => useInputDraft({ id: 'u-1' }));

    act(() => result.current.saveDraft('pending text'));
    act(() => result.current.saveDraft('   '));

    expect(localStorage.getItem(KEY)).toBeNull(); // synchronous clear
    act(() => vi.runAllTimers());
    expect(localStorage.getItem(KEY)).toBeNull(); // pending write was cancelled
  });

  it('flushes a pending save on unmount (navigation must not lose keystrokes)', () => {
    const { result, unmount } = renderHook(() => useInputDraft({ id: 'u-1' }));

    act(() => result.current.saveDraft('presque parti'));
    unmount();

    expect(localStorage.getItem(KEY)).toBe('presque parti');
  });

  it('exposes the stored draft once at mount', () => {
    localStorage.setItem(KEY, 'restauré après F5');
    const { result } = renderHook(() => useInputDraft({ id: 'u-1' }));
    expect(result.current.initialDraft).toBe('restauré après F5');
  });

  it('does nothing without a user id', () => {
    const { result } = renderHook(() => useInputDraft(undefined));

    expect(result.current.initialDraft).toBeUndefined();
    act(() => result.current.saveDraft('jamais stocké'));
    act(() => vi.runAllTimers());

    expect(localStorage.length).toBe(0);
  });

  it('does nothing when disabled (future aparté mode — never persists)', () => {
    localStorage.setItem(KEY, 'préexistant');
    const { result } = renderHook(() => useInputDraft({ id: 'u-1' }, false));

    expect(result.current.initialDraft).toBeUndefined();
    act(() => result.current.saveDraft('jamais stocké'));
    act(() => vi.runAllTimers());

    expect(localStorage.getItem(KEY)).toBe('préexistant'); // untouched
  });

  it('survives a storage that throws (private mode)', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    try {
      const { result } = renderHook(() => useInputDraft({ id: 'u-1' }));
      act(() => result.current.saveDraft('x'));
      expect(() => act(() => vi.runAllTimers())).not.toThrow();
    } finally {
      setItem.mockRestore();
    }
  });

  it('clearInputDraft purges only the given user key (logout path)', () => {
    localStorage.setItem(KEY, 'brouillon');
    localStorage.setItem(`${CHAT_DRAFT_STORAGE_KEY_PREFIX}u-2`, 'autre compte');

    clearInputDraft('u-1');

    expect(localStorage.getItem(KEY)).toBeNull();
    expect(localStorage.getItem(`${CHAT_DRAFT_STORAGE_KEY_PREFIX}u-2`)).toBe('autre compte');
  });
});
