/**
 * ExpressiveEyes — presentational contract.
 *
 * The component is purely declarative: expression → data attribute (CSS owns
 * the motion), gaze → custom properties, size → scale class, blink/wink →
 * transient classes. Decorative by design: aria-hidden, no role, no text.
 * No test waits on an animation (jsdom emits no animation events).
 */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';

import { ExpressiveEyes } from '../ExpressiveEyes';

function eyesRoot(container: HTMLElement): HTMLElement {
  const root = container.querySelector('.lia-eyes');
  if (!(root instanceof HTMLElement)) throw new Error('eyes root not rendered');
  return root;
}

describe('ExpressiveEyes', () => {
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

  it('exposes the gaze as CSS custom properties, clamped to [-1, 1]', () => {
    const { container } = render(
      <ExpressiveEyes expression="thinking" gaze={{ x: -0.6, y: -2 }} size="md" />
    );
    const root = eyesRoot(container);
    expect(root.style.getPropertyValue('--gaze-x')).toBe('-0.6');
    expect(root.style.getPropertyValue('--gaze-y')).toBe('-1');
  });

  it('a null gaze centers the eyes', () => {
    const { container } = render(<ExpressiveEyes expression="neutral" gaze={null} size="md" />);
    const root = eyesRoot(container);
    expect(root.style.getPropertyValue('--gaze-x')).toBe('0');
    expect(root.style.getPropertyValue('--gaze-y')).toBe('0');
  });

  it('blinking toggles the transient blink class', () => {
    const { container, rerender } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="md" blinking />
    );
    expect(eyesRoot(container).classList.contains('is-blinking')).toBe(true);
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" />);
    expect(eyesRoot(container).classList.contains('is-blinking')).toBe(false);
  });

  it('carries the idle gesture as a data attribute, absent when null', () => {
    const { container, rerender } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="md" gesture="tilt" />
    );
    expect(eyesRoot(container).dataset.gesture).toBe('tilt');
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" gesture={null} />);
    expect(eyesRoot(container).dataset.gesture).toBeUndefined();
  });

  it('exposes the gaze travel time as --gaze-ms only when provided', () => {
    const { container, rerender } = render(
      <ExpressiveEyes expression="neutral" gaze={{ x: 0.2, y: 0 }} size="md" gazeDurationMs={90} />
    );
    expect(eyesRoot(container).style.getPropertyValue('--gaze-ms')).toBe('90ms');
    rerender(<ExpressiveEyes expression="neutral" gaze={{ x: 0.2, y: 0 }} size="md" />);
    expect(eyesRoot(container).style.getPropertyValue('--gaze-ms')).toBe('');
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

  it('accepts an extra className for the host to position it', () => {
    const { container } = render(
      <ExpressiveEyes expression="neutral" gaze={null} size="md" className="extra" />
    );
    expect(eyesRoot(container).classList.contains('extra')).toBe(true);
  });

  it('every engine expression renders without error and lands in the data attribute', () => {
    const expressions = [
      'neutral',
      'joy',
      'excited',
      'tender',
      'surprise',
      'fear',
      'anger',
      'sad',
      'worried',
      'question',
      'thinking',
      'searching',
      'focused',
      'attentive',
      'speaking',
      'bored',
      'tired',
      'sleepy',
      'sleep',
      'wink',
    ] as const;
    for (const expression of expressions) {
      const { container, unmount } = render(
        <ExpressiveEyes expression={expression} gaze={null} size="md" />
      );
      expect(eyesRoot(container).dataset.expression).toBe(expression);
      unmount();
    }
  });
});
