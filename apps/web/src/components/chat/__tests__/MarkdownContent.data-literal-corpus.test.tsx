/**
 * A value a draft card draws as itself renders as its characters in the chat.
 *
 * The server draws every value of a card with numeric references
 * (`markdown_data_literal`, ADR-323 review 14) and pins each drawing in a
 * corpus (`apps/api/tests/unit/domains/shared/data_literal_corpus.json`); this
 * test renders the SAME corpus through the chat's own pipeline. A value reads
 * as the characters it holds — no emphasis, no strike-through, no image, no
 * formula — and the only links are addresses reading as themselves: the
 * references the server wrote into a URL used to cut the link or send it
 * elsewhere (`jean&#95;dupont@example.com` linked to `dupont@example.com`).
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

interface Case {
  id: string;
  value: string;
  drawn: string;
}

const CORPUS = join(
  process.cwd(),
  '..',
  'api',
  'tests',
  'unit',
  'domains',
  'shared',
  'data_literal_corpus.json'
);
const corpus = JSON.parse(readFileSync(CORPUS, 'utf8')) as { cases: Case[]; html: Case[] };
const cases = corpus.cases;

/** A link is honest when it reads as the address it goes to. */
function readsAsItsAddress(link: HTMLAnchorElement): boolean {
  const href = decodeURI(link.getAttribute('href') ?? '');
  const text = link.textContent ?? '';
  return [text, `mailto:${text}`, `http://${text}`].includes(href);
}

describe('MarkdownContent — values drawn as themselves (shared corpus)', () => {
  it.each(cases)('$id reads as its characters', ({ value, drawn }) => {
    const { container } = render(<MarkdownContent content={`**Label** : ${drawn}`} />);

    expect(container.textContent?.replace(/\s+/g, ' ').trim()).toBe(
      `Label : ${value.replace(/\s+/g, ' ')}`
    );
    expect(container.querySelectorAll('em, del, s, img, .katex')).toHaveLength(0);
    for (const link of container.querySelectorAll('a')) {
      expect(readsAsItsAddress(link)).toBe(true);
    }
  });

  it('the corpus is not trivial', () => {
    expect(cases.length).toBeGreaterThanOrEqual(15);
  });
});

describe("MarkdownContent — an HTML card's values drawn as themselves (shared corpus)", () => {
  // The chat reads math in an HTML card's DECODED text: « rm -rf $BACKUP_DIR/$OLD »
  // drew a formula until `escape_html` referenced it (review 14).
  it.each(corpus.html)('$id reads as its characters', ({ value, drawn }) => {
    const card = `<div class="lia-card"><div class="lia-d-row"><span>${drawn}</span></div></div>`;

    const { container } = render(<MarkdownContent content={card} />);

    expect(container.textContent?.replace(/\s+/g, ' ').trim()).toBe(value.replace(/\s+/g, ' '));
    expect(container.querySelectorAll('a, em, del, s, img, code, .katex')).toHaveLength(0);
  });
});
