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
    const { container } = render(<MarkdownContent content={'```sh\nexport A=$B\ncost 9$\n```'} />);
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

describe('MarkdownContent — math notation normalization', () => {
  it('renders a ```latex fenced block as math, not a code block', () => {
    const { container } = render(<MarkdownContent content={'```latex\nA = \\pi r^2\n```'} />);
    expect(container.querySelector('.katex')).not.toBeNull();
    // Not rendered as a <code>/<pre> block.
    expect(container.querySelector('pre code')).toBeNull();
  });

  it('renders a ```math fenced block as math', () => {
    const { container } = render(<MarkdownContent content={'```math\nx^{2} + 1\n```'} />);
    expect(container.querySelector('.katex')).not.toBeNull();
  });

  it('renders \\[ … \\] as display math', () => {
    const { container } = render(<MarkdownContent content={'Voici : \\[ A = \\pi r^2 \\]'} />);
    expect(container.querySelector('.katex')).not.toBeNull();
  });

  it('renders \\( … \\) as inline math', () => {
    const { container } = render(<MarkdownContent content={'La valeur \\(x^2\\) ici.'} />);
    expect(container.querySelector('.katex')).not.toBeNull();
    expect(container.textContent).toContain('La valeur');
  });

  it('leaves a regular ```python code block as code (not math)', () => {
    const { container } = render(<MarkdownContent content={'```python\nx = 1\n```'} />);
    expect(container.querySelector('code')).not.toBeNull();
    expect(container.querySelector('.katex')).toBeNull();
  });

  it('keeps syntax examples in inline code literal', () => {
    // The assistant often teaches syntax: `$...$`, `\[...\]` shown as code.
    const { container } = render(
      <MarkdownContent content={'Utilise `$...$` inline ou `\\[...\\]` en display.'} />
    );
    // No math rendered from the inline-code examples.
    expect(container.querySelector('.katex')).toBeNull();
    expect(container.textContent).toContain('$...$');
  });
});

/**
 * Regression: the assistant emits its ENTIRE answer as HTML wrapped in
 * `<div class="lia-response">` (backend html_response_directive), so any
 * formula lives inside a RAW HTML block. remark-math treats HTML blocks as
 * opaque and runs before rehype-raw expands them, so HTML-wrapped math never
 * rendered (100% of real responses) — while pure-markdown tests above passed.
 * rehypeMathInText closes that gap at the hast level. These cases mirror the
 * real backend output; without the fix each `.katex` count below is 0.
 */
