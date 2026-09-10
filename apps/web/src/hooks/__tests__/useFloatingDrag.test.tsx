/**
 * useFloatingDrag — the one geometry machine under the eyes widget and the
 * shortcuts dock (ADR-277): a press that travels is a drag, a press that does
 * not is a click, a press on a control is that control's, and the arrows move
 * the SURFACE only while the surface itself holds the focus.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useRef } from 'react';

import {
  KEYBOARD_STEP_PX,
  clampToViewport,
  useFloatingDrag,
  type FloatingPosition,
} from '@/hooks/useFloatingDrag';

function Harness({
  position,
  setPosition,
}: {
  position: FloatingPosition | null;
  setPosition: (next: FloatingPosition) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useFloatingDrag(ref, position, setPosition);
  return (
    <div
      ref={ref}
      role="group"
      aria-label="surface"
      data-testid="surface"
      tabIndex={0}
      onPointerDown={drag.onPointerDown}
      onPointerMove={drag.onPointerMove}
      onPointerUp={drag.onPointerUp}
      onKeyDown={drag.onKeyDown}
      data-dragging={drag.dragPos ? 'yes' : 'no'}
      data-recent={drag.wasRecentDrag() ? 'yes' : 'no'}
    >
      <a href="#elsewhere">link</a>
      <button type="button">button</button>
    </div>
  );
}

const pct = (px: number, extent: number) => (px / extent) * 100;

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useFloatingDrag', () => {
  it('a drag beyond the threshold commits the spot as viewport percentages', () => {
    const setPosition = vi.fn();
    render(<Harness position={null} setPosition={setPosition} />);
    const surface = screen.getByTestId('surface');

    fireEvent.pointerDown(surface, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(surface, { pointerId: 1, clientX: 160, clientY: 140 });
    expect(surface).toHaveAttribute('data-dragging', 'yes');
    fireEvent.pointerUp(surface, { pointerId: 1, clientX: 160, clientY: 140 });

    expect(setPosition).toHaveBeenCalledTimes(1);
    const [next] = setPosition.mock.calls[0] as [FloatingPosition];
    // jsdom lays the surface out at (0, 0): the drop lands 60 px right, 40 px down.
    expect(next.xPct).toBeCloseTo(pct(60, window.innerWidth), 5);
    expect(next.yPct).toBeCloseTo(pct(40, window.innerHeight), 5);
    expect(surface).toHaveAttribute('data-dragging', 'no');
    expect(surface).toHaveAttribute('data-recent', 'yes');
  });

  it('a micro-move stays a click and commits nothing', () => {
    const setPosition = vi.fn();
    render(<Harness position={null} setPosition={setPosition} />);
    const surface = screen.getByTestId('surface');

    fireEvent.pointerDown(surface, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(surface, { pointerId: 1, clientX: 102, clientY: 101 });
    expect(surface).toHaveAttribute('data-dragging', 'no');
    fireEvent.pointerUp(surface, { pointerId: 1, clientX: 102, clientY: 101 });

    expect(setPosition).not.toHaveBeenCalled();
    expect(surface).toHaveAttribute('data-recent', 'no');
  });

  it('a press on a link or a button is theirs, never a drag', () => {
    const setPosition = vi.fn();
    render(<Harness position={null} setPosition={setPosition} />);
    const surface = screen.getByTestId('surface');

    for (const control of [screen.getByRole('link'), screen.getByRole('button')]) {
      fireEvent.pointerDown(control, { pointerId: 3, clientX: 10, clientY: 10 });
      fireEvent.pointerMove(surface, { pointerId: 3, clientX: 90, clientY: 90 });
      fireEvent.pointerUp(surface, { pointerId: 3, clientX: 90, clientY: 90 });
    }

    expect(setPosition).not.toHaveBeenCalled();
    expect(surface).toHaveAttribute('data-dragging', 'no');
  });

  it('arrow keys on the surface itself move it one step', () => {
    const setPosition = vi.fn();
    render(<Harness position={null} setPosition={setPosition} />);

    fireEvent.keyDown(screen.getByTestId('surface'), { key: 'ArrowRight' });

    expect(setPosition).toHaveBeenCalledTimes(1);
    const [next] = setPosition.mock.calls[0] as [FloatingPosition];
    expect(next.xPct).toBeCloseTo(pct(KEYBOARD_STEP_PX, window.innerWidth), 5);
    expect(next.yPct).toBe(0);
  });

  it('adds a keyboard step to a stored spot', () => {
    const setPosition = vi.fn();
    render(<Harness position={{ xPct: 50, yPct: 50 }} setPosition={setPosition} />);

    fireEvent.keyDown(screen.getByTestId('surface'), { key: 'ArrowDown' });

    const [next] = setPosition.mock.calls.at(-1) as [FloatingPosition];
    expect(next.xPct).toBeCloseTo(50, 5);
    expect(next.yPct).toBeCloseTo(50 + pct(KEYBOARD_STEP_PX, window.innerHeight), 5);
  });

  it('leaves the arrows to a focused control inside', () => {
    const setPosition = vi.fn();
    render(<Harness position={null} setPosition={setPosition} />);

    fireEvent.keyDown(screen.getByRole('link'), { key: 'ArrowRight' });
    fireEvent.keyDown(screen.getByRole('button'), { key: 'ArrowDown' });

    expect(setPosition).not.toHaveBeenCalled();
  });

  it('ignores every other key', () => {
    const setPosition = vi.fn();
    render(<Harness position={null} setPosition={setPosition} />);

    fireEvent.keyDown(screen.getByTestId('surface'), { key: 'Enter' });

    expect(setPosition).not.toHaveBeenCalled();
  });

  it('pulls a stored spot back on screen at mount', () => {
    // A spot saved on a wider screen sits off this viewport's right edge.
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 100,
      height: 40,
      left: 0,
      top: 0,
      right: 100,
      bottom: 40,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);
    const setPosition = vi.fn();

    render(<Harness position={{ xPct: 100, yPct: 10 }} setPosition={setPosition} />);

    expect(setPosition).toHaveBeenCalledTimes(1);
    const [next] = setPosition.mock.calls[0] as [FloatingPosition];
    expect(next.xPct).toBeCloseTo(pct(window.innerWidth - 100, window.innerWidth), 5);
    expect(next.yPct).toBeCloseTo(10, 5);
  });

  it('leaves a spot that is already on screen alone', () => {
    const setPosition = vi.fn();

    render(<Harness position={{ xPct: 10, yPct: 10 }} setPosition={setPosition} />);

    expect(setPosition).not.toHaveBeenCalled();
  });
});

describe('clampToViewport', () => {
  it('keeps the whole widget inside the viewport', () => {
    const size = { w: 100, h: 40 };
    expect(clampToViewport({ x: -20, y: -5 }, size)).toEqual({ x: 0, y: 0 });
    expect(clampToViewport({ x: 5000, y: 5000 }, size)).toEqual({
      x: window.innerWidth - 100,
      y: window.innerHeight - 40,
    });
    expect(clampToViewport({ x: 30, y: 30 }, size)).toEqual({ x: 30, y: 30 });
  });
});

function ButtonHarness({ setPosition }: { setPosition: (next: FloatingPosition) => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  const drag = useFloatingDrag(ref, null, setPosition);
  return (
    <button
      ref={ref}
      type="button"
      data-testid="dot"
      onPointerDown={drag.onPointerDown}
      onPointerMove={drag.onPointerMove}
      onPointerUp={drag.onPointerUp}
    >
      dot
    </button>
  );
}

describe('a surface that is itself a button', () => {
  it('still drags — only interactive DESCENDANTS are left alone', () => {
    const setPosition = vi.fn();
    render(<ButtonHarness setPosition={setPosition} />);
    const dot = screen.getByTestId('dot');

    fireEvent.pointerDown(dot, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(dot, { pointerId: 1, clientX: 160, clientY: 140 });
    fireEvent.pointerUp(dot, { pointerId: 1, clientX: 160, clientY: 140 });

    expect(setPosition).toHaveBeenCalledTimes(1);
  });
});
