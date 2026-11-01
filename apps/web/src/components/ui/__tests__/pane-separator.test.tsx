/**
 * PaneSeparator — the window splitter shared by every pane a person sizes by
 * hand (the debug panel, the « Tools » panes): a focusable WAI-ARIA separator
 * whose drag, arrows (Shift for larger steps), Home/End and Enter or
 * double-click propose the pane's next width — always inside its bounds. Which
 * way widens depends on the edge of the pane it sits on.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { PaneSeparator } from '../pane-separator';

const BOUNDS = { min: 200, max: 500 };

/** A pane whose width the separator drives, as a caller keeps it. */
function Harness({
  edge,
  initial = 300,
  onReset = vi.fn(),
}: {
  edge: 'start' | 'end';
  initial?: number;
  onReset?: () => void;
}) {
  const [width, setWidth] = useState(initial);
  return (
    <>
      <div id="pane" />
      <PaneSeparator
        edge={edge}
        width={width}
        bounds={BOUNDS}
        step={16}
        label="Resize the folders"
        controls="pane"
        onResize={setWidth}
        onReset={() => {
          onReset();
          setWidth(initial);
        }}
      />
    </>
  );
}

const handle = () => screen.getByRole('separator', { name: 'Resize the folders' });
const now = () => Number(handle().getAttribute('aria-valuenow'));

describe('PaneSeparator', () => {
  it('is a vertical separator a keyboard can reach, naming the pane it sizes', () => {
    render(<Harness edge="end" />);

    expect(handle()).toHaveAttribute('aria-orientation', 'vertical');
    expect(handle()).toHaveAttribute('tabindex', '0');
    expect(handle()).toHaveAttribute('aria-controls', 'pane');
    expect(handle()).toHaveAttribute('aria-valuenow', '300');
    expect(handle()).toHaveAttribute('aria-valuemin', '200');
    expect(handle()).toHaveAttribute('aria-valuemax', '500');
  });

  it('on a pane’s right edge, widens it with ArrowRight, four times as far with Shift', () => {
    render(<Harness edge="end" />);

    fireEvent.keyDown(handle(), { key: 'ArrowRight' });
    expect(now()).toBe(316);
    fireEvent.keyDown(handle(), { key: 'ArrowLeft', shiftKey: true });
    expect(now()).toBe(252);
  });

  it('on a pane’s left edge, widens it with ArrowLeft', () => {
    render(<Harness edge="start" />);

    fireEvent.keyDown(handle(), { key: 'ArrowLeft' });
    expect(now()).toBe(316);
    fireEvent.keyDown(handle(), { key: 'ArrowRight' });
    expect(now()).toBe(300);
  });

  it('reaches the bounds with Home and End, and never passes them', () => {
    render(<Harness edge="end" />);

    fireEvent.keyDown(handle(), { key: 'End' });
    expect(now()).toBe(500);
    fireEvent.keyDown(handle(), { key: 'ArrowRight', shiftKey: true });
    expect(now()).toBe(500);
    fireEvent.keyDown(handle(), { key: 'Home' });
    expect(now()).toBe(200);
    fireEvent.keyDown(handle(), { key: 'ArrowLeft' });
    expect(now()).toBe(200);
  });

  it('restores the pane on Enter and on a double-click', () => {
    const onReset = vi.fn();
    render(<Harness edge="end" onReset={onReset} />);

    fireEvent.keyDown(handle(), { key: 'End' });
    fireEvent.keyDown(handle(), { key: 'Enter' });
    expect(now()).toBe(300);
    fireEvent.keyDown(handle(), { key: 'End' });
    fireEvent.doubleClick(handle());
    expect(now()).toBe(300);
    expect(onReset).toHaveBeenCalledTimes(2);
  });

  it('follows a drag on either edge, inside the bounds', () => {
    const right = render(<Harness edge="end" />);
    fireEvent.pointerDown(handle(), { pointerId: 1, clientX: 600 });
    fireEvent.pointerMove(handle(), { pointerId: 1, clientX: 680 });
    expect(now()).toBe(380);
    fireEvent.pointerMove(handle(), { pointerId: 1, clientX: 2000 });
    expect(now()).toBe(500);
    fireEvent.pointerUp(handle(), { pointerId: 1, clientX: 2000 });
    // Released: a later move drags nothing.
    fireEvent.pointerMove(handle(), { pointerId: 1, clientX: 100 });
    expect(now()).toBe(500);
    right.unmount();

    render(<Harness edge="start" />);
    fireEvent.pointerDown(handle(), { pointerId: 1, clientX: 600 });
    fireEvent.pointerMove(handle(), { pointerId: 1, clientX: 550 });
    expect(now()).toBe(350);
    fireEvent.pointerCancel(handle(), { pointerId: 1 });
    fireEvent.pointerMove(handle(), { pointerId: 1, clientX: 300 });
    expect(now()).toBe(350);
  });

  it('leaves every other key alone', () => {
    render(<Harness edge="end" />);
    const event = fireEvent.keyDown(handle(), { key: 'a' });

    expect(event).toBe(true);
    expect(now()).toBe(300);
  });
});
