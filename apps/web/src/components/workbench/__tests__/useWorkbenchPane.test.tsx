/**
 * A « Tools » pane sized by hand (owner request 2026-10-31): untouched, it keeps
 * its layout's width and its separator starts from where it is drawn; dragged
 * or moved by the keyboard, it draws the chosen width inside its bounds and the
 * device remembers it; Enter gives the layout its width back.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PaneSeparator } from '@/components/ui/pane-separator';
import { WORKBENCH_PANES_PREFS_KEY } from '@/lib/constants';
import { WORKBENCH_PANES } from '@/lib/workbench/panes';
import { useWorkbenchPanesStore } from '@/stores/workbenchPanesStore';

import { useWorkbenchPane } from '../useWorkbenchPane';

// A row narrow enough for the pane's share, not its declared maximum, to bound it.
const ROW = 1200;
// Drawn at a width other than the declared `initial`: the separator reads the drawing.
const DRAWN = 250;
const SPEC = WORKBENCH_PANES['mail.folders'];
const MAX = Math.min(SPEC.max, Math.floor(ROW * SPEC.share));

/** jsdom lays nothing out: the row and the pane report fixed widths. */
function layout() {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement
  ) {
    const width = this.dataset.row !== undefined ? ROW : DRAWN;
    return {
      width,
      height: 600,
      top: 0,
      left: 0,
      right: width,
      bottom: 600,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect;
  });
}

function Pane() {
  const folders = useWorkbenchPane('en', 'mail.folders');
  return (
    <div data-row="">
      <nav {...folders.pane} data-resized={folders.resized ? '' : undefined} />
      <PaneSeparator {...folders.separator} />
    </div>
  );
}

const handle = () => screen.getByRole('separator', { name: SPEC.labelKey });
const pane = () => document.getElementById(handle().getAttribute('aria-controls') ?? '');

beforeEach(() => {
  localStorage.removeItem(WORKBENCH_PANES_PREFS_KEY);
  useWorkbenchPanesStore.setState({ widths: {} });
  layout();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useWorkbenchPane', () => {
  it('keeps the layout’s width until someone sizes it, starting from where it is drawn', () => {
    render(<Pane />);

    expect(handle()).toHaveAttribute('aria-valuenow', String(DRAWN));
    expect(handle()).toHaveAttribute('aria-valuemin', String(SPEC.min));
    expect(MAX).toBeLessThan(SPEC.max);
    expect(handle()).toHaveAttribute('aria-valuemax', String(MAX));
    expect(pane()).not.toHaveAttribute('data-resized');
    expect(pane()?.style.getPropertyValue('--pane-w')).toBe('');
  });

  it('draws the width chosen by the keyboard, and the device keeps it', () => {
    const { unmount } = render(<Pane />);

    fireEvent.keyDown(handle(), { key: 'ArrowRight' });

    expect(pane()).toHaveAttribute('data-resized');
    expect(pane()?.style.getPropertyValue('--pane-w')).toBe(`${DRAWN + 16}px`);
    expect(useWorkbenchPanesStore.getState().widths['mail.folders']).toBe(DRAWN + 16);
    unmount();

    render(<Pane />);
    expect(handle()).toHaveAttribute('aria-valuenow', String(DRAWN + 16));
  });

  it('draws a dragged width inside its bounds', () => {
    render(<Pane />);

    fireEvent.pointerDown(handle(), { pointerId: 1, clientX: 300 });
    fireEvent.pointerMove(handle(), { pointerId: 1, clientX: 5000 });

    expect(pane()?.style.getPropertyValue('--pane-w')).toBe(`${MAX}px`);
  });

  it('gives the layout its width back on Enter', () => {
    useWorkbenchPanesStore.getState().setWidth('mail.folders', 280);
    render(<Pane />);
    expect(pane()?.style.getPropertyValue('--pane-w')).toBe('280px');

    fireEvent.keyDown(handle(), { key: 'Enter' });

    expect(pane()).not.toHaveAttribute('data-resized');
    expect(useWorkbenchPanesStore.getState().widths).toEqual({});
  });

  it('draws a kept width the row cannot hold at the most the row allows', () => {
    useWorkbenchPanesStore.getState().setWidth('mail.folders', 5000);
    render(<Pane />);

    expect(pane()?.style.getPropertyValue('--pane-w')).toBe(`${MAX}px`);
    // Kept as chosen: a wider window gets it back.
    expect(useWorkbenchPanesStore.getState().widths['mail.folders']).toBe(5000);
  });
});
