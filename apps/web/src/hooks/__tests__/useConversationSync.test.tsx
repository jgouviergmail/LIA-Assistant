/**
 * useConversationSync — the chat's sync controller, wired (ADR-320).
 *
 * The controller's rules are pinned in `lib/__tests__/chat-sync.test.ts`; this
 * suite pins the wiring: the tab's own asks (foreground, online), the resume
 * once the thread is free, and a controller that survives StrictMode's double
 * mount — created during render and disposed by the first unmount, it would be
 * dead in development.
 */

import { StrictMode, type ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { readerBusy, useConversationSync } from '@/hooks/useConversationSync';
import type { Message } from '@/types/chat';

const row: Message = {
  id: 'a',
  role: 'assistant',
  content: 'a',
  timestamp: new Date('2026-09-25T10:00:00Z'),
  metadata: { message_db_id: 'a' },
};

function options(overrides: Partial<Parameters<typeof useConversationSync>[0]> = {}) {
  return {
    enabled: true,
    blocked: false,
    messages: [row],
    readNewestPage: vi.fn(async () => ({ messages: [row] })),
    mergeServerPage: vi.fn(),
    onPageReplaced: vi.fn(),
    onReset: vi.fn(),
    ...overrides,
  };
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
}

afterEach(() => {
  setVisibility('visible');
  document.body.innerHTML = '';
  document.getSelection()?.removeAllRanges();
});

describe('useConversationSync — the tab asks on its own', () => {
  it('reads the newest page when the tab comes back to the foreground', async () => {
    const opts = options();
    renderHook(() => useConversationSync(opts));

    setVisibility('visible');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(() => expect(opts.mergeServerPage).toHaveBeenCalledWith([row]));
  });

  it('ignores the tab going to the background', () => {
    const opts = options();
    renderHook(() => useConversationSync(opts));

    setVisibility('hidden');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(opts.readNewestPage).not.toHaveBeenCalled();
  });

  it('reads the newest page when the device is back online', async () => {
    const opts = options();
    renderHook(() => useConversationSync(opts));

    act(() => {
      window.dispatchEvent(new Event('online'));
    });

    await waitFor(() => expect(opts.readNewestPage).toHaveBeenCalledTimes(1));
  });
});

describe('useConversationSync — a busy thread', () => {
  it('runs what was asked once the thread is free', async () => {
    const opts = options({ blocked: true });
    const { result, rerender } = renderHook(props => useConversationSync(props), {
      initialProps: opts,
    });

    act(() => result.current.requestSync('signal'));
    expect(opts.readNewestPage).not.toHaveBeenCalled();

    rerender({ ...opts, blocked: false });

    await waitFor(() => expect(opts.mergeServerPage).toHaveBeenCalledTimes(1));
  });
});

describe('useConversationSync — StrictMode', () => {
  it('still syncs after the double mount of development', async () => {
    const opts = options();
    const { result } = renderHook(() => useConversationSync(opts), {
      wrapper: ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>,
    });

    act(() => result.current.requestSync('signal'));

    await waitFor(() => expect(opts.mergeServerPage).toHaveBeenCalledTimes(1));
  });
});

describe('readerBusy', () => {
  it('is busy while text of the page is selected', () => {
    document.body.innerHTML = '<p id="p">Some words</p>';
    const range = document.createRange();
    range.selectNodeContents(document.getElementById('p') as HTMLElement);
    document.getSelection()?.addRange(range);

    expect(readerBusy()).toBe(true);
  });

  it('is busy while a menu is open', () => {
    document.body.innerHTML = '<div role="menu" data-state="open"></div>';

    expect(readerBusy()).toBe(true);
  });

  it('is free otherwise — a closed menu included', () => {
    document.body.innerHTML = '<div role="menu" data-state="closed"></div>';

    expect(readerBusy()).toBe(false);
  });
});
