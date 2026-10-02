/**
 * MarkdownContent — the KaTeX stylesheet the layout serves styles the markup
 * the renderer emits.
 *
 * Two copies of KaTeX lived side by side from 2026-07-20: `rehype-katex`
 * rendered with 0.16 while `app/[lng]/layout.tsx` imported the 0.18 stylesheet,
 * whose layout classes had been renamed (`base` → `katex-base`, `strut` →
 * `katex-strut`, …). Nothing failed: overlines, underlines, `\Huge`/`\tiny`,
 * script sizes and accents silently lost their rules. This guard renders through
 * the real component and reads the real stylesheet, so a split is red the day
 * it lands.
 */

import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const requireFromHere = createRequire(import.meta.url);

/** The stylesheet `app/[lng]/layout.tsx` imports, as the app resolves it. */
const SERVED_CSS = readFileSync(requireFromHere.resolve('katex/dist/katex.min.css'), 'utf8');
const STYLED = new Set(Array.from(SERVED_CSS.matchAll(/\.([A-Za-z_][\w-]*)/g), m => m[1]));

/**
 * Classes KaTeX emits to name an atom's TeX type or an error, which its own
 * stylesheet never styles in any version (measured on 0.16.45 and 0.18.9).
 */
const UNSTYLED_BY_DESIGN = new Set([
  'katex-error',
  'mbin',
  'mclose',
  'minner',
  'mop',
  'mopen',
  'mord',
  'mpunct',
  'mrel',
  'mtight',
  'text',
]);

/**
 * Formulas reaching the layout classes that moved: fractions, roots, scripts,
 * sizes, accents, matrices, tags. Display blocks, so `\tag` is legal.
 */
const FORMULAS = [
  String.raw`x_{1,2}=\frac{-b\pm\sqrt{b^2-4ac}}{2a}`,
  String.raw`\sum_{i=0}^{n} i^2 = \frac{n(n+1)(2n+1)}{6}`,
  String.raw`\overline{AB} + \underline{x} + \hat{y} + \vec{v}`,
  String.raw`\begin{pmatrix}a&b\\c&d\end{pmatrix} \quad \underbrace{a+b}_{n}`,
  String.raw`\Huge A \normalsize b \tiny c`,
  String.raw`\text{if } x>0 \tag{1}`,
];
const CONTENT = FORMULAS.map(formula => `$$\n${formula}\n$$`).join('\n\n');

describe('MarkdownContent — served KaTeX stylesheet', () => {
  it('styles every layout class the renderer emits', () => {
    const { container } = render(<MarkdownContent content={CONTENT} />);

    const roots = container.querySelectorAll('.katex-display > .katex');
    expect(roots.length).toBe(FORMULAS.length);
    expect(container.querySelector('.katex-error')).toBeNull();

    const emitted = new Set<string>();
    roots.forEach(root => {
      root.classList.forEach(name => emitted.add(name));
      root
        .querySelectorAll('[class]')
        .forEach(el => el.classList.forEach(name => emitted.add(name)));
    });

    const unstyled = [...emitted]
      .filter(name => !STYLED.has(name) && !UNSTYLED_BY_DESIGN.has(name))
      .sort();
    expect(unstyled).toEqual([]);
  });
});
