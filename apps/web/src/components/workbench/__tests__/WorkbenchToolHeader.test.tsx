/**
 * A tool's heading and its re-read (ADR-369): the person's button, and the
 * return to the page after a while, which nobody asked for.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { act, fireEvent, renderWithProviders, screen } from '@/__tests__/test-utils';
import { WORKBENCH_RETURN_REREAD_MIN_MS } from '@/lib/workbench/tools';

import { WorkbenchActionsSlot, WorkbenchToolHeader } from '../WorkbenchToolHeader';

const REFRESH = 'workbench.states.refresh';

function header(onRefresh?: (options: { unasked: boolean }) => Promise<void>) {
  return renderWithProviders(<WorkbenchToolHeader lng="en" tool="mail" onRefresh={onRefresh} />);
}

function hiddenPage(hidden: boolean) {
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue(hidden ? 'hidden' : 'visible');
}

function comeBack(after: number) {
  vi.setSystemTime(Date.now() + after);
  act(() => {
    window.dispatchEvent(new Event('focus'));
  });
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  hiddenPage(false);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('WorkbenchToolHeader — the row of the tools', () => {
  it('keeps one heading for the page, its words said by the open pill', () => {
    header();

    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading).toHaveClass('sr-only');
    expect(heading).toHaveTextContent('workbench.tools.mail.label');
  });

  it('sets its actions in the row of the tools, beside the pills', () => {
    const slot = document.createElement('div');
    document.body.append(slot);

    renderWithProviders(
      <WorkbenchActionsSlot.Provider value={slot}>
        <WorkbenchToolHeader lng="en" tool="mail" onRefresh={vi.fn()} />
      </WorkbenchActionsSlot.Provider>
    );

    expect(slot.querySelector('button')).toHaveAccessibleName(REFRESH);
    slot.remove();
  });
});

describe('WorkbenchToolHeader — re-reading', () => {
  it('offers nothing where the screen has nothing to re-read', () => {
    header();

    expect(screen.queryByRole('button', { name: REFRESH })).toBeNull();
  });

  it('re-reads when asked, saying it was', async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    header(onRefresh);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: REFRESH }));
    });

    expect(onRefresh).toHaveBeenCalledExactlyOnceWith({ unasked: false });
  });

  it('takes one ask at a time, the button saying it is busy', async () => {
    let answer!: () => void;
    const onRefresh = vi.fn(
      () =>
        new Promise<void>(resolve => {
          answer = resolve;
        })
    );
    header(onRefresh);
    const button = screen.getByRole('button', { name: REFRESH });

    await act(async () => {
      fireEvent.click(button);
    });
    expect(button).toHaveAttribute('aria-busy', 'true');
    await act(async () => {
      fireEvent.click(button);
    });
    expect(onRefresh).toHaveBeenCalledTimes(1);

    await act(async () => answer());
    expect(button).not.toHaveAttribute('aria-busy', 'true');
  });

  it('re-reads on a return after a while, saying nobody asked', () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    header(onRefresh);

    comeBack(WORKBENCH_RETURN_REREAD_MIN_MS);

    expect(onRefresh).toHaveBeenCalledExactlyOnceWith({ unasked: true });
  });

  it('leaves a quick return alone', () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    header(onRefresh);

    comeBack(WORKBENCH_RETURN_REREAD_MIN_MS - 1);

    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('re-reads once, whichever signals the return sends', () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    header(onRefresh);

    comeBack(WORKBENCH_RETURN_REREAD_MIN_MS);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('reads nothing for a page nobody is looking at', () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    header(onRefresh);
    hiddenPage(true);

    vi.setSystemTime(Date.now() + WORKBENCH_RETURN_REREAD_MIN_MS);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('counts a re-read the person asked for', async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    header(onRefresh);
    vi.setSystemTime(Date.now() + WORKBENCH_RETURN_REREAD_MIN_MS);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: REFRESH }));
    });
    onRefresh.mockClear();

    comeBack(1);

    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('calls what the screen reads now, never what it read when it opened', () => {
    const first = vi.fn().mockResolvedValue(undefined);
    const second = vi.fn().mockResolvedValue(undefined);
    const { rerender } = header(first);
    rerender(<WorkbenchToolHeader lng="en" tool="mail" onRefresh={second} />);

    comeBack(WORKBENCH_RETURN_REREAD_MIN_MS);

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('stops listening with the screen', () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const { unmount } = header(onRefresh);

    unmount();
    comeBack(WORKBENCH_RETURN_REREAD_MIN_MS);

    expect(onRefresh).not.toHaveBeenCalled();
  });
});
