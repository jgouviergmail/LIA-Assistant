/**
 * useAutoSendIntent (QW-24, ADR-173) — the `?intent=` auto-send contract.
 *
 * What must hold:
 *  - sends EXACTLY once when ready (StrictMode double-effects included);
 *  - waits for the API / a streaming turn, then sends on the state flip;
 *  - a usage-blocked session falls back to the draft (saved, never sent,
 *    never retried once consumed);
 *  - no intent, no work.
 */

import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { StrictMode } from 'react';

import { useAutoSendIntent, type UseAutoSendIntentArgs } from '../useAutoSendIntent';

function args(over: Partial<UseAutoSendIntentArgs> = {}): UseAutoSendIntentArgs {
  return {
    intent: 'Résume le mail « X »',
    ready: true,
    apiAvailable: true,
    isTyping: false,
    isUsageBlocked: false,
    send: vi.fn(),
    fallbackToDraft: vi.fn(),
    ...over,
  };
}

describe('useAutoSendIntent', () => {
  it('sends once when everything is ready', () => {
    const a = args();
    renderHook(props => useAutoSendIntent(props), { initialProps: a });
    expect(a.send).toHaveBeenCalledTimes(1);
    expect(a.send).toHaveBeenCalledWith(a.intent);
    expect(a.fallbackToDraft).not.toHaveBeenCalled();
  });

  it('sends once even under StrictMode double effects', () => {
    const a = args();
    renderHook(props => useAutoSendIntent(props), {
      initialProps: a,
      wrapper: StrictMode,
    });
    expect(a.send).toHaveBeenCalledTimes(1);
  });

  it('waits while a turn is streaming, then sends on the flip', () => {
    const a = args({ isTyping: true });
    const { rerender } = renderHook(props => useAutoSendIntent(props), { initialProps: a });
    expect(a.send).not.toHaveBeenCalled();

    rerender({ ...a, isTyping: false });
    expect(a.send).toHaveBeenCalledTimes(1);
  });

  it('waits for the API to come back', () => {
    const a = args({ apiAvailable: false });
    const { rerender } = renderHook(props => useAutoSendIntent(props), { initialProps: a });
    expect(a.send).not.toHaveBeenCalled();

    rerender({ ...a, apiAvailable: true });
    expect(a.send).toHaveBeenCalledTimes(1);
  });

  it('degrades to the draft behind a quota wall — and never retries after', () => {
    const a = args({ isUsageBlocked: true });
    const { rerender } = renderHook(props => useAutoSendIntent(props), { initialProps: a });
    expect(a.fallbackToDraft).toHaveBeenCalledTimes(1);
    expect(a.send).not.toHaveBeenCalled();

    // Even if the wall lifts later, the intent was consumed as a draft.
    rerender({ ...a, isUsageBlocked: false });
    expect(a.send).not.toHaveBeenCalled();
  });

  it('does nothing without an intent or before auth resolves', () => {
    const empty = args({ intent: '' });
    renderHook(props => useAutoSendIntent(props), { initialProps: empty });
    expect(empty.send).not.toHaveBeenCalled();

    const notReady = args({ ready: false });
    renderHook(props => useAutoSendIntent(props), { initialProps: notReady });
    expect(notReady.send).not.toHaveBeenCalled();
  });
});
