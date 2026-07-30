/**
 * The fixed cosmic layers must be decorative, drawn once, and redraw only on
 * debounced resize — never on scroll (zero continuous cost).
 */

import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CosmicBackdrop } from '../CosmicBackdrop';

function stubCanvasContext() {
  const context = {
    scale: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    fillStyle: '',
  };
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    context as unknown as CanvasRenderingContext2D
  );
  return context;
}

describe('CosmicBackdrop', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders all layers as a decorative subtree', () => {
    stubCanvasContext();
    render(<CosmicBackdrop />);
    const backdrop = screen.getByTestId('cosmic-backdrop');
    expect(backdrop).toHaveAttribute('aria-hidden', 'true');
    expect(backdrop.querySelector('.cosmos-nebula')).toBeInTheDocument();
    expect(backdrop.querySelector('canvas.cosmos-stars')).toBeInTheDocument();
    expect(backdrop.querySelector('.cosmos-grain')).toBeInTheDocument();
  });

  it('draws stars once on mount and once more after a debounced resize', () => {
    const context = stubCanvasContext();
    render(<CosmicBackdrop />);
    const drawsAfterMount = context.scale.mock.calls.length;
    expect(drawsAfterMount).toBe(1);

    // A burst of resizes coalesces into one redraw after the debounce.
    window.dispatchEvent(new Event('resize'));
    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(150);
    expect(context.scale.mock.calls.length).toBe(1);
    vi.advanceTimersByTime(100);
    expect(context.scale.mock.calls.length).toBe(2);
  });

  it('stops redrawing after unmount', () => {
    const context = stubCanvasContext();
    const { unmount } = render(<CosmicBackdrop />);
    unmount();
    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(500);
    expect(context.scale.mock.calls.length).toBe(1);
  });
});
