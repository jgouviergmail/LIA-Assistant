/**
 * When the board's figures are read again: whenever the board under them was
 * read or written, and for no other reason — a re-render is no reason to ask.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, renderHook } from '@testing-library/react';

import { makeTicket } from '@/__tests__/factories';
import { useBoardGlance, useBoardReads } from '@/components/workboard/useBoardGlance';
import { useWorkboardLanesStore } from '@/stores/workboardLanesStore';
import type { TicketRow } from '@/types/workboard';

const stamps = vi.hoisted(() => [] as string[]);
vi.mock('@/hooks/useWorkboardSummary', () => ({
  useWorkboardSummary: (_enabled: boolean, stamp: string) => {
    stamps.push(stamp);
    return { summary: undefined, loading: false, error: false };
  },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'me' } }) }));

beforeEach(() => {
  stamps.length = 0;
  window.localStorage.clear();
  useWorkboardLanesStore.setState({ collapsed: [], summaryOpen: null });
});

describe('useBoardReads', () => {
  it('counts nothing while the same rows are drawn again', () => {
    const rows = [makeTicket({ id: 't1' })];
    const hook = renderHook(({ current }) => useBoardReads(current), {
      initialProps: { current: rows },
    });
    const before = hook.result.current;

    hook.rerender({ current: rows });
    hook.rerender({ current: rows });

    expect(hook.result.current).toBe(before);
  });

  it('counts a payload that changed nothing: new rows mean the board was read', () => {
    // What no count of the page says: a due time that passed, a category
    // renamed, a ticket handed to LIA from another device.
    const row = makeTicket({ id: 't1' });
    const hook = renderHook(({ current }) => useBoardReads(current), {
      initialProps: { current: [row] },
    });
    const before = hook.result.current;

    hook.rerender({ current: [row] });
    expect(hook.result.current).toBe(before + 1);
    hook.rerender({ current: [row] });
    expect(hook.result.current).toBe(before + 2);
  });
});

describe('useBoardGlance — when the figures are read again', () => {
  function Host({ revision, rows }: { revision: number; rows: TicketRow[] }) {
    return useBoardGlance({
      lng: 'fr',
      board: { tickets: rows, firstLoad: false },
      revision,
      wide: true,
      embedded: false,
      onFilters: () => {},
    });
  }
  const last = () => stamps.at(-1);

  it('keeps its stamp while nothing was read or written', () => {
    const rows: TicketRow[] = [];
    const view = render(<Host revision={0} rows={rows} />);
    const before = last();

    view.rerender(<Host revision={0} rows={rows} />);

    expect(before).toBeDefined();
    expect(last()).toBe(before);
  });

  it('moves its stamp when the board was read again, whatever the payload held', () => {
    const view = render(<Host revision={0} rows={[]} />);
    const before = last();

    view.rerender(<Host revision={0} rows={[]} />);

    expect(last()).not.toBe(before);
  });

  it('moves its stamp after a write that succeeded, even one the rows do not show', () => {
    // A ticket the page does not carry — opened by its link under a filter
    // that hides it — handed to LIA: « with LIA » moved, and no row did.
    const rows: TicketRow[] = [];
    const view = render(<Host revision={0} rows={rows} />);
    const before = last();

    view.rerender(<Host revision={1} rows={rows} />);

    expect(last()).not.toBe(before);
  });
});
