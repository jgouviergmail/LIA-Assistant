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
    onConsumed: vi.fn(),
    ...over,
  };
}

describe('useAutoSendIntent', () => {
  it('sends once when everything is ready', () => {
    const a = args();
    renderHook(props => useAutoSendIntent(props), { initialProps: a });
    expect(a.send).toHaveBeenCalledTimes(1);
    expect(a.send).toHaveBeenCalledWith(a.intent, undefined);
    expect(a.fallbackToDraft).not.toHaveBeenCalled();
  });

  it('carries the capability directive to the send (ADR-191)', () => {
    // The half that makes the 360° CERTAIN rather than merely visible.
    // Production, 2026-08-01: the sentence alone reached the planner, which
    // called the generic mail tool instead of the 0.853-scoring 360° tool.
    const directive = { capability: 'person_overview', subject: 'Paul Martin' } as const;
    const a = args({ intent: 'Point 360° sur Paul Martin', directive });

    renderHook(props => useAutoSendIntent(props), { initialProps: a });

    expect(a.send).toHaveBeenCalledWith('Point 360° sur Paul Martin', directive);
  });

  it('sends the directive of the CURRENT request, never the previous one', () => {
    const first = { capability: 'person_overview', subject: 'Marie Dupont' } as const;
    const second = { capability: 'person_overview', subject: 'Paul Martin' } as const;
    const a = args({ intent: 'Point 360° sur Marie Dupont', directive: first });
    const { rerender } = renderHook(props => useAutoSendIntent(props), { initialProps: a });

    rerender({ ...a, intent: 'Point 360° sur Paul Martin', directive: second });

    expect(a.send).toHaveBeenLastCalledWith('Point 360° sur Paul Martin', second);
  });

  it('a quota wall saves the sentence and never fires the capability', () => {
    // The draft is prose: replaying it later must not smuggle a guaranteed
    // tool call the user never re-confirmed.
    const directive = { capability: 'person_overview', subject: 'Marie' } as const;
    const a = args({ intent: 'Point 360° sur Marie', directive, isUsageBlocked: true });

    renderHook(props => useAutoSendIntent(props), { initialProps: a });

    expect(a.send).not.toHaveBeenCalled();
    expect(a.fallbackToDraft).toHaveBeenCalledWith('Point 360° sur Marie');
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

  describe('a SECOND intent is a second request', () => {
    /**
     * Production, 2026-08-01: a 360° recap on one person, then on another,
     * then on a third — three deep links, three sends, and the DATABASE holds
     * the SAME sentence three times. The consumption latch was scoped to the
     * hook instance, so once armed it refused every later intent; the page
     * meanwhile froze the value at mount. Either defect alone reproduces it.
     */
    it('sends a NEW intent that arrives after the first was consumed', () => {
      const a = args({ intent: 'Point 360° sur A' });
      const { rerender } = renderHook(props => useAutoSendIntent(props), { initialProps: a });
      expect(a.send).toHaveBeenCalledWith('Point 360° sur A', undefined);

      rerender({ ...a, intent: 'Point 360° sur B' });
      expect(a.send).toHaveBeenCalledTimes(2);
      expect(a.send).toHaveBeenLastCalledWith('Point 360° sur B', undefined);
    });

    it('sends the SAME intent again when it arrives as a fresh navigation', () => {
      // Asking twice for the same person is a legitimate act. The URL is
      // cleared between the two, so the value passes through '' — that
      // transition is what re-arms the latch.
      const a = args({ intent: 'Point 360° sur A' });
      const { rerender } = renderHook(props => useAutoSendIntent(props), { initialProps: a });
      expect(a.send).toHaveBeenCalledTimes(1);

      rerender({ ...a, intent: '' });
      rerender({ ...a, intent: 'Point 360° sur A' });
      expect(a.send).toHaveBeenCalledTimes(2);
    });

    it('still sends exactly once while the value does not change', () => {
      const a = args();
      const { rerender } = renderHook(props => useAutoSendIntent(props), { initialProps: a });
      rerender({ ...a });
      rerender({ ...a, isTyping: false });
      expect(a.send).toHaveBeenCalledTimes(1);
    });

    it('survives a page that is not ready yet, then sends', () => {
      // Production, 2026-08-01 06:30: the scope PUT succeeded five times and
      // the chat received nothing. The URL was cleared ON ARRIVAL, which won
      // the race against auth resolution — the request vanished before this
      // hook could act. The param must live until it has been CONSUMED.
      const a = args({ ready: false });
      const { rerender } = renderHook(props => useAutoSendIntent(props), { initialProps: a });
      expect(a.send).not.toHaveBeenCalled();
      expect(a.onConsumed).not.toHaveBeenCalled();

      rerender({ ...a, ready: true });
      expect(a.send).toHaveBeenCalledTimes(1);
      expect(a.onConsumed).toHaveBeenCalledTimes(1);
    });

    it('signals consumption for the quota-wall fallback too', () => {
      const a = args({ isUsageBlocked: true });
      renderHook(props => useAutoSendIntent(props), { initialProps: a });
      expect(a.fallbackToDraft).toHaveBeenCalledTimes(1);
      expect(a.onConsumed).toHaveBeenCalledTimes(1);
    });

    it('does not signal consumption while it is still waiting', () => {
      const a = args({ apiAvailable: false });
      renderHook(props => useAutoSendIntent(props), { initialProps: a });
      expect(a.onConsumed).not.toHaveBeenCalled();
    });

    it('does not resend the intent it just turned into a draft', () => {
      const a = args({ isUsageBlocked: true });
      const { rerender } = renderHook(props => useAutoSendIntent(props), { initialProps: a });
      expect(a.fallbackToDraft).toHaveBeenCalledTimes(1);

      rerender({ ...a, isUsageBlocked: false });
      expect(a.send).not.toHaveBeenCalled();
      expect(a.fallbackToDraft).toHaveBeenCalledTimes(1);
    });
  });
});