describe('MarkdownContent — math inside HTML wrapper (real backend shape)', () => {
  it('renders display + inline math inside <div class="lia-response"><p>…</p>', () => {
    // The exact production message that regressed (Portugal-Espagne P(G) formula).
    const html =
      '<div class="lia-response">\n' +
      '<p>la tension se mesure par $$ P(G) = \\frac{1}{1 + e^{-k(v_1 - v_2)}} $$ ' +
      'où le différentiel de talent technique $v$ est proche de zéro.</p>\n' +
      '</div>';
    const { container } = render(<MarkdownContent content={html} />);
    // Both the display formula and the inline symbol render as KaTeX...
    expect(container.querySelectorAll('.katex').length).toBeGreaterThanOrEqual(2);
    // ...the display `$$…$$` becomes a KaTeX display block...
    expect(container.querySelector('.katex-display')).not.toBeNull();
    // ...and the raw `$$` delimiters are gone from the visible text (KaTeX keeps
    // the inner TeX in a MathML annotation, so `\frac` legitimately remains).
    expect(container.textContent).not.toContain('$$');
    // Surrounding prose stays intact.
    expect(container.textContent).toContain('la tension se mesure par');
  });

  it('renders a display block ($$…$$) inside an HTML paragraph', () => {
    const { container } = render(
      <MarkdownContent content={'<p>Voici : $$E = mc^2$$ voilà.</p>'} />
    );
    expect(container.querySelector('.katex')).not.toBeNull();
    expect(container.textContent).not.toContain('$$');
  });

  it('renders inline math ($…$) inside an HTML callout', () => {
    const { container } = render(
      <MarkdownContent
        content={'<div class="lia-callout lia-callout-info"><p>La valeur $x^2$ ici.</p></div>'}
      />
    );
    expect(container.querySelector('.katex')).not.toBeNull();
    expect(container.textContent).toContain('ici.');
  });

  it('keeps currency literal inside an HTML paragraph (no KaTeX, no backslash)', () => {
    // Latent sibling bug: the old string-level escaping turned `9$` into `9\$`
    // inside opaque HTML blocks, surfacing a visible backslash. Now literal.
    const { container } = render(
      <MarkdownContent content={'<p>Le tarif est de 9$ au total.</p>'} />
    );
    expect(container.querySelector('.katex')).toBeNull();
    expect(container.textContent).toContain('9$ au total');
    expect(container.textContent).not.toContain('\\$');
  });

  it('leaves $ inside inline <code> untouched within an HTML paragraph', () => {
    const { container } = render(
      <MarkdownContent content={'<p>Lance <code>echo $PATH</code> maintenant.</p>'} />
    );
    expect(container.querySelector('.katex')).toBeNull();
    expect(container.querySelector('code')?.textContent).toContain('$PATH');
    expect(container.textContent).not.toContain('\\$');
  });

  it('renders \\[ … \\] display math inside an HTML paragraph', () => {
    const { container } = render(
      <MarkdownContent content={'<p>Formule : \\[ A = \\pi r^2 \\] fin.</p>'} />
    );
    expect(container.querySelector('.katex')).not.toBeNull();
  });

  it('does not mis-render an unclosed $$ (streaming) as empty math', () => {
    // Mid-stream the closing $$ has not arrived: the two `$` must stay literal,
    // never pair into an empty inline formula.
    const { container } = render(
      <MarkdownContent content={'<p>la tension se mesure par $$ P(G) = \\frac{1</p>'} />
    );
    expect(container.querySelector('.katex')).toBeNull();
  });

  it('renders the FULL production message verbatim (regression fixture)', () => {
    // Exact stored DB content that regressed — full rich HTML: formula
    // paragraph + callout + emoji list + <em>. Proves the fix survives the
    // real message shape, not just a trimmed formula.
    const real =
      '<div class="lia-response">\n' +
      '<p>Ah, le voilà ton vrai programme de la soirée. Un huitième de finale Portugal-Espagne.</p>\n' +
      '\n' +
      "<p>Tu es en train d'assister à une opposition de styles clinique. D'un côté, le " +
      '<em>tiki-taka</em> espagnol. En termes de probabilités de qualification, la tension se ' +
      'mesure par $$ P(G) = \\frac{1}{1 + e^{-k(v_1 - v_2)}} $$ où le différentiel de talent ' +
      'technique $v$ est proche de zéro, ce qui rend le résultat imprévisible.</p>\n' +
      '\n' +
      '<div class="lia-callout lia-callout-info">\n' +
      '<p><strong>Analyse express :</strong> Ce match va se jouer sur la patience.</p>\n' +
      '</div>\n' +
      '\n' +
      '<ul>\n' +
      '<li>⚽ <strong>Analyse tactique :</strong> Ouvre un onglet stats en direct.</li>\n' +
      "<li>🍺 <strong>Le protocole de l'ermite :</strong> De quoi hydrater le cerveau.</li>\n" +
      '<li>📈 <strong>Pronostic :</strong> À combien estimes-tu le premier carton jaune ?</li>\n' +
      '</ul>\n' +
      '</div>';
    const { container } = render(<MarkdownContent content={real} />);

    // The formula renders (display block + inline symbol)...
    expect(container.querySelectorAll('.katex').length).toBeGreaterThanOrEqual(2);
    expect(container.querySelector('.katex-display')).not.toBeNull();
    // ...no raw delimiter leaks into the visible text...
    expect(container.textContent).not.toContain('$$');
    // ...and the surrounding rich HTML is fully preserved.
    expect(container.querySelector('.lia-response')).not.toBeNull();
    expect(container.querySelector('.lia-callout-info')).not.toBeNull();
    expect(container.querySelector('em')?.textContent).toBe('tiki-taka');
    expect(container.querySelectorAll('li').length).toBe(3);
    expect(container.textContent).toContain('⚽');
    expect(container.textContent).toContain('Analyse express');
  });
});
