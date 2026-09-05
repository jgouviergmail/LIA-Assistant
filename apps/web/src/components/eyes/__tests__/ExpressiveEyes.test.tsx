/**
 * ExpressiveEyes — the presentational contract, in its two vocabularies.
 *
 * `data-*` is the STATE the host declares (expression, style, family,
 * gesture, blink, gaze aim): stable, synchronous, the probe the widget's own
 * behavioural tests read. `--rig-*` is the MOTION the rig computes and writes
 * on this node — asserted here at the two moments that matter: the first
 * paint (settled, no boot animation) and the arrival of a new pose.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, render } from '@testing-library/react';

import { ExpressiveEyes } from '../ExpressiveEyes';
import { EYE_EXPRESSIONS } from '../expression-engine';
import { resolvePose } from '../rig/poses';

function eyesRoot(container: HTMLElement): HTMLElement {
  const root = container.querySelector('.lia-eyes');
  if (!(root instanceof HTMLElement)) throw new Error('eyes root not rendered');
  return root;
}

/** Advance the animation loop by N frames (vitest fakes rAF with its timers). */
function runFrames(count: number): void {
  act(() => {
    vi.advanceTimersByTime(count * 16);
  });
}

afterEach(() => {
  vi.useRealTimers();
});

describe('ExpressiveEyes — declared state', () => {
  it('renders two eyes, decorative (aria-hidden), with the expression as data attribute', () => {
    const { container } = render(<ExpressiveEyes expression="joy" gaze={null} size="md" />);
    const root = eyesRoot(container);
    expect(root.getAttribute('aria-hidden')).toBe('true');
    expect(root.dataset.expression).toBe('joy');
    expect(container.querySelectorAll('.lia-eye')).toHaveLength(2);
    expect(container.querySelector('.lia-eye--left')).not.toBeNull();
    expect(container.querySelector('.lia-eye--right')).not.toBeNull();
  });

  it('carries the size preset as a modifier class', () => {
    const { container, rerender } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="sm" />
    );
    expect(eyesRoot(container).classList.contains('lia-eyes--sm')).toBe(true);
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="lg" />);
    expect(eyesRoot(container).classList.contains('lia-eyes--lg')).toBe(true);
  });

  it('publishes the gaze aim, clamped to [-1, 1]', () => {
    const { container } = render(
      <ExpressiveEyes expression="thinking" gaze={{ x: -0.6, y: -2 }} size="md" />
    );
    const root = eyesRoot(container);
    expect(root.dataset.gazeX).toBe('-0.6');
    expect(root.dataset.gazeY).toBe('-1');
  });

  it('a null gaze centers the eyes', () => {
    const { container } = render(<ExpressiveEyes expression="neutral" gaze={null} size="md" />);
    expect(eyesRoot(container).dataset.gazeX).toBe('0');
    expect(eyesRoot(container).dataset.gazeY).toBe('0');
  });

  it('publishes the gaze travel time only when the host states one', () => {
    const { container, rerender } = render(
      <ExpressiveEyes expression="neutral" gaze={{ x: 0.2, y: 0 }} size="md" gazeDurationMs={90} />
    );
    expect(eyesRoot(container).dataset.gazeMs).toBe('90');
    rerender(<ExpressiveEyes expression="neutral" gaze={{ x: 0.2, y: 0 }} size="md" />);
    expect(eyesRoot(container).dataset.gazeMs).toBeUndefined();
  });

  it('marks the blink cycle while the host holds it', () => {
    const { container, rerender } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="md" blinking />
    );
    expect(eyesRoot(container).dataset.blinking).toBe('true');
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" />);
    expect(eyesRoot(container).dataset.blinking).toBeUndefined();
  });

  it('carries the idle gesture as a data attribute, absent when null', () => {
    const { container, rerender } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="md" gesture="tilt" />
    );
    expect(eyesRoot(container).dataset.gesture).toBe('tilt');
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" gesture={null} />);
    expect(eyesRoot(container).dataset.gesture).toBeUndefined();
  });

  it('renders the floating emote with its glyph and leave phase', () => {
    const { container, rerender } = render(
      <ExpressiveEyes expression="question" gaze={null} size="md" emote="?" />
    );
    const emoteEl = container.querySelector('.lia-emote');
    expect(emoteEl?.textContent).toBe('?');
    expect(emoteEl?.getAttribute('data-emote')).toBe('?');
    expect(emoteEl?.classList.contains('is-leaving')).toBe(false);
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" emote="?" emoteLeaving />);
    expect(container.querySelector('.lia-emote')?.classList.contains('is-leaving')).toBe(true);
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" emote={null} />);
    expect(container.querySelector('.lia-emote')).toBeNull();
  });

  it('renders a rare cartoon accessory only while the host summons one', () => {
    const { container, rerender } = render(
      <ExpressiveEyes expression="sad" gaze={null} size="md" accessory="tear" />
    );
    expect(container.querySelector('.lia-accessory')?.getAttribute('data-accessory')).toBe('tear');
    rerender(<ExpressiveEyes expression="sad" gaze={null} size="md" accessory={null} />);
    expect(container.querySelector('.lia-accessory')).toBeNull();
  });

  it('gives each eye a brow and a pupil (the two organs)', () => {
    const { container } = render(<ExpressiveEyes expression="neutral" gaze={null} size="md" />);
    expect(container.querySelectorAll('.lia-eye-brow')).toHaveLength(2);
    expect(container.querySelectorAll('.lia-eye-pupil')).toHaveLength(2);
    // The brow sits OUTSIDE the lid layer: a blink must never clip it.
    const brow = container.querySelector('.lia-eye-brow');
    expect(brow?.parentElement?.classList.contains('lia-eye')).toBe(true);
    // The pupil sits INSIDE the shape, so the lids cover it like everything else.
    expect(
      container.querySelector('.lia-eye-pupil')?.parentElement?.classList.contains('lia-eye-shape')
    ).toBe(true);
  });

  it('lives on its own by default, and declares it when the host turns that off', () => {
    const { container, rerender } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="md" />
    );
    expect(container.querySelector('.lia-eyes')).not.toHaveAttribute('data-life');
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" life={false} />);
    expect(container.querySelector('.lia-eyes')).toHaveAttribute('data-life', 'off');
  });

  it('accepts an extra className for the host to position it', () => {
    const { container } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="md" className="extra" />
    );
    expect(eyesRoot(container).classList.contains('extra')).toBe(true);
  });

  it('every engine expression renders without error and lands in the data attribute', () => {
    for (const expression of EYE_EXPRESSIONS) {
      const { container, unmount } = render(
        <ExpressiveEyes expression={expression} gaze={null} size="md" />
      );
      expect(eyesRoot(container).dataset.expression).toBe(expression);
      unmount();
    }
  });
});

