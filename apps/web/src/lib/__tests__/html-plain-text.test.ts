/**
 * html-plain-text — multi-line flattener for assistant HTML (ADR-177).
 *
 * Client-side mirror of the backend's `html_to_text` semantics
 * (display/components/base.py): same bullets ("• "), block spacing (one empty
 * line between blocks), inline tags stripped to '' (no injected space), ≤1
 * empty line, per-line trim. Extended for the ADR-177 vocabulary (dl/dt/dd,
 * details/summary, caption/figcaption). Feeds the clipboard text/plain flavor,
 * the native share sheet and the .md export.
 */
import { describe, it, expect } from 'vitest';

import { htmlToPlainText, looksLikeHtml } from '../html-plain-text';

const RICH = [
  '<div class="lia-response">',
  '<h2>Synthèse</h2>',
  '<p>Deux points <strong>clés</strong>.</p>',
  '<ul><li>Premier</li><li>Second</li></ul>',
  '<dl class="lia-kv"><dt>Date</dt><dd>12 août</dd></dl>',
  '<p>Icône <span class="material-symbols-outlined">event</span> masquée.</p>',
  '</div>',
].join('\n');

describe('looksLikeHtml', () => {
  it('detects the lia-response wrapper (attribute signal)', () => {
    expect(looksLikeHtml('<div class="lia-response"><p>x</p></div>')).toBe(true);
  });

  it('never flags prose with comparison operators', () => {
    expect(looksLikeHtml('if x<a and b>c then count<b et total>i')).toBe(false);
  });
});

describe('htmlToPlainText', () => {
  it('is a strict no-op on markdown/prose', () => {
    const md = '**gras**\n\n- item\n\nif x<a and b>c';
    expect(htmlToPlainText(md)).toBe(md);
  });

  it('flattens rich HTML to readable multi-line text', () => {
    const out = htmlToPlainText(RICH);
    expect(out).toContain('Synthèse');
    // Inline tags strip to '' — no space injected around "clés".
    expect(out).toContain('Deux points clés.');
    // List items become bullet lines (backend html_to_text uses "• ").
    expect(out).toMatch(/^• Premier$/m);
    expect(out).toMatch(/^• Second$/m);
    // dt/dd pairs read as "key : value".
    expect(out).toMatch(/Date\s*:\s*12 août/);
    // Icon ligature names are dropped whole.
    expect(out).not.toContain('event');
    // No tag survives; never more than one empty line in a row.
    expect(out).not.toMatch(/<[a-z]/i);
    expect(out).not.toMatch(/\n{3,}/);
  });

  it('separates blocks with exactly one empty line', () => {
    expect(htmlToPlainText('<div class="lia-response"><h2>Titre</h2><p>Corps</p></div>')).toBe(
      'Titre\n\nCorps'
    );
  });

  it('keeps link text and drops the href (backend preserve_links=False)', () => {
    expect(
      htmlToPlainText('<p>Voir <a href="https://example.com/x">la page</a> ici</p>')
    ).toBe('Voir la page ici');
  });

  it('renders hr as a separator line and br as a line break', () => {
    const out = htmlToPlainText('<p>Avant</p><hr><p>ligne1<br>ligne2</p>');
    expect(out).toContain('---');
    expect(out).toMatch(/^ligne1$/m);
    expect(out).toMatch(/^ligne2$/m);
  });

  it('decodes the fixed entity set after stripping', () => {
    expect(htmlToPlainText('<p>A&nbsp;&amp;&nbsp;B</p>')).toBe('A & B');
    // Quoted markup decodes to literal text — never re-stripped.
    expect(htmlToPlainText('<p>code : &lt;div&gt;</p>')).toBe('code : <div>');
  });

  it('flattens table rows with cell separators', () => {
    const out = htmlToPlainText(
      '<table><thead><tr><th>Option</th><th>Durée</th></tr></thead>' +
        '<tbody><tr><td>A</td><td>1 h</td></tr></tbody></table>'
    );
    expect(out).toMatch(/Option\s*\|\s*Durée/);
    expect(out).toMatch(/A\s*\|\s*1 h/);
  });

  it('flattens the ADR-177 collapsible and caption vocabulary', () => {
    const out = htmlToPlainText(
      '<details class="lia-collapsible"><summary>Détails</summary><p>corps</p></details>' +
        '<table><caption>Comparatif</caption><tbody><tr><td>x</td></tr></tbody></table>'
    );
    expect(out).toMatch(/^Détails$/m);
    expect(out).toContain('corps');
    expect(out).toMatch(/^Comparatif$/m);
  });
});
