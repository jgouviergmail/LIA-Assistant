/**
 * TypingIndicator — random variant selection and reduced-motion fallback.
 */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';

import { TypingIndicator, TYPING_VARIANTS } from '../TypingIndicator';

function root(container: HTMLElement): HTMLElement {
  return container.querySelector('[role="status"]') as HTMLElement;
}

describe('TypingIndicator', () => {
  it('renders one of the known variants with the status role and aria label', () => {
    const { container } = render(<TypingIndicator />);
    const el = root(container);
    expect(el).not.toBeNull();
    expect(el.getAttribute('aria-label')).toBe('chat.assistant_typing');
    expect(TYPING_VARIANTS).toContain(el.dataset.variant);
  });

  it('keeps the same variant across re-renders of one mount', () => {
    const { container, rerender } = render(<TypingIndicator />);
    const first = root(container).dataset.variant;
    rerender(<TypingIndicator />);
    rerender(<TypingIndicator />);
    expect(root(container).dataset.variant).toBe(first);
  });

  it('keeps the historical gray tint (no inline color override)', () => {
    const { container } = render(<TypingIndicator />);
    expect(root(container).className).toContain('text-gray-400');
    expect(root(container).style.color).toBe('');
  });

  it('ships a static reduced-motion fallback alongside the animated variant', () => {
    const { container } = render(<TypingIndicator />);
    expect(container.querySelector('.motion-reduce\\:hidden')).not.toBeNull();
    expect(container.querySelector('.motion-reduce\\:flex')).not.toBeNull();
  });
});
