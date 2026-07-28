/**
 * FAQ search helpers — HTML stripping and accent-aware highlighting.
 *
 * The highlighter writes `<mark>` into translation HTML that the FAQ then
 * renders with `dangerouslySetInnerHTML`, so two properties matter beyond
 * "it highlights": the output must never contain anything the USER typed
 * (only slices of the trusted source text), and it must never open or close a
 * tag it did not find in the source.
 *
 * The third property is structural: this module used to carry its OWN
 * normalized-position mapping, a hand-rolled O(n²) double loop, while
 * `utils.findNormalizedMatches` — the helper the rest of the search stack uses
 * (`search-excerpt`, `rehype-search-highlight`) — solves exactly the same
 * problem. Its docstring even claimed "same mapping the FAQ highlighter uses".
 * Two implementations of one rule drift; the differential class below pins them
 * to the same answer.
 */

import { describe, expect, it } from 'vitest';

import { highlightText, stripHtml } from '@/lib/faq-search';
import { findNormalizedMatches, normalizeSearchText } from '@/lib/utils';

const MARK_OPEN = '<mark class="bg-yellow-200 dark:bg-yellow-800 rounded px-0.5">';

/** The substrings the highlighter wrapped, in order. */
function highlighted(output: string): string[] {
  return [...output.matchAll(/<mark[^>]*>([\s\S]*?)<\/mark>/g)].map(match => match[1]);
}

describe('stripHtml', () => {
  it('replaces tags with a space so adjacent words do not weld together', () => {
    expect(stripHtml('<p>Bonjour</p><p>Monde</p>')).toBe('Bonjour Monde');
  });

  it('collapses runs of whitespace and trims', () => {
    expect(stripHtml('  <p>  a \n\n  b  </p> ')).toBe('a b');
  });

  it('leaves plain text untouched', () => {
    expect(stripHtml('déjà vu')).toBe('déjà vu');
  });

  it('drops attributes along with their tag', () => {
    expect(stripHtml('<a href="https://x.test" title="Aller">lien</a>')).toBe('lien');
  });
});

describe('highlightText', () => {
  it('returns the text untouched for an empty or blank query', () => {
    expect(highlightText('Comment ça marche ?', '')).toBe('Comment ça marche ?');
    expect(highlightText('Comment ça marche ?', '   ')).toBe('Comment ça marche ?');
  });

  it('returns the text untouched when the query normalizes to nothing', () => {
    // A lone combining acute normalizes away entirely.
    expect(highlightText('Comment ça marche ?', '́')).toBe('Comment ça marche ?');
  });

  it('wraps the match in the mark element', () => {
    expect(highlightText('Comment ça marche', 'ça')).toBe(`Comment ${MARK_OPEN}ça</mark> marche`);
  });

  it('matches without regard to case', () => {
    expect(highlighted(highlightText('Sécurité des données', 'SÉCURITÉ'))).toEqual(['Sécurité']);
  });

  it('matches without regard to accents, and preserves them in the output', () => {
    // Typing "securite" must find "sécurité" AND leave the accents intact.
    expect(highlighted(highlightText('La sécurité avant tout', 'securite'))).toEqual(['sécurité']);
  });

  it('highlights every occurrence', () => {
    expect(highlighted(highlightText('data, data et data', 'data'))).toEqual([
      'data',
      'data',
      'data',
    ]);
  });

  it('never highlights inside a tag', () => {
    // "mark" appears in the class attribute of the source markup: highlighting
    // it would emit a <mark> inside an attribute value and break the HTML.
    const source = '<span class="marker">un mark visible</span>';
    const output = highlightText(source, 'mark');

    expect(highlighted(output)).toEqual(['mark']);
    expect(output).toContain('<span class="marker">');
  });

  it('keeps the tag structure balanced', () => {
    const source = '<p>Le <strong>chiffrement</strong> est actif</p>';
    const output = highlightText(source, 'chiffrement');

    expect(output).toBe(
      `<p>Le <strong>${MARK_OPEN}chiffrement</strong> est actif</p>`.replace(
        `${MARK_OPEN}chiffrement`,
        `${MARK_OPEN}chiffrement</mark>`
      )
    );
    expect((output.match(/<mark/g) ?? []).length).toBe((output.match(/<\/mark>/g) ?? []).length);
  });

  it('treats a query with regex metacharacters as literal text', () => {
    // Unescaped, ".*" would match the whole string; "(" would throw.
    expect(highlightText('Prix: 10.50 EUR', '.*')).toBe('Prix: 10.50 EUR');
    expect(() => highlightText('Coût (TTC)', '(')).not.toThrow();
    expect(highlighted(highlightText('Coût (TTC)', '(TTC)'))).toEqual(['(TTC)']);
  });

  it('emits nothing the user typed — only slices of the source text', () => {
    const injection = '<img src=x onerror=alert(1)>';
    const output = highlightText('Une réponse sans image', injection);

    expect(output).toBe('Une réponse sans image');
    expect(output).not.toContain('onerror');
  });

  it('highlights the source spelling, not the query spelling', () => {
    const output = highlightText('RÉUNION hebdomadaire', 'reunion');

    expect(highlighted(output)).toEqual(['RÉUNION']);
    expect(output).not.toContain('reunion<');
  });
});

describe('highlightText agrees with the canonical matcher', () => {
  // Text WITHOUT tags: the highlighter's per-part path is then exactly the
  // problem `findNormalizedMatches` solves, so the two must select the same
  // characters. A divergence here means one of the two mappings is wrong.
  const corpus: Array<[string, string]> = [
    ['La sécurité avant tout', 'securite'],
    ['RÉUNION hebdomadaire', 'reunion'],
    ['déjà vu, déjà vécu', 'deja'],
    ['Ça coûte 10 EUR', 'ca coute'],
    ['data data data', 'data'],
    ['Ærø et œuvre', 'oeuvre'],
    ['sans correspondance', 'introuvable'],
    ['Une phrase entière', 'Une phrase entière'],
    ['aaa', 'aa'],
    ['ÉÉÉ', 'ee'],
  ];

  it.each(corpus)(
    'selects the same characters as findNormalizedMatches in %j / %j',
    (text, query) => {
      const expected = findNormalizedMatches(text, normalizeSearchText(query)).map(range =>
        text.slice(range.start, range.end)
      );

      expect(highlighted(highlightText(text, query))).toEqual(expected);
    }
  );

  it('reconstructs the original text when the marks are removed', () => {
    for (const [text, query] of corpus) {
      const stripped = highlightText(text, query)
        .replace(/<mark[^>]*>/g, '')
        .replace(/<\/mark>/g, '');

      expect(stripped).toBe(text);
    }
  });
});
