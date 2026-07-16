/**
 * ReasoningScroll — renders the streamed reasoning children inside the capped,
 * auto-scrolling reasoning container.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { ReasoningScroll } from '../ReasoningScroll';

describe('ReasoningScroll', () => {
  it('renders its children inside the reasoning container', () => {
    const { container } = renderWithProviders(
      <ReasoningScroll>
        <p>Thinking about the answer…</p>
      </ReasoningScroll>
    );
    expect(screen.getByText('Thinking about the answer…')).toBeInTheDocument();
    expect(container.querySelector('.lia-reasoning')).not.toBeNull();
  });
});
