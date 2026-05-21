/**
 * MarkdownContent — math delimiter handling.
 *
 * Regression guard: a single `$` must NOT be treated as an inline-math
 * delimiter, otherwise currency amounts ("1,50$ … 9$") get swallowed into a
 * KaTeX formula — spaces dropped, `*`→`∗`, `é`→`eˊ` (observed in interest
 * notifications). Display math `$$…$$` must keep working.
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('MarkdownContent — math delimiters', () => {
  it('renders currency amounts (single $) as literal text, not KaTeX', () => {
    const { container } = render(
      <MarkdownContent content="Tarif : 1,50$ le million en entrée et 9$ en sortie." />
    );
    // Spaces preserved → the phrase survives intact (would collapse if rendered as math).
    expect(container.textContent).toContain('le million en entrée et 9');
    // No math span was produced.
    expect(container.querySelector('.katex')).toBeNull();
  });

  it('still renders display math ($$…$$) via KaTeX', () => {
    const { container } = render(<MarkdownContent content={'$$a + b$$'} />);
    expect(container.querySelector('.katex')).not.toBeNull();
  });
});
