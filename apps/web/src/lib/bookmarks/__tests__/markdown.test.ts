/**
 * What a bookmark exports to (ADR-282): the chat's own `.md` path, plus what
 * the chat cannot know — the request, quoted, and the answer's date.
 */

import { describe, expect, it } from 'vitest';

import { bookmarkExportBaseName, bookmarkToMarkdown } from '@/lib/bookmarks/markdown';
import type { Bookmark } from '@/types/bookmarks';

const LABELS = { request: 'Request', answer: 'Answer', kept: 'Kept from LIA — answered on 12 Sept' };

function bookmark(over: Partial<Bookmark> = {}): Bookmark {
  return {
    id: 'b1',
    message_id: 'm1',
    conversation_id: 'c1',
    content: '**Réservé** : salle B, 14 h.\n\n- vidéoprojecteur\n- 6 places\n',
    request_content: 'Réserve la salle B à 14 h',
    answered_at: '2026-09-12T08:05:00Z',
    created_at: '2026-09-12T08:06:00Z',
    ...over,
  };
}

describe('bookmarkToMarkdown', () => {
  it('quotes the request above the answer, under dated and named headings', () => {
    const md = bookmarkToMarkdown(bookmark(), LABELS);

    expect(md).toBe(
      [
        '> Kept from LIA — answered on 12 Sept',
        '',
        '## Request',
        '',
        '> Réserve la salle B à 14 h',
        '',
        '## Answer',
        '',
        '**Réservé** : salle B, 14 h.\n\n- vidéoprojecteur\n- 6 places',
        '',
      ].join('\n')
    );
  });

  it('quotes EVERY line of a request that spans paragraphs', () => {
    // An unquoted second paragraph would read as the start of the answer.
    const md = bookmarkToMarkdown(
      bookmark({ request_content: 'Première ligne\n\nDeuxième ligne' }),
      LABELS
    );

    expect(md).toContain('> Première ligne\n>\n> Deuxième ligne');
  });

  it('omits the request section when the answer answered no request', () => {
    const md = bookmarkToMarkdown(bookmark({ request_content: null }), LABELS);

    expect(md).not.toContain('## Request');
    expect(md).toContain('## Answer');
  });

  it('flattens a lia-response HTML document like the chat export does', () => {
    const md = bookmarkToMarkdown(
      bookmark({ content: '<div class="lia-response"><p>Bonjour <b>Marie</b></p></div>' }),
      LABELS
    );

    expect(md).not.toContain('<div');
    expect(md).toContain('Bonjour Marie');
  });
});

describe('bookmarkExportBaseName', () => {
  it('stamps the ANSWER instant in the local clock, with the chat convention', () => {
    const at = new Date('2026-09-12T08:05:00Z');
    const expected = `lia-bookmark-${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, '0')}-${String(at.getDate()).padStart(2, '0')}-${String(at.getHours()).padStart(2, '0')}-${String(at.getMinutes()).padStart(2, '0')}`;

    expect(bookmarkExportBaseName(bookmark())).toBe(expected);
  });
});