describe('ExpressiveEyes — the rig on the DOM', () => {
  it('paints the first frame already settled on its pose (no boot animation)', () => {
    const { container } = render(<ExpressiveEyes expression="sad" gaze={null} size="md" />);
    const root = eyesRoot(container);
    expect(root.style.getPropertyValue('--rig-sy-l')).toBe(String(resolvePose('sad', 'cozmo').syL));
    expect(root.style.getPropertyValue('--rig-oy-l')).toBe('100%');
  });

  it('renders each style with ITS silhouette, never the default one', () => {
    const { container } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="md" styleId="billes" />
    );
    expect(eyesRoot(container).style.getPropertyValue('--rig-r-top-l')).toBe('0.58em');
  });

  it('travels to a new pose over time instead of jumping to it', () => {
    vi.useFakeTimers();
    const { container, rerender } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="md" />
    );
    const root = eyesRoot(container);
    rerender(<ExpressiveEyes expression="anger" gaze={null} size="md" />);
    runFrames(2);
    const midway = Number(root.style.getPropertyValue('--rig-rot-l').replace('deg', ''));
    expect(midway).toBeLessThan(7);
    runFrames(90);
    expect(Number(root.style.getPropertyValue('--rig-rot-l').replace('deg', ''))).toBeCloseTo(7, 1);
  });

  it('closes the lid when the host announces a blink', () => {
    vi.useFakeTimers();
    const { container, rerender } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="md" />
    );
    const root = eyesRoot(container);
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" blinking />);
    runFrames(6);
    expect(Number(root.style.getPropertyValue('--rig-blink-l'))).toBeGreaterThan(0.5);
    runFrames(40);
    expect(Number(root.style.getPropertyValue('--rig-blink-l'))).toBeCloseTo(0, 2);
  });

  it('carries the gaze aim into the rig', () => {
    vi.useFakeTimers();
    const { container, rerender } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="md" />
    );
    const root = eyesRoot(container);
    rerender(<ExpressiveEyes expression="neutral" gaze={{ x: 1, y: 0 }} size="md" />);
    runFrames(60);
    expect(Number(root.style.getPropertyValue('--rig-gaze-x'))).toBeCloseTo(1, 1);
  });
});
