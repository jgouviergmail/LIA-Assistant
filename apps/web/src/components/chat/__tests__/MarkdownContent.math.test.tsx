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

  it('does not treat "$5 and $6" (currency) as math', () => {
    const { container } = render(<MarkdownContent content="Ça coûte $5 and $6 au total." />);
    expect(container.querySelector('.katex')).toBeNull();
    expect(container.textContent).toContain('$5 and $6');
  });

  it('still renders display math ($$…$$) via KaTeX', () => {
    const { container } = render(<MarkdownContent content={'$$a + b$$'} />);
    expect(container.querySelector('.katex')).not.toBeNull();
  });

  it('renders inline math ($…$) via KaTeX (MathJax delimiter rules)', () => {
    const { container } = render(
      <MarkdownContent content={'La formule $A = \\pi r^2$ est simple.'} />
    );
    // Inline math now renders...
    expect(container.querySelector('.katex')).not.toBeNull();
    // ...and the surrounding prose is intact.
    expect(container.textContent).toContain('La formule');
    expect(container.textContent).toContain('est simple.');
  });

  it('renders short inline symbols ($A$, $\\pi$)', () => {
    const { container } = render(
      <MarkdownContent content={'Où $A$ est l’aire et $\\pi$ la constante.'} />
    );
    expect(container.querySelectorAll('.katex').length).toBeGreaterThanOrEqual(2);
  });

  it('handles inline math and currency on the same line', () => {
    const { container } = render(
      <MarkdownContent content={'La valeur $x^2$ coûte 9$ en sortie.'} />
    );
    // The math renders...
    expect(container.querySelector('.katex')).not.toBeNull();
    // ...and the currency stays literal (not swallowed).
    expect(container.textContent).toContain('9$ en sortie');
  });

  it('renders inline math ending in a digit ($r^2$)', () => {
    // Regression: a naive "digit before $" currency heuristic would break
    // the closing delimiter of math that ends in a number.
    const { container } = render(<MarkdownContent content={'Le terme $r^2$ ici.'} />);
    expect(container.querySelector('.katex')).not.toBeNull();
  });

  it('leaves $ inside inline code untouched (no visible backslash)', () => {
    // The currency-protection preprocessor runs on the raw string; it must
    // skip code spans, else it would inject a literal "\$".
    const { container } = render(<MarkdownContent content={'Lance `echo $PATH` maintenant.'} />);
    const code = container.querySelector('code');
    expect(code?.textContent).toBe('echo $PATH');
    expect(container.textContent).not.toContain('\\$');
  });

  it('leaves $ inside fenced code blocks untouched', () => {
    const { container } = render(
      <MarkdownContent content={'```sh\nexport A=$B\ncost 9$\n```'} />
    );
    expect(container.textContent).toContain('$B');
    expect(container.textContent).toContain('9$');
    expect(container.textContent).not.toContain('\\$');
  });

  it('renders a dollar price inside an HTML card without a visible backslash', () => {
    const { container } = render(
      <MarkdownContent content={'<span class="lia-card__meta">9$</span>'} />
    );
    expect(container.querySelector('.lia-card__meta')?.textContent).toBe('9$');
    expect(container.textContent).not.toContain('\\$');
  });
});
